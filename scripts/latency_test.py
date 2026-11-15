"""LLM latency and sanity test for MRIS.
Owner: Senthil

Sends 10 made-up merchant pages (no real websites, no internet) to Groq API through the same
prompt and JSON parser the real pipeline uses, and reports speed and basic correctness.

Usage (from the project root):
    python scripts/latency_test.py                              # default model from config.yaml
    python scripts/latency_test.py openai/gpt-oss-20b           # compare several models
    python scripts/latency_test.py --concurrency 1 4 8 --repeats 2
    python scripts/latency_test.py --quick                      # 10 calls only (a few minutes on a slow machine)
    python scripts/latency_test.py --mock                       # no model: just checks the script works
"""
import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402

# (name, page text, expected restricted_goods, expected refund_ambiguous, expected delivery_risk)  None = do not check
SAMPLES = [
    ("Clear outdoor shop",
     "TrailPeak Outfitters - hiking boots, jackets and backpacks. Free shipping on orders over $75. Orders ship within 2 business days "
     "and arrive in 3-5 business days. Returns: you may return unused items within 30 days for a full refund to your original "
     "payment method. Contact: support@trailpeak.example, 1-800-555-0142, 120 Main St, Calgary AB.", False, False, False),
    ("No refund policy",
     "BrightHome Decor - lamps, rugs and wall art. Add to cart. Secure checkout. Sale ends soon! Follow us on social media. "
     "All sales are processed securely. Sign up for our newsletter.", False, True, None),
    ("Vague delivery",
     "Handmade Candles by Lena - soy candles poured to order. Delivery: your order will arrive at some point, usually when it is ready. "
     "We cannot say how long it takes. Refunds: within 14 days if unused, contact us by email.", False, False, True),
    ("Firearms shop",
     "North Ridge Arms - rifles, shotguns, handguns and ammunition. Buy firearms and ammunition online with shipping to your door. "
     "No licence needed for accessories. Returns within 7 days.", True, None, None),
    ("Pre-order with no dates",
     "GadgetNova - the new X1 smart watch is available for pre-order now! Pay today and we will ship when stock arrives. "
     "Delivery date: to be announced. Refunds are handled case by case at our discretion.", False, True, True),
    ("Counterfeit goods",
     "LuxeReplica - designer handbags and watches, 1:1 copies of famous brands at 10% of the price. Looks exactly like the original "
     "brand. Worldwide shipping in 2-3 weeks. All sales final.", True, True, None),
    ("Software subscription",
     "CloudNote - a note-taking app for teams. Plans from $8/month. Cancel any time; we refund the unused part of your annual plan within "
     "30 days of purchase. Instant access after payment. Contact us at help@cloudnote.example.", False, False, False),
    ("Restaurant gift cards",
     "Harbour Grill - fresh seafood and steaks. Order gift cards online, delivered by email within minutes. Gift cards are non-refundable "
     "but can be replaced if lost. Phone 604-555-0199.", False, False, False),
    ("CBD and vape products",
     "CloudNine Vape - e-liquids, vape pens and CBD oils. Buy 3 get 1 free. Ships in 1-2 days. Must be 19 or older. "
     "Returns: unopened items only, within 10 days.", True, False, False),
    ("Furniture, long lead time",
     "Oakline Furniture - solid wood tables built to order. Lead time can be anywhere from 8 to 20 weeks depending on the workshop. "
     "Deposits are non-refundable once production begins. Call 403-555-0123.", False, False, True),
]


# acceptable industry names (substring match) for each sample, so the industry-number answer is checked too
INDUSTRY_OK = {
    "Clear outdoor shop": ("Sporting", "Clothing", "Shoes"),
    "No refund policy": ("Home decor", "Furniture"),
    "Vague delivery": ("Gifts", "Home decor"),
    "Firearms shop": ("Firearms",),
    "Pre-order with no dates": ("electronics", "Jewelry and watches"),
    "Counterfeit goods": ("Luggage", "Jewelry", "Clothing"),
    "Software subscription": ("SaaS", "Software"),
    "Restaurant gift cards": ("Restaurants", "Gifts"),
    "CBD and vape products": ("Tobacco", "Cannabis"),
    "Furniture, long lead time": ("Furniture",),
}


def installed_models(base_url: str) -> list:
    r = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=5)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def model_available(model: str, installed: list) -> bool:
    return model in installed or (":" not in model and f"{model}:latest" in installed)


async def one_call(client, text):
    from mris.llm.client import chat_json
    from mris.llm.analyze import parse_llm_json
    from mris.llm.prompts import build_messages
    t0 = time.perf_counter()
    valid, result, retried, raw = True, None, False, ""
    for attempt in range(2):
        try:
            raw = await chat_json(client, build_messages(text))
            result = parse_llm_json(raw)
            valid = True
            break
        except Exception as e:                               # noqa: BLE001 - count any failure as invalid
            valid, retried = False, attempt == 0
            raw = raw or f"ERROR: {e!r}"                     # show the real reason (HTTP error, bad JSON, ...)
    return time.perf_counter() - t0, valid, retried, result, raw


def check_expected(result, exp_restricted, exp_refund, exp_delivery, name=""):
    if result is None:
        return 0, 0
    pairs = [(result.restricted_goods.value, exp_restricted), (result.refund_ambiguous.value, exp_refund),
             (result.delivery_risk.value, exp_delivery)]
    checked = [(got, exp) for got, exp in pairs if exp is not None]
    good, n = sum(1 for got, exp in checked if got is exp), len(checked)
    ok_names = INDUSTRY_OK.get(name)
    if ok_names:
        n += 1
        good += 1 if any(k.lower() in result.industry.lower() for k in ok_names) else 0
    return good, n


