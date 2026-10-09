"""Resilience tests (v4c): bounded retry, exponential backoff, failure taxonomy.

The claims this module defends:

1. Retry is bounded **twice** — by attempt count *and* by total wait.
2. Backoff is exponential and capped per delay.
3. Deterministic failures are never retried: 4xx, a malformed body, a policy
   refusal, and anything unrecognised. Retrying a denial would record one
   decision as several in the audit log.
4. Every scheduled retry and every exhaustion is observable in the audit stream.
5. With no failures, behaviour is unchanged (exactly one call).
"""

import json

import httpx
import pytest

from ragdemo import audit, llm, retry
from ragdemo.retry import PolicyRefusal, RetryPolicy, SchemaError, classify, is_retryable


# ---------------------------------------------------------------- helpers


def _no_jitter(**kwargs) -> RetryPolicy:
    """A policy whose schedule is reproducible (tests assert on exact delays)."""
    return RetryPolicy(jitter=False, **kwargs)


def _recorder(sleeps: list[float]):
    return sleeps.append


@pytest.fixture()
def audit_stream(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr("ragdemo.audit._ACTIVE_LOG", log)
    audit.set_log_path(log)
    yield log
    audit.set_log_path(None)


def _events(log) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- 1. taxonomy


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("refused"),
    httpx.ReadTimeout("slow"),
    httpx.WriteTimeout("slow"),
    httpx.PoolTimeout("busy"),
    httpx.RemoteProtocolError("reset"),
])
def test_transport_failures_are_retryable(exc):
    assert is_retryable(exc) is True


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://localhost/api/generate")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"HTTP {code}", request=request, response=response)


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_server_side_status_is_retryable(code):
    assert is_retryable(_status_error(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 409, 422])
def test_client_side_status_is_not_retryable(code):
    """A request that is wrong will be wrong again — retrying it only adds latency
    and noise."""
    assert is_retryable(_status_error(code)) is False


def test_malformed_body_is_not_retryable():
    assert is_retryable(SchemaError("missing field")) is False
    assert is_retryable(KeyError("response")) is False


def test_policy_refusal_is_never_retryable():
    """The important one: a denial is a decision, not a failure."""
    assert is_retryable(PolicyRefusal("blocked_by_policy")) is False
    assert classify(PolicyRefusal("x")) == "deterministic"


def test_unknown_exception_defaults_to_not_retryable():
    """Retry is an allow-list decision; never amplify an unrecognised fault."""
    assert is_retryable(RuntimeError("something new")) is False


# ---------------------------------------------------------------- 2. backoff shape


def test_backoff_is_exponential_and_capped():
    policy = _no_jitter(base_delay=0.5, max_delay=2.0)
    assert [policy.delay_for(i) for i in (1, 2, 3, 4, 5)] == [0.5, 1.0, 2.0, 2.0, 2.0]


def test_jitter_stays_within_the_cap():
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0, jitter=True)
    for _ in range(50):
        assert 0.0 <= policy.delay_for(3) <= 4.0


def test_policy_rejects_nonsense():
    for bad in ({"max_attempts": 0}, {"base_delay": -1.0}, {"max_total_wait": -1.0}):
        with pytest.raises(ValueError):
            _no_jitter(**bad).validate()


def test_transient_failure_is_retried_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ReadTimeout("slow generation")
        return "ok"

    sleeps: list[float] = []
    result = retry.run(flaky, policy=_no_jitter(max_attempts=3), label="t", sleep=_recorder(sleeps))
    assert result == "ok"
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_attempt_cap_bounds_the_number_of_calls():
    calls = []

    def always_down():
        calls.append(1)
        raise httpx.ConnectError("refused")

    sleeps: list[float] = []
    with pytest.raises(httpx.ConnectError):
        retry.run(always_down, policy=_no_jitter(max_attempts=4), label="t", sleep=_recorder(sleeps))
    assert len(calls) == 4, "max_attempts counts the first try"
    assert len(sleeps) == 3


def test_total_wait_cap_abandons_rather_than_overshoots():
    """A cap on attempts is not a cap on latency: when the next backoff would
    exceed the budget, stop instead of making the caller wait longer."""
    calls = []

    def always_down():
        calls.append(1)
        raise httpx.ConnectError("refused")

    sleeps: list[float] = []
    with pytest.raises(httpx.ConnectError):
        retry.run(
            always_down,
            policy=_no_jitter(max_attempts=10, base_delay=1.0, max_delay=8.0, max_total_wait=2.5),
            label="t",
            sleep=_recorder(sleeps),
        )
    # First retry sleeps 1.0 (budget 2.5). The second would need 2.0 more,
    # totalling 3.0 > 2.5, so it is abandoned *before* sleeping: the caller
    # never waits past the budget, and no further attempt is made.
    assert sleeps == [1.0]
    assert len(calls) == 2


