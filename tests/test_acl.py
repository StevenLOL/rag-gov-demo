"""Permission-aware retrieval tests (v4d).

The four claims this module exists to defend:

1. A chunk inherits its ACL from the document it was cut from.
2. A principal that may not read a chunk never receives it — and the filter
   runs before ranking, so a denied chunk does not consume a top-k slot.
3. A denied chunk never appears in the audit stream (only the *count* of
   filtered-out chunks does).
4. The refusal path does not disclose that restricted material exists.

Claim 2 is the one that matters: post-filtering would still "not return" the
chunk while quietly destroying recall, which is why one test asserts the
slot-preserving behaviour directly rather than just checking absence.
"""

import json

import pytest

from ragdemo import acl, audit
from ragdemo.acl import Principal
from ragdemo.chunker import Chunk, chunk_markdown, load_corpus, parse_acl, split_front_matter
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import Bm25Backend, Hit, build_index
from ragdemo.tools_impl import impl_search_docs

# ---------------------------------------------------------------- fixtures


def _chunk(cid: str, title: str, text: str, allow=("*",), sensitivity: str = "internal") -> Chunk:
    return Chunk(
        chunk_id=cid, source="synthetic.md", title=title, text=text,
        acl=tuple(allow), sensitivity=sensitivity,
    )


def _staff() -> Principal:
    """An ordinary member of staff: no special group, internal clearance."""
    return Principal(id="bob@example.com", groups=("all-staff",), clearance="internal")


def _sre() -> Principal:
    return Principal(id="carol@example.com", groups=("sre",), clearance="confidential")


@pytest.fixture()
def audit_stream(tmp_path, monkeypatch):
    """Redirect the process-wide audit stream to a temp file for the test."""
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr("ragdemo.audit._ACTIVE_LOG", log)
    audit.set_log_path(log)
    yield log
    audit.set_log_path(None)


# ---------------------------------------------------------------- 1. inheritance


def test_front_matter_is_stripped_and_not_retrievable():
    """The declaration must never become retrievable text or an embedding input."""
    declaration, body = split_front_matter('---\nacl: ["group:sre"]\nsensitivity: confidential\n---\n\n# 标题\n\n正文')
    assert declaration == {"acl": ["group:sre"], "sensitivity": "confidential"}
    assert body.lstrip().startswith("# 标题")
    assert "acl" not in body, "the declaration must not leak into retrievable text"


def test_every_chunk_inherits_the_document_declaration():
    chunks = chunk_markdown("# A\n\ntext A\n\n# B\n\ntext B", "doc.md", acl=["group:sre"], sensitivity="confidential")
    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.acl == ("group:sre",)
        assert chunk.sensitivity == "confidential"


def test_real_corpus_declares_its_own_acl():
    """The shipped corpus is not uniformly readable -- otherwise the filter
    could never be observed doing anything."""
    chunks = load_corpus(CORPUS_DIR)
    by_source = {c.source for c in chunks}
    assert "incident_response.md" in by_source

    restricted = [c for c in chunks if c.source == "incident_response.md"]
    assert restricted, "corpus must contain the restricted document"
    assert all("group:security" in c.acl for c in restricted)
    assert all(c.sensitivity == "confidential" for c in restricted)

    public = [c for c in chunks if c.source == "gov_ai_usage_rules.md"]
    assert all(c.acl == ("*",) for c in public)


def test_unknown_sensitivity_fails_at_ingestion():
    """A typo in a classification must raise, not silently mean 'everybody'."""
    with pytest.raises(ValueError):
        parse_acl({"acl": ["*"], "sensitivity": "top-secret"})
    with pytest.raises(ValueError):
        Principal(id="x", clearance="ultra")


def test_undeclared_document_inherits_the_configured_default(tmp_path):
    doc = tmp_path / "plain.md"
    doc.write_text("# 未分类文档\n\n内容", encoding="utf-8")
    chunks = load_corpus(tmp_path, default_acl="group:all-staff", default_sensitivity="internal")
    assert chunks[0].acl == ("group:all-staff",)
    assert acl.chunk_visible(chunks[0], _staff())
    assert not acl.chunk_visible(chunks[0], Principal(id="outsider@example.com", groups=()))


# ---------------------------------------------------------------- 2. the filter


def test_empty_acl_denies_everybody():
    """Deny by default: an unclassified allowance is not an open door."""
    chunk = _chunk("c#0", "未分类", "内容", allow=())
    assert not acl.chunk_visible(chunk, _staff())
    assert not acl.chunk_visible(chunk, _sre())
    assert not acl.chunk_visible(chunk, Principal(id="root", groups=("sre", "admin"), clearance="restricted"))


def test_clearance_ceiling_holds_even_for_a_group_member():
    """Group membership and clearance are independent conditions."""
    chunk = _chunk("c#0", "运维手册", "部署细节", allow=("group:sre",), sensitivity="confidential")
    assert not acl.chunk_visible(chunk, Principal(id="dave@example.com", groups=("sre",), clearance="internal"))
    assert acl.chunk_visible(chunk, _sre())


