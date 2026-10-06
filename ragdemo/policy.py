"""Second gate: authorized-use validation (policy gate).

[Division of labor among the three gates — this is what most sets this demo
apart from a "plain approval flow"]

  Gate 1  scopes.yaml        permission gate: is the tool on the whitelist?
                             overreach -> UNAUTHORIZED (no approval chance given)
  Gate 2  asset_policy.yaml  authorization gate: may this asset batch be used
                             this way? overreach -> BLOCKED_BY_POLICY
  Gate 3  risk + interrupt   risk gate: high-risk actions -> suspend and wait
                             for a human decision (approve/reject)

Key distinction — and the one that matters most here:
  - The approval gate is "let a human take a look"; the authorization gate is
    "this should not be done at all". Pushing an authorization question to
    human approval is a governance design flaw: the approver does not
    understand COPYING-MEDIA any better than the policy does, and "approved"
    does not mean "lawful".
  - Therefore the authorization rejection happens before the interrupt: the
    call is blocked outright, without even a chance to suspend.
    This is asserted by tests/test_assets.py::test_license_gate_blocks_before_approval.

[Why this is worth building] An approval flow alone does not answer "may we do
this at all". Turning a legal clause into an executable, assertable gate means
CI can check it on every commit instead of trusting a reviewer's memory.
"""

from __future__ import annotations

from typing import Any

from .assets import get_package

# Register "which tools must pass the authorization gate" — the policy only
# applies to tools with authorization semantics; everything else passes through.
POLICY_BOUND_TOOLS = {"extract_game_assets"}


def check_tool_policy(tool: str, params: dict[str, Any]) -> tuple[bool, str]:
    """Validate the authorization compliance of a tool call.

    Returns (allowed, reason). When allowed, the reason is an empty string so
    it can be persisted directly for auditing.
    """
    if tool not in POLICY_BOUND_TOOLS:
        return True, ""

    package_id = params.get("package")
    use = params.get("use", "reference")  # default to "reference only" (least privilege)

    if not package_id:
        return False, "missing package parameter (unregistered packages are denied by default)"

    pkg = get_package(package_id)
    if pkg is None:
        return False, (
            f"unregistered asset package {package_id!r}: denied by default "
            "(no authorization declared in asset_policy.yaml)"
        )

    ok, reason = pkg.check_use(use)
    if not ok:
        return False, f"{reason} | package={package_id}"
    return True, reason