def test_deterministic_failure_is_not_retried():
    calls = []

    def denied():
        calls.append(1)
        raise PolicyRefusal("blocked_by_policy")

    sleeps: list[float] = []
    with pytest.raises(PolicyRefusal):
        retry.run(denied, policy=_no_jitter(max_attempts=5), label="t", sleep=_recorder(sleeps))
    assert len(calls) == 1, "a denial must be asked exactly once"
    assert sleeps == []


# ---------------------------------------------------------------- 3. observability


def test_retries_and_exhaustion_are_audited(audit_stream):
    def always_down():
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        retry.run(always_down, policy=_no_jitter(max_attempts=3), label="ollama.generate:m",
                  sleep=lambda _d: None)

    events = _events(audit_stream)
    scheduled = [e for e in events if e["type"] == "retry_scheduled"]
    exhausted = [e for e in events if e["type"] == "retry_exhausted"]
    assert [e["attempt"] for e in scheduled] == [1, 2]
    assert [e["delay"] for e in scheduled] == [0.5, 1.0]
    assert len(exhausted) == 1
    assert exhausted[0]["reason"] == "max_attempts"
    assert exhausted[0]["label"] == "ollama.generate:m"


def test_budget_exhaustion_is_audited_with_its_reason(audit_stream):
    def always_down():
        raise httpx.ReadTimeout("slow")

    with pytest.raises(httpx.ReadTimeout):
        retry.run(
            always_down,
            policy=_no_jitter(max_attempts=10, base_delay=1.0, max_delay=8.0, max_total_wait=1.5),
            label="t",
            sleep=lambda _d: None,
        )
    exhausted = [e for e in _events(audit_stream) if e["type"] == "retry_exhausted"]
    assert exhausted and exhausted[0]["reason"] == "max_total_wait"


def test_deterministic_failure_writes_no_retry_event(audit_stream):
    """No retry happened, so no retry may be recorded — otherwise the log would
    imply the system kept asking after a refusal."""
    with pytest.raises(PolicyRefusal):
        retry.run(lambda: (_ for _ in ()).throw(PolicyRefusal("no")),
                  policy=_no_jitter(max_attempts=3), label="t", sleep=lambda _d: None)
    assert _events(audit_stream) == []


# ---------------------------------------------------------------- 4. llm wiring


def _patch_model(monkeypatch, model: str = "granite4.2:3b") -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"models": [{"name": model}]},
        })()
    )


def test_generate_retries_a_transient_failure(monkeypatch):
    """End-to-end: a warm local model that hiccups once should still answer."""
    _patch_model(monkeypatch)
    attempts = []

    def fake_post(url, json=None, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("cold start")
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"response": "Approval required [1]"},
        })()

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    answer = llm.generate("q", [], model="granite4.2:3b", policy=_no_jitter(max_attempts=3))
    assert answer == "Approval required [1]"
    assert len(attempts) == 2


def test_generate_does_not_retry_a_missing_model(monkeypatch):
    """404 = the model is not there. Asking twice will not make it appear."""
    _patch_model(monkeypatch)
    attempts = []

    def fake_post(url, json=None, **kwargs):
        attempts.append(1)
        raise _status_error(404)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        llm.generate("q", [], model="granite4.2:3b", policy=_no_jitter(max_attempts=5))
    assert len(attempts) == 1


def test_generate_does_not_retry_a_malformed_body(monkeypatch):
    _patch_model(monkeypatch)
    attempts = []

    def fake_post(url, json=None, **kwargs):
        attempts.append(1)
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"unexpected": "shape"},
        })()

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(SchemaError):
        llm.generate("q", [], model="granite4.2:3b", policy=_no_jitter(max_attempts=5))
    assert len(attempts) == 1


def test_generate_makes_exactly_one_call_when_healthy(monkeypatch):
    """Existing behaviour with no failures must not change: no retry, no event."""
    _patch_model(monkeypatch)
    attempts = []

    def fake_post(url, json=None, **kwargs):
        attempts.append(1)
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"response": "ok [1]"},
        })()

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate("q", [], model="granite4.2:3b") == "ok [1]"
    assert len(attempts) == 1


def test_default_policy_is_configurable(monkeypatch):
    """The bounds come from configuration, so a slow local model and a fast
    remote endpoint can be tuned without touching code."""
    monkeypatch.setattr(llm, "LLM_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(llm, "LLM_BACKOFF_BASE", 0.25)
    monkeypatch.setattr(llm, "LLM_MAX_TOTAL_WAIT", 30.0)
    policy = llm.default_policy()
    assert policy.max_attempts == 5
    assert policy.base_delay == 0.25
    assert policy.max_total_wait == 30.0
