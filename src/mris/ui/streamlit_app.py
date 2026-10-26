"""Optional Streamlit UI (build LAST). Owner: Member 2.

Run the API first (uvicorn mris.api:app --app-dir src), then:
    streamlit run src/mris/ui/streamlit_app.py
"""
import io
import pandas as pd
import requests
import streamlit as st

API = st.sidebar.text_input("API address", "http://localhost:8000")
st.title("MRIS - Merchant Risk Intelligence System")
st.caption("RiskLens AI")

text = st.text_area("Paste URLs (one per line)")
upload = st.file_uploader("...or upload a CSV with a 'url' column", type="csv")

urls = [u.strip() for u in text.splitlines() if u.strip()]
if upload is not None:
    urls += pd.read_csv(upload)["url"].dropna().tolist()

if st.button("Assess merchants", disabled=not urls):
    with st.spinner(f"Assessing {len(urls)} sites..."):
        r = requests.post(f"{API}/assess", json={"urls": urls}, timeout=3600)
    if r.ok:
        data = r.json()
        st.success(f"{data['count']} sites in {data['elapsed_seconds']} seconds")
        rows = [{"url": x["url"], "decision": x["decision"], "industry": x["industry"], "mcc": x["mcc"],
                 "reasons": " | ".join(x["reasons"])} for x in data["results"]]
        df = pd.DataFrame(rows)
        only_review = st.checkbox("Show only HUMAN_REVIEW")
        st.dataframe(df[df["decision"] == "HUMAN_REVIEW"] if only_review else df, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False), "mris_results.csv", "text/csv")
        st.download_button("Download JSON", r.text, "mris_results.json", "application/json")
    else:
        st.error(f"API error {r.status_code}: {r.text[:300]}")
