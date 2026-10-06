"""rag-gov-demo showcase UI (v2 entry point).

Launch: streamlit run ui/streamlit_app.py   (or make ui, see the Makefile)
Features:
1. Q&A: POST {API}/ask, renders the answer / refusal reason + citation list;
2. Audit: GET {API}/audit, view recent events in the sidebar (direct evidence that
   refusals are audited too);
3. Governance preview (v3b): the approval card UI will live on this page — the
   approve/reject buttons for high-risk actions appear here.

Requires: the API service is already running (uvicorn api.main:app).
"""

import json

import httpx
import streamlit as st

st.set_page_config(page_title="rag-gov-demo", page_icon="🛡", layout="wide")

# ---- Sidebar: API address and health status ----
with st.sidebar:
    st.title("rag-gov-demo")
    st.caption("Governance-first agentic RAG reference implementation")
    api_base = st.text_input("API address", value="http://localhost:8000")

    if st.button("Check health"):
        try:
            health = httpx.get(f"{api_base}/health", timeout=5).json()
            st.success(f"Online · {health['chunks']} corpus chunks indexed")
        except Exception as exc:  # noqa: BLE001 — caught and surfaced in the UI, no crash
            st.error(f"API unreachable: {exc}")

    st.divider()
    st.subheader("Audit log (last 10 events)")
    if st.button("Refresh audit"):
        try:
            events = httpx.get(f"{api_base}/audit", timeout=5).json()["events"]
            st.json(json.dumps(events[-10:], ensure_ascii=False, indent=2))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Audit unreachable: {exc}")

# ---- Main area: Q&A ----
st.header("Corpus Q&A (citations + refusal)")
question = st.text_input(
    "Your question",
    placeholder="e.g. 高风险动作执行前需要什么流程？(ask in Chinese — the corpus is Chinese)",
)

if st.button("Ask", type="primary") and question:
    try:
        resp = httpx.post(f"{api_base}/ask", json={"question": question}, timeout=30)
        result = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Request failed: {exc}")
        st.stop()

    if result.get("refused"):
        st.warning(f"**Refused**: {result['refusal_reason']}")
        st.caption("Refusal is by design: with no grounding in the corpus, the system "
                   "declines to fabricate. This refusal has been written to the audit log.")
    else:
        st.markdown(result["answer"])
        mode = result.get("mode", "extractive")
        st.caption(f"Answer mode: {mode}" + (" (local LLM)" if mode == "llm" else " (extractive fallback)"))

        st.subheader("Citations")
        for c in result.get("citations", []):
            with st.expander(f"[{c['ref']}] {c['source']} · {c['title']}"):
                st.write(c["snippet"])

st.divider()
st.caption(
    "v3b preview: high-risk actions (export report / delete record) will pop up an "
    "approval card on this page; approve/reject decisions resume execution via "
    "LangGraph Command(resume=...)."
)
