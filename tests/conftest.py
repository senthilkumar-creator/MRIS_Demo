"""Offline integration tests use loopback mock servers and the mock LLM."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("MRIS_LLM_MODE", "mock")
os.environ.setdefault("MRIS_ALLOW_PRIVATE_NETWORKS", "1")
os.environ.setdefault("MRIS_SKIP_DNS_CHECK", "1")
os.environ.setdefault("MRIS_RESPECT_ROBOTS", "0")
os.environ.setdefault("MRIS_ENABLE_DYNAMIC_FALLBACK", "1")
