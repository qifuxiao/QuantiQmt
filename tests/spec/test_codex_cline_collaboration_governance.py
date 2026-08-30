"""Governance tests for the Codex-Cline collaboration protocol (TASK-056)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


# ── Role boundaries ─────────────────────────────────────────────────────


def test_agents_define_four_role_boundaries() -> None:
    """AGENTS.md must explicitly define Codex, Cline, Review, and Human roles
    with their Collaboration artifacts and PR types."""
    agents = _text("AGENTS.md")
    assert "Codex" in agents
    assert "Cline" in agents
    assert "Implementation Packet" in agents
    assert "Repair Packet" in agents
    assert "Implementation PR" in agents
    assert "Closeout PR" in agents
    assert "APPROVE" in agents
    assert "REQUEST_CHANGES" in agents
    assert "人类" in agents


def test_team_workflow_defines_three_artifacts_and_two_pr_types() -> None:
    """Team workflow must define Implementation Packet, Implementation Report,
    Repair Packet, and the two-PR lifecycle (Implementation PR + Closeout PR)."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "Implementation Packet" in wf
    assert "Implementation Report" in wf
    assert "Repair Packet" in wf
    assert "Implementation PR" in wf
    assert "Closeout PR" in wf


# ── Cline handoff fail-closed gates ─────────────────────────────────────


def test_cline_handoff_plan_blocked_on_dirty_base_or_gap() -> None:
    """Cline handoff must define PLAN_BLOCKED on dirty worktree, base mismatch,
    or design gap."""
    handoff = _text(".clinerules/10-codex-handoff.md")
    assert "PLAN_BLOCKED" in handoff
    lower = handoff.lower()
    assert "dirty" in lower or "clean" in lower
    assert "base" in lower


def test_cline_handoff_prohibits_self_approve_merge_closeout() -> None:
    """Cline must be prohibited from self-approve, merge, closeout, and
    direct push to main."""
    handoff = _text(".clinerules/10-codex-handoff.md")
    lower = handoff.lower()
    assert "self-approve" in lower
    assert "merge" in lower
    assert "closeout" in lower
    assert "push" in lower
    assert "main" in lower


def test_cline_adapter_requires_codex_plan_and_handoff() -> None:
    """Cline adapter must require reading Codex Plan and reference the
    handoff rules and Implementation Report."""
    adapter = _text("ai/adapters/cline.md")
    assert "Codex Plan" in adapter
    assert "10-codex-handoff" in adapter
    assert "Implementation Report" in adapter


# ── Planning Base vs Implementation Base ────────────────────────────────


def test_template_distinguishes_planning_and_implementation_base() -> None:
    """Task template must have separate Planning Base SHA and
    Implementation Base SHA fields."""
    template = _text("tasks/templates/task-template.md")
    assert "Planning Base SHA" in template
    assert "Implementation Base SHA" in template


def test_task_defines_ancestor_relationship() -> None:
    """The active task must document that Planning Base is an ancestor of
    Implementation Base."""
    task = _text("tasks/active/TASK-056-codex-cline-collaboration.md")
    assert "ancestor" in task.lower() or "祖先" in task


# ── Review binding to exact Head ────────────────────────────────────────


