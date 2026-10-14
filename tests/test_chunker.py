"""chunker tests: heading-based chunking, metadata, determinism."""

from ragdemo.chunker import chunk_markdown

SAMPLE = """# Agent 治理

引言文字。

## 人在回路

高风险动作必须人工批准。

## 最小权限

每工具只给最小权限。
"""


def test_chunks_follow_headings():
    chunks = chunk_markdown(SAMPLE, "sample.md")
    titles = [c.title for c in chunks]
    assert titles == ["Agent 治理", "人在回路", "最小权限"]


def test_chunk_metadata():
    chunks = chunk_markdown(SAMPLE, "sample.md")
    first = chunks[0]
    assert first.source == "sample.md"
    assert first.chunk_id.startswith("sample.md#")
    assert "引言文字" in first.text


def test_intro_without_heading():
    chunks = chunk_markdown("开头没有标题的说明文字。", "x.md")
    assert len(chunks) == 1
    assert chunks[0].title == "(intro)"


def test_snippet_truncates():
    long_text = "# 标题\n\n" + "很长" * 200
    chunks = chunk_markdown(long_text, "long.md")
    assert len(chunks[0].snippet) <= 121  # 120 characters + ellipsis