async def run_model(model: str, concurrency_levels, repeats: int, verbose: bool, quick: bool = False) -> dict:
    from mris.config import get_config
    get_config()["llm"]["model"] = model
    out = {"model": model}
    async with httpx.AsyncClient() as client:
        print(f"\n=== {model} ===")
        print("Warm-up call (loads the model, not counted; the first call can take a minute)...", flush=True)
        await one_call(client, SAMPLES[0][1])

        print("Sequential run (one call at a time):")
        times, invalid, retried, ok, total = [], 0, 0, 0, 0
        for name, text, er, ef, ed in SAMPLES:
            sec, valid, rt, res, raw = await one_call(client, text)
            times.append(sec)
            invalid += 0 if valid else 1
            retried += 1 if rt else 0
            good, n = check_expected(res, er, ef, ed, name)
            ok, total = ok + good, total + n
            note = "INVALID JSON" if not valid else f"{good}/{n} expected answers"
            print(f"  {name:<26} {sec:6.2f}s  {note}", flush=True)
            if (not valid or good < n) and raw:
                print(f"      model said: {' '.join(raw.split())[:300]}", flush=True)
                print(f"      expected  : restricted={er} refund_ambiguous={ef} delivery_risk={ed} industry~{INDUSTRY_OK.get(name)}", flush=True)
                if res is not None:
                    print(f"      parsed    : industry='{res.industry}' mcc={res.mcc} naics={res.naics}", flush=True)
        out.update(mean=statistics.mean(times), median=statistics.median(times), slowest=max(times),
                   invalid=invalid, retried=retried, correct=ok, checked=total)
        print(f"  mean {out['mean']:.2f}s | median {out['median']:.2f}s | slowest {out['slowest']:.2f}s")
        print(f"  valid JSON: {len(SAMPLES) - invalid}/{len(SAMPLES)} (needed retry: {retried}) | "
              f"expected answers matched: {ok}/{total}")

        if quick:
            out["best_concurrency"], out["best_per_site"] = 1, out["mean"]
            return out
        print("Throughput with several calls at once:", flush=True)
        best = None
        for c in concurrency_levels:
            sem = asyncio.Semaphore(c)

            async def guarded(text):
                async with sem:
                    return await one_call(client, text)
            jobs = [t for _, t, *_ in SAMPLES] * repeats
            t0 = time.perf_counter()
            await asyncio.gather(*[guarded(t) for t in jobs])
            wall = time.perf_counter() - t0
            per_site = wall / len(jobs)
            print(f"  {c:>2} at once: {len(jobs)} calls in {wall:5.1f}s -> {per_site:5.2f} s/site, {60 / max(per_site, 1e-9):5.0f} sites/min")
            if best is None or per_site < best[1]:
                best = (c, per_site)
        out["best_concurrency"], out["best_per_site"] = best
    return out


def verdict(per_site: float) -> str:
    if per_site <= 0.6:
        return "ON TRACK for the LLM part (target 0.6 s/site, i.e. 100 sites in 60 s)"
    if per_site <= 1.0:
        return "BORDERLINE: try a smaller model, shorter text (llm.max_chars_per_site), or a stronger machine"
    return "TOO SLOW for the 60-second target: use a smaller model, a GPU, or cut the text sent to the model"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="Ollama model names (default: model in config.yaml)")
    ap.add_argument("--concurrency", nargs="+", type=int, default=[1, 4, 8])
    ap.add_argument("--repeats", type=int, default=2, help="times the 10 samples are repeated in the throughput test")
    ap.add_argument("--verbose", action="store_true", help="(kept for compatibility; every call is now printed)")
    ap.add_argument("--quick", action="store_true", help="only the 10 sequential calls, skip the throughput test")
    ap.add_argument("--mock", action="store_true", help="use the built-in fake LLM (checks the script, timings are meaningless)")
    args = ap.parse_args()

    if args.mock:
        os.environ["MRIS_LLM_MODE"] = "mock"
    from mris.config import get_config
    cfg = get_config()["llm"]
    models = args.models or [cfg["model"]]

    if cfg["mode"] == "openai":
        print(f"Hosted / OpenAI-compatible mode: {cfg['base_url']} (API key from MRIS_LLM_API_KEY). Model install check skipped.")
    elif cfg["mode"] == "ollama":
        try:
            have = installed_models(cfg["base_url"])
        except Exception as e:                               # noqa: BLE001
            sys.exit(f"Cannot reach Ollama at {cfg['base_url']} ({type(e).__name__}). Start the Ollama app or run: ollama serve")
        missing = [m for m in models if not model_available(m, have)]
        if missing:
            sys.exit("Model(s) not installed: " + ", ".join(missing) + "\n" +
                     "\n".join(f"  ollama pull {m}" for m in missing) + f"\nInstalled: {', '.join(have) or 'none'}")
    else:
        print("MOCK MODE: no model is called; timings are meaningless.")

    results = [asyncio.run(run_model(m, args.concurrency, args.repeats, args.verbose, args.quick)) for m in models]

    print("\n=== Summary ===")
    print(f"{'model':<22}{'median s':>9}{'best s/site':>13}{'at once':>9}{'valid JSON':>12}{'answers ok':>12}")
    for r in results:
        print(f"{r['model']:<22}{r['median']:>9.2f}{r['best_per_site']:>13.2f}{r['best_concurrency']:>9}"
              f"{len(SAMPLES) - r['invalid']:>8}/{len(SAMPLES)}{r['correct']:>8}/{r['checked']}")
    for r in results:
        print(f"- {r['model']}: {verdict(r['best_per_site'])}")
    print("\nNote: this tests only the LLM step on short made-up pages. Fetching real sites adds time (it runs in parallel),"
          " and real accuracy comes from the labeled benchmark.")


if __name__ == "__main__":
    main()
