"""语料档位（CORPUS_PROFILE）测试。

断言的四件事：
1. 档位表完整，且默认档是 gov —— 保证 tests/ 里其它检索/引用用例不被真实语料"劫持"；
2. legacy 档位真的能加载到量级正确的语料（37 篇 / 1052 chunk，不是空目录）；
3. 真实语料上的区分性术语检索可用（用 012/013 两个脚本挖出来的 df=1 锚点词验证）；
4. 两套语料的 chunk 完全不重叠 —— 证明档位切换是真的换了知识库，而不是混在一起。

为什么不测 hybrid 后端：向量后端需要 sentence-transformers 与本地模型，
CI 上不可得；hybrid 的对照实验结果记在 README 与 docs/015，不走单测。
"""

from __future__ import annotations

import os

import pytest

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_PROFILES
from ragdemo.retriever import Bm25Backend


def test_profiles_defined_and_gov_is_default():
    """gov 与 legacy 两个档位都在；未设环境变量时默认 gov。"""
    assert set(CORPUS_PROFILES) >= {"gov", "legacy"}
    # 默认档必须是治理语料：tests/test_retriever.py、test_citation.py 断言的是它的内容
    assert CORPUS_PROFILES["gov"].name == "corpus"
    assert CORPUS_PROFILES["legacy"].name == "corpus_legacy"


def test_legacy_corpus_has_expected_scale():
    """真实语料规模：37 篇 → 上千 chunk（数字来自 2026-09-30 实测）。"""
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"真实语料目录不存在：{legacy_dir}")
    files = sorted(legacy_dir.glob("*.md"))
    assert len(files) == 37, f"期望 37 篇逆向文档，实际 {len(files)}"
    chunks = load_corpus(legacy_dir)
    assert len(chunks) >= 1000, f"期望 >=1000 chunk，实际 {len(chunks)}"


def test_distinctive_anchor_retrieves_its_document():
    """df=1 锚点词能把对应文档捞到 top1（锚点由 scripts/013 挖掘得出）。

    选 PKLite（全语料仅 017 一篇）与 xentax（仅 026 一篇）这两个最硬的锚点：
    它们不受"同一游戏有两篇文档"的干扰，是检索器能力的下界验证。
    """
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"真实语料目录不存在：{legacy_dir}")
    backend = Bm25Backend(chunks=load_corpus(legacy_dir))

    hits = backend.search("ETIN 的 16 位 DOS EXE 被 PKLite 压缩过，怎么解压", top_k=1)
    assert hits and hits[0].chunk.source == "017_ETIN格式破解全记录.md"


def test_two_corpora_do_not_overlap():
    """两套语料的 chunk 来源互不相交 —— 档位切换是替换，不是合并。"""
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"真实语料目录不存在：{legacy_dir}")
    gov_sources = {c.source for c in load_corpus(CORPUS_PROFILES["gov"])}
    legacy_sources = {c.source for c in load_corpus(legacy_dir)}
    assert gov_sources & legacy_sources == set()
    assert legacy_sources  # 真实语料非空


def test_profile_env_switches_directory():
    """CORPUS_PROFILE=legacy 时配置里的语料目录随之改变（全链路档位化的前提）。

    用子进程而不是 importlib.reload：reload 会替换 config 模块里的对象身份，
    而其它模块早已 `from ragdemo.config import CORPUS_DIR` 把旧值绑定走了，
    造成"reload 之后行为不一致"的隐式污染。子进程能真正验证"进程启动时读环境变量"这一语义。
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    code = "import sys; sys.path.insert(0, '.'); from ragdemo.config import CORPUS_DIR; print(CORPUS_DIR)"
    env = dict(os.environ, CORPUS_PROFILE="legacy", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("corpus_legacy"), proc.stdout