def test_review_bound_to_exact_head_with_limited_verdicts() -> None:
    """Review must be bound to exact Head and verdicts limited to
    APPROVE, REQUEST_CHANGES, BLOCKED."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "Head" in wf
    assert "APPROVE" in wf
    assert "REQUEST_CHANGES" in wf
    assert "BLOCKED" in wf


def test_head_change_invalidates_review() -> None:
    """After Head changes, the old review must be invalidated and a
    re-review is required."""
    wf = _text("ai/workflows/team-collaboration.md")
    lower = wf.lower()
    assert "invalidat" in lower or "失效" in lower
    assert "re-review" in lower or "重新" in lower


# ── Task template Codex Plan fields ─────────────────────────────────────


def test_task_template_contains_all_codex_plan_fields() -> None:
    """Task template must include Plan version, both Base SHAs, Design,
    File-level change plan, Acceptance-to-test mapping, failure design,
    and PLAN_BLOCKED conditions."""
    template = _text("tasks/templates/task-template.md")
    assert "Codex Implementation Plan" in template
    assert "Plan version" in template
    assert "Planning Base SHA" in template
    assert "Implementation Base SHA" in template
    assert "Design" in template
    assert "File-level change plan" in template
    assert "Acceptance-to-test mapping" in template
    assert "failure" in template.lower()
    assert "PLAN_BLOCKED" in template


# ── Implementation Report required fields ───────────────────────────────


def test_implementation_report_contains_all_required_fields() -> None:
    """Cline handoff must define all required Implementation Report fields:
    Base/Head SHA, branch/PR, changed files, acceptance, exit codes,
    unverified scope, risks, deviations, and path audit."""
    handoff = _text(".clinerules/10-codex-handoff.md")
    assert "Implementation Report" in handoff
    lower = handoff.lower()
    assert "base" in lower
    assert "head" in lower
    assert "branch" in lower
    assert "pr" in lower
    assert "changed" in lower
    assert "acceptance" in lower
    assert "exit" in lower
    assert "unverified" in lower or "未验证" in handoff
    assert "risk" in lower
    assert "deviation" in lower
    assert "allowed" in lower


# ── Path audit in workflow ──────────────────────────────────────────────


def test_workflow_requires_path_audit() -> None:
    """Team workflow must require an explicit path audit on the
    implementation diff."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "path audit" in wf.lower() or "路径审计" in wf


# ── .clinerules must not copy business contracts ────────────────────────