def test_unauthorised_principal_never_receives_the_chunk():
    index = build_index(load_corpus(CORPUS_DIR))
    hits = index.search("事故分级与上报", top_k=5, principal=_staff())
    assert hits, "the corpus should still answer something"
    assert all(h.chunk.source != "incident_response.md" for h in hits)

    unrestricted = index.search("事故分级与上报", top_k=5)
    assert any(h.chunk.source == "incident_response.md" for h in unrestricted), (
        "guard: without a principal the chunk is findable, otherwise this test proves nothing"
    )


def test_authorised_principal_receives_it():
    index = build_index(load_corpus(CORPUS_DIR))
    hits = index.search("事故分级与上报", top_k=5, principal=_sre())
    assert any(h.chunk.source == "incident_response.md" for h in hits)


def test_prefilter_does_not_consume_a_topk_slot():
    """The recall argument for pre-filtering.

    The denied chunk is the single best lexical match. Post-filtering would
    take top_k=1, drop it, and return nothing; pre-filtering must surface the
    next best *authorised* chunk instead.
    """
    denied = _chunk("d#0", "事故分级", "事故分级 事故分级 事故分级",
                    allow=("group:sre",), sensitivity="confidential")
    allowed = _chunk("a#0", "数据分级", "数据分级 事故", allow=("*",))
    index = Bm25Backend(chunks=[denied, allowed])

    assert index.search("事故分级", top_k=1)[0].chunk.chunk_id == "d#0", (
        "guard: the denied chunk really is the top lexical match"
    )
    hits = index.search("事故分级", top_k=1, principal=_staff())
    assert [h.chunk.chunk_id for h in hits] == ["a#0"]


def test_a_principal_who_may_read_nothing_gets_nothing():
    index = build_index(load_corpus(CORPUS_DIR))
    hits = index.search("数据分级", top_k=5, principal=Principal(id="anon", groups=(), clearance="public"))
    assert hits == []


def test_no_principal_means_no_filter():
    """The raw backend stays usable for whole-corpus evaluation runs."""
    index = build_index(load_corpus(CORPUS_DIR))
    assert len(index.search("数据分级", top_k=5)) >= len(index.search("数据分级", top_k=5, principal=_sre()))


def test_hybrid_fusion_is_filtered_too():
    """The filter is enforced on the fused result, not only per channel."""

    class _Fake:
        def __init__(self, chunks):
            self.chunks = chunks

        def search(self, query, top_k=5, principal=None):
            hits = [Hit(chunk=c, score=10.0 - i) for i, c in enumerate(self.chunks[:top_k])]
            return acl.filter_hits(hits, principal)

    from ragdemo.vector import HybridBackend

    denied = _chunk("d#0", "事故", "事故分级", allow=("group:sre",), sensitivity="confidential")
    allowed = _chunk("a#0", "数据", "数据分级", allow=("*",))
    backend = HybridBackend(bm25=_Fake([denied, allowed]), vector=_Fake([denied, allowed]))
    assert [h.chunk.chunk_id for h in backend.search("分级", top_k=2, principal=_staff())] == ["a#0"]


# ---------------------------------------------------------------- 3. audit


def test_denied_chunk_never_enters_the_audit_stream(audit_stream):
    """What the retriever did is auditable; what it withheld is only counted."""
    out = impl_search_docs({
        "query": "事故分级与上报",
        "top_k": 5,
        "principal": {"id": "bob@example.com", "groups": ["all-staff"], "clearance": "internal"},
    })

    assert all(h["source"] != "incident_response.md" for h in out["hits"])

    raw = audit_stream.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    retrievals = [e for e in events if e["type"] == "retrieval"]
    assert retrievals, "the retrieval layer must write its own audit event"

    event = retrievals[-1]
    assert event["principal"]["id"] == "bob@example.com"
    assert event["filtered_out"] > 0, "something must have been withheld for this guard to mean anything"
    assert not any("incident_response" in chunk_id for chunk_id in event["returned"])

    # The identifiers of denied chunks are never written -- anywhere.
    assert "incident_response" not in raw
    assert "违规与事故响应" not in raw   # the restricted document's title


def test_audit_records_the_principal_who_asked(audit_stream):
    impl_search_docs({"query": "数据分级", "top_k": 3, "principal": {"id": "carol@example.com", "groups": ["sre"], "clearance": "confidential"}})
    events = [json.loads(line) for line in audit_stream.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = [e for e in events if e["type"] == "retrieval"][-1]
    assert event["principal"] == {"id": "carol@example.com", "groups": ["sre"], "clearance": "confidential"}


# ---------------------------------------------------------------- 4. refusal wording


def test_refusal_does_not_disclose_that_restricted_content_exists():
    """A denial and a miss must read identically -- otherwise the refusal
    itself becomes an existence oracle for restricted material."""
    from ragdemo.citation import answer_question

    index = build_index(load_corpus(CORPUS_DIR))

    # "docker compose" exists only in the SRE-restricted document, so an
    # ordinary member of staff gets an empty result set -- and the refusal they
    # see must look exactly like "the corpus has nothing on this".
    result = answer_question("docker compose", index, principal=_staff())
    assert result.refused
    assert "deploy_operations" not in result.refusal_reason
    assert "Docker" not in result.refusal_reason
    assert result.citations == []

    guard = answer_question("docker compose", index, principal=_sre())
    assert not guard.refused, "guard: cleared staff are answered, so the refusal above is an ACL effect"
