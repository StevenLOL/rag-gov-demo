"""rag-gov-demo 演示 UI（v2 入口）。

启动：streamlit run ui/streamlit_app.py   （或 make ui，见 Makefile）
功能：
1. 问答：POST {API}/ask，渲染答案/拒答原因 + 引用列表；
2. 审计：GET {API}/audit，侧栏查看最近事件（拒答也落审计的直观证据）；
3. 治理预告（v3b）：审批卡 UI 将挂在本页——高风险动作的 approve/reject 按钮在此出现。

依赖：API 服务已启动（uvicorn api.main:app）。
"""

import json

import httpx
import streamlit as st

st.set_page_config(page_title="rag-gov-demo", page_icon="🛡", layout="wide")

# ---- 侧栏：API 地址与健康状态 ----
with st.sidebar:
    st.title("rag-gov-demo")
    st.caption("治理优先的 agentic RAG 参考实现")
    api_base = st.text_input("API 地址", value="http://localhost:8000")

    if st.button("检查健康状态"):
        try:
            health = httpx.get(f"{api_base}/health", timeout=5).json()
            st.success(f"在线 · 语料 {health['chunks']} 个片段")
        except Exception as exc:  # noqa: BLE001 —— UI 层捕获并提示，不崩
            st.error(f"API 不可达：{exc}")

    st.divider()
    st.subheader("审计日志（最近 10 条）")
    if st.button("刷新审计"):
        try:
            events = httpx.get(f"{api_base}/audit", timeout=5).json()["events"]
            st.json(json.dumps(events[-10:], ensure_ascii=False, indent=2))
        except Exception as exc:  # noqa: BLE001
            st.error(f"审计不可达：{exc}")

# ---- 主区：问答 ----
st.header("资料问答（引用 + 拒答）")
question = st.text_input(
    "你的问题",
    placeholder="例：高风险动作执行前需要什么流程？",
)

if st.button("提问", type="primary") and question:
    try:
        resp = httpx.post(f"{api_base}/ask", json={"question": question}, timeout=30)
        result = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"请求失败：{exc}")
        st.stop()

    if result.get("refused"):
        st.warning(f"**已拒答**：{result['refusal_reason']}")
        st.caption("拒答是设计行为：资料中无依据时，系统拒绝编造。本次拒答已写入审计日志。")
    else:
        st.markdown(result["answer"])
        mode = result.get("mode", "extractive")
        st.caption(f"生成模式：{mode}" + ("（本地 LLM）" if mode == "llm" else "（抽取式降级）"))

        st.subheader("引用")
        for c in result.get("citations", []):
            with st.expander(f"[{c['ref']}] {c['source']} · {c['title']}"):
                st.write(c["snippet"])

st.divider()
st.caption(
    "v3b 预告：高风险动作（导出报告/删除记录）将在此页面弹出审批卡，"
    "approve/reject 决定经 LangGraph Command(resume=...) 恢复执行。"
)
