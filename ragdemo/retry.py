"""Bounded retry with exponential backoff, and an explicit failure taxonomy (v4c).

Why the taxonomy is the deliverable, not the retry loop
-------------------------------------------------------
Retrying is easy; deciding *what may be retried* is the actual engineering.
Retrying the wrong thing has a specific failure mode that is worse than not
retrying at all:

- **Retrying a deterministic refusal corrupts the audit log.** A policy denial
  is a *decision*. If the retry layer treats it as a transient failure and
  re-asks, the log records N refusals for one request, and an auditor cannot
  tell "denied once" from "denied three times". A denial is not a failure, so
  it is never a retry candidate.
- **Retrying a malformed response never helps.** If the body does not have the
  expected shape, the second call will produce the same shape.
- **Retrying an unknown exception amplifies it.** Retry is an *allow-list*
  decision: anything not explicitly known to be transient is not retried.

So the rule is: **transient by allow-list, deterministic by default.**

| Failure | Class | Retried | Why |
|---|---|---|---|
| connection refused / reset | transient | yes | the server may simply not be up yet |
| read / write / pool timeout | transient | yes | a slow generation can succeed on a second call |
| HTTP 408, 429, 5xx | transient | yes | server-side or rate-limit pressure |
| HTTP 4xx (400/401/403/404/422) | deterministic | no | the same request fails identically |
| response body missing its field | deterministic | no | retrying cannot change the schema |
| `PolicyRefusal` (a governance denial) | deterministic | no | it is a decision, not a failure |
| anything unrecognised | deterministic | no | never amplify an unknown fault |

The retry is bounded twice, because a cap on attempts alone is not a cap on
time: `max_attempts` bounds how many times we ask, and `max_total_wait` bounds
how long the caller may be made to wait. When the next backoff would exceed the
remaining budget, the retry is abandoned rather than overshooting it.

Every scheduled retry and every exhaustion is written to the same audit stream
the rest of the system uses — a silent retry is a hidden cost, and a retried
request that finally failed must be reconstructable after the fact.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from . import audit

TRANSIENT = "transient"
DETERMINISTIC = "deterministic"

# Status codes that mean "try again later" rather than "this request is wrong".
_TRANSIENT_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 507, 509, 521, 522, 524})

# Transport-level failures that are transient by nature. Note this is an
# allow-list: httpx raises other TransportError subclasses, and only the ones
# listed here are known to be worth another attempt.
_TRANSIENT_EXC = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


class NonRetryable(Exception):
    """Base class for failures that must never be retried.

    Raising this is how a caller tells the retry layer "I already decided".
    """


class PolicyRefusal(NonRetryable):
    """A governance denial.

    A policy decision is deterministic by construction: re-asking will produce
    the same answer, and recording it N times would make the audit log
    dishonest. Callers raise this instead of a generic error whenever a gate
    refused an action.
    """


class SchemaError(NonRetryable):
    """The response had the wrong shape (missing or malformed fields)."""


def classify(exc: BaseException) -> str:
    """Decide whether an exception may be retried.

    Returns `"transient"` or `"deterministic"`. Anything unrecognised is
    deterministic — see the module docstring for why the default matters.
    """
    if isinstance(exc, NonRetryable):
        return DETERMINISTIC
    if isinstance(exc, _TRANSIENT_EXC):
        return TRANSIENT

    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return TRANSIENT if (status in _TRANSIENT_STATUS or status >= 500) else DETERMINISTIC

    # Malformed payloads: retrying cannot change the schema.
    if isinstance(exc, (KeyError, ValueError, TypeError)):
        return DETERMINISTIC

    return DETERMINISTIC


def is_retryable(exc: BaseException) -> bool:
    """Convenience wrapper used by the tests and by callers that want a bool."""
    return classify(exc) == TRANSIENT


@dataclass(frozen=True)
class RetryPolicy:
    """Bounds for a retry loop. Both dimensions are capped: attempts and time."""

    max_attempts: int = 3          # total attempts, including the first one
    base_delay: float = 0.5        # seconds before the second attempt
    max_delay: float = 4.0         # ceiling for a single delay
    max_total_wait: float = 10.0   # ceiling for the sum of all delays
    jitter: bool = True            # spread retries; avoids a thundering herd

    def delay_for(self, retry_index: int) -> float:
        """Delay before retry number `retry_index` (1-based), exponential and capped."""
        raw = self.base_delay * (2 ** (retry_index - 1))
        delay = min(raw, self.max_delay)
        if not self.jitter:
            return delay
        # Full jitter: any point in [0, delay]. Keeps the mean wait bounded
        # while breaking up synchronised retries.
        return random.uniform(0.0, delay)

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < self.base_delay:
            raise ValueError("delays must satisfy 0 <= base_delay <= max_delay")
        if self.max_total_wait < 0:
            raise ValueError("max_total_wait must be >= 0")


def run(
    operation: Callable[[], Any],
    *,
    policy: RetryPolicy,
    label: str,
    sleep: Callable[[float], Any] = time.sleep,
) -> Any:
    """Run `operation`, retrying only failures the taxonomy allows.

    `sleep` is injectable so tests can record the schedule instead of waiting.
    """
    policy.validate()
    waited = 0.0

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except BaseException as exc:  # noqa: BLE001 -- classified below, not swallowed
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            kind = classify(exc)
            last_attempt = attempt >= policy.max_attempts

            if kind == DETERMINISTIC:
                # Not a failure to recover from: propagate immediately, with no
                # retry event. There is nothing to audit except the error.
                raise

            if last_attempt:
                audit.append_event(
                    "retry_exhausted",
                    {
                        "label": label,
                        "attempts": attempt,
                        "reason": "max_attempts",
                        "error_class": type(exc).__name__,
                        "waited": round(waited, 3),
                    },
                )
                raise

            delay = policy.delay_for(attempt)
            if waited + delay > policy.max_total_wait:
                # Abandon rather than overshoot: a cap on attempts is not a cap
                # on latency, and the caller's latency is what users feel.
                audit.append_event(
                    "retry_exhausted",
                    {
                        "label": label,
                        "attempts": attempt,
                        "reason": "max_total_wait",
                        "error_class": type(exc).__name__,
                        "waited": round(waited, 3),
                    },
                )
                raise

            audit.append_event(
                "retry_scheduled",
                {
                    "label": label,
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "error_class": type(exc).__name__,
                    "delay": round(delay, 3),
                },
            )
            sleep(delay)
            waited += delay

    raise AssertionError("unreachable")  # pragma: no cover