def test_clinerules_reference_not_copy_business_contracts() -> None:
    """No .clinerules file may embed specific business event, command,
    DTO, error-code, or state-machine names. Each file must reference
    the authority chain (AGENTS or spec)."""
    for path in sorted((ROOT / ".clinerules").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        assert "broker.order_reported" not in content
        assert "order_status_changed" not in content
        assert "state_changed" not in content
        assert "order_registered" not in content
        assert "order_evaluated" not in content
        assert "AGENTS" in content or "spec" in content


# ── Repair v1: .clinerules must be reference-only (no business terms) ──


BUSINESS_TERMS = ("xtquant", "OrderIntent", "Kill Switch", "OMS", "UNKNOWN")


def test_clinerules_no_business_terms() -> None:
    """.clinerules/*.md must not contain trading/business architecture terms."""
    for path in sorted((ROOT / ".clinerules").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for term in BUSINESS_TERMS:
            assert term not in content, (
                f"{path.name} contains business term {term!r}; refer to AGENTS.md / spec/ instead"
            )


# ── Repair v1: Review must use three-dot diff ─────────────────────────


def test_review_uses_three_dot_diff() -> None:
    """Review instructions must use three-dot (Base...Head), not two-dot."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "..." in wf or "Base...Head" in wf, "must use three-dot diff"
    # Two-dot for diff review is rejected (main..branch is two-dot)
    assert "origin/main..origin/" not in wf, "two-dot diff is forbidden"


# ── Repair v1: Review must have exactly three verdicts ─────────────────


def test_review_has_exactly_three_verdicts() -> None:
    """Review template must list APPROVE, REQUEST_CHANGES, and BLOCKED.
    Must NOT use two-verdict alternatives."""
    wf = _text("ai/workflows/team-collaboration.md")
    # The Review template section must contain all three
    assert "APPROVE" in wf
    assert "REQUEST_CHANGES" in wf
    assert "BLOCKED" in wf
    # Must not have old two-verdict pattern: "APPROVE 或 REQUEST_CHANGES" without BLOCKED
    assert "APPROVE 或 REQUEST_CHANGES\n" not in wf, (
        "two-verdict pattern (without BLOCKED) is rejected"
    )


# ── Repair v1: Review must require PR OPEN and exact Head ─────────────


def test_review_requires_pr_open_and_head_verification() -> None:
    """Review must require PR OPEN and verify beginning/end Head SHA."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "OPEN" in wf, "Review must require PR status OPEN"
    assert "Beginning Head" in wf or "Beginning head" in wf, "Review must record Beginning Head SHA"
    assert "Ending Head" in wf or "Ending head" in wf, "Review must record Ending Head SHA"


# ── Repair v1: Human-only authorization ───────────────────────────────


def test_human_only_authorization_explicit() -> None:
    """Workflow must explicitly state that activation, merge, closeout are
    human-only and Reviewer cannot authorize closeout."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "人类独占" in wf or "human-only" in wf.lower(), (
        "must explicitly state human-only authorization"
    )
    assert "不能授权 closeout" in wf or "cannot authorize closeout" in wf.lower(), (
        "must state Reviewer cannot authorize closeout"
    )


# ── Repair v1: AGENTS.md must also state three verdicts ───────────────


def test_agents_md_has_three_verdicts() -> None:
    """AGENTS.md role section must list all three review verdicts."""
    agents = _text("AGENTS.md")
    assert "APPROVE" in agents
    assert "REQUEST_CHANGES" in agents
    assert "BLOCKED" in agents


# ── ADDENDUM-1: Implementation Base from Handoff Record only ──────────


def test_cline_rules_base_from_handoff_not_origin_main() -> None:
    """.clinerules must state Implementation Base comes from Handoff Record,
    not from origin/main or the task."""
    rules = _text(".clinerules/10-codex-handoff.md")
    assert "Handoff Record" in rules, (
        "Cline rules must reference the Handoff Record as Base authority"
    )
    assert "must not" in rules or "不得" in rules, (
        "Cline rules must prohibit Cline from deriving Base"
    )
    # Must NOT say Cline records origin/main as the Implementation Base
    assert "Cline records\ngit rev-parse origin/main" not in rules, (
        "Cline rules must not let Cline derive Implementation Base from origin/main"
    )


def test_cline_adapter_base_from_handoff() -> None:
    """ai/adapters/cline.md must state Implementation Base comes from Handoff Record."""
    adapter = _text("ai/adapters/cline.md")
    assert "Handoff Record" in adapter, (
        "Cline adapter must reference the Handoff Record for Implementation Base"
    )
    assert "must not derive" in adapter or "must not" in adapter, (
        "Cline adapter must prohibit deriving Base from origin/main"
    )


def test_task_template_base_from_handoff() -> None:
    """tasks/templates/task-template.md must state Implementation Base is
    provided by Codex in the Handoff Record, not derived by Cline."""
    template = _text("tasks/templates/task-template.md")
    assert "Handoff Record" in template, (
        "Task template must reference the Handoff Record for Implementation Base"
    )
    assert "Cline records" not in template or "git rev-parse origin/main" not in template, (
        "Task template must not let Cline derive Base from origin/main"
    )


# ── ADDENDUM-1: Closeout is human-only (no "or Review") ───────────────


def test_closeout_human_only_no_reviewer() -> None:
    """.clinerules must state closeout is human-only, not 'human or Review'."""
    rules = _text(".clinerules/10-codex-handoff.md")
    # Must NOT contain the old ambiguous wording
    assert "human or independent Review" not in rules, (
        "closeout must not be 'human or independent Review decision'"
    )
    # Must contain human-only language
    assert "human-only" in rules or "human only" in rules.lower(), (
        "closeout must be explicitly human-only"
    )


def test_team_collab_review_binds_github_facts() -> None:
    """Review template must bind to GitHub PR Base and Head explicitly."""
    wf = _text("ai/workflows/team-collaboration.md")
    assert "baseRefOid" in wf or "PR Base" in wf, "Review must read GitHub PR Base SHA"
    assert "headRefOid" in wf or "Beginning Head" in wf, "Review must read GitHub PR Head SHA"
    assert "--pr-base" in wf, "Review must pass --pr-base to validator"
