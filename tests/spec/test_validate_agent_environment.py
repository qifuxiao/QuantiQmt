"""Formal live GitHub environment-evidence validator tests for TASK-057 Plan v3."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema.validators import Draft202012Validator
from scripts import validate_agent_environment as validator
from scripts.validate_specs import extract_front_matter

ROOT = Path(__file__).resolve().parents[2]
TASK_PATH = ROOT / "tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
HANDOFF_PATH = ROOT / "ai/handoffs/TASK-057-REPAIR-v3.yaml"
ASSIGNMENT_SCHEMA_PATH = ROOT / "ai/schemas/agent-assignment.schema.yaml"
EVIDENCE_SCHEMA_PATH = ROOT / "ai/schemas/agent-environment-evidence.schema.yaml"
REPOSITORY = "qifuxiao/QuantiQmt"
PR = 100
PLAN_V3_HEAD = "86b5a75585f646c7faf667645694776ac4273c20"
BRANCH = "codex/task-057-implementation"
BASE = "7be471949dbce8278b5ce7681384ef987b0fbc86"
STARTING_HEAD = "03d5c425143c2101a82ccd64d752c770886117d6"
HEAD = "f" * 40
ASSIGNMENT_COMMENT_ID = 5505098259
EVIDENCE_COMMENT_ID = 5509999999
ASSIGNMENT_URL = "https://github.com/qifuxiao/QuantiQmt/pull/100#issuecomment-5505098259"
EVIDENCE_URL = "https://github.com/qifuxiao/QuantiQmt/pull/100#issuecomment-5509999999"


def _task() -> dict[str, Any]:
    return copy.deepcopy(extract_front_matter(TASK_PATH))


def _handoff() -> dict[str, Any]:
    value = yaml.safe_load(HANDOFF_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def _canonical_body(sentinel: str, document: dict[str, Any]) -> str:
    return f"{sentinel}\n```json\n{json.dumps(document, indent=2)}\n```"


def _assignment_document() -> dict[str, Any]:
    producer = {
        "agent_id": "task-057-plan-v3-codex-windows-1",
        "github_login": "qfxyyy",
        "role": "Implementation Agent",
        "tool": "Codex",
        "os": "Windows",
        "lanes": ["portable", "windows"],
    }
    return {
        "schema_version": 1,
        "task_id": "TASK-057",
        "plan_version": "TASK-057-PLAN-v3",
        "repository": REPOSITORY,
        "pull_request_number": PR,
        "base_branch": "main",
        "head_branch": BRANCH,
        "expected_base_sha": BASE,
        "starting_head_sha": STARTING_HEAD,
        "events": [
            {
                "event": "ASSIGN",
                "sequence": 1,
                "task_id": "TASK-057",
                "repository": REPOSITORY,
                "pull_request_number": PR,
                "head_branch": BRANCH,
                "role": "Implementation Agent",
                "agent_id": producer["agent_id"],
                "github_login": producer["github_login"],
                "tool": producer["tool"],
                "os": producer["os"],
                "lanes": producer["lanes"],
                "starting_head_sha": STARTING_HEAD,
                "pr_head_sha": STARTING_HEAD,
                "single_writer": True,
            }
        ],
        "authorized_producers": [producer],
    }


def _switched_assignment_document() -> dict[str, Any]:
    document = _assignment_document()
    first_event = document["events"][0]
    next_producer = {
        "agent_id": "task-057-plan-v3-codex-windows-2",
        "github_login": "next-writer",
        "role": "Implementation Agent",
        "tool": "Codex",
        "os": "Windows",
        "lanes": ["portable", "windows"],
    }
    stop_event = {
        "event": "STOP",
        "sequence": 2,
        "task_id": first_event["task_id"],
        "repository": first_event["repository"],
        "pull_request_number": first_event["pull_request_number"],
        "head_branch": first_event["head_branch"],
        "role": first_event["role"],
        "agent_id": first_event["agent_id"],
        "github_login": first_event["github_login"],
        "tool": first_event["tool"],
        "os": first_event["os"],
        "lanes": copy.deepcopy(first_event["lanes"]),
        "stop_head_sha": HEAD,
        "pr_head_sha": HEAD,
        "single_writer": True,
    }
    switch_event = {
        "event": "SWITCH",
        "sequence": 3,
        "task_id": first_event["task_id"],
        "repository": first_event["repository"],
        "pull_request_number": first_event["pull_request_number"],
        "head_branch": first_event["head_branch"],
        **copy.deepcopy(next_producer),
        "starting_head_sha": HEAD,
        "previous_agent_id": first_event["agent_id"],
        "next_agent_id": next_producer["agent_id"],
        "previous_agent_stop_head_sha": HEAD,
        "pr_head_sha": HEAD,
        "single_writer": True,
    }
    document["events"].extend((stop_event, switch_event))
    document["authorized_producers"].append(next_producer)
    return document


def _authority() -> validator.Authority:
    handoff = _handoff()
    assignment_body = _canonical_body(validator.AUTHORITY_SENTINEL, _assignment_document())
    handoff["github_authority"]["assignment_comment"]["body_sha256"] = hashlib.sha256(
        assignment_body.encode("utf-8")
    ).hexdigest()
    return validator.build_authority(_task(), handoff)


def _record(command: str, lane: str) -> dict[str, Any]:
    return {
        "lane": lane,
        "requirement": "required",
        "python_version": "3.12.10",
        "poetry_version": "2.4.1",
        "xtquant": None,
        "command": command,
        "exit_code": 0,
        "executed": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "timestamp": "2026-09-02T09:00:00+08:00",
        "sanitized_evidence": True,
        "unverified_scope": "",
        "capabilities": {
            "portable": True,
            "windows": True,
            "miniqmt_available": False,
            "userdata_mini_verified": False,
            "unique_session_verified": False,
            "simulation_account_allowlisted": False,
        },
        "miniqmt_connection": False,
        "account_query": False,
        "simulation_order": False,
        "real_money": False,
    }


def _evidence_document(authority: validator.Authority) -> dict[str, Any]:
    producer = copy.deepcopy(_assignment_document()["authorized_producers"][0])
    return {
        "schema_version": 1,
        "task_id": authority.task_id,
        "plan_version": authority.plan_version,
        "repository": REPOSITORY,
        "pull_request_number": PR,
        "base_sha": authority.expected_base,
        "head_sha": HEAD,
        "producer": producer,
        "assignment_comment": {
            "id": ASSIGNMENT_COMMENT_ID,
            "url": ASSIGNMENT_URL,
        },
        "records": [
            _record(command, lane.lane)
            for lane in authority.required_lanes
            for command in lane.commands
        ],
    }


def _pull() -> dict[str, Any]:
    return {
        "number": PR,
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "sha": BASE, "repo": {"full_name": REPOSITORY}},
        "head": {"ref": BRANCH, "sha": HEAD, "repo": {"full_name": REPOSITORY}},
    }


def _comment(comment_id: int, url: str, author: str, body: str) -> dict[str, Any]:
    return {
        "id": comment_id,
        "url": (f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{comment_id}"),
        "html_url": url,
        "issue_url": f"https://api.github.com/repos/{REPOSITORY}/issues/{PR}",
        "user": {"login": author},
        "created_at": "2026-09-02T09:00:00Z",
        "updated_at": "2026-09-02T09:00:00Z",
        "body": body,
    }


class FakeTransport:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, float, int]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> bytes:
        del headers
        self.calls.append((url, timeout, max_bytes))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, bytes):
            return response
        return json.dumps(response).encode("utf-8")


def _live_fixture() -> tuple[validator.Authority, validator.GitHubApiClient, FakeTransport]:
    authority = _authority()
    assignment_body = _canonical_body(validator.AUTHORITY_SENTINEL, _assignment_document())
    evidence_body = _canonical_body(validator.EVIDENCE_SENTINEL, _evidence_document(authority))
    assignment_comment = _comment(
        ASSIGNMENT_COMMENT_ID, ASSIGNMENT_URL, "qifuxiao", assignment_body
    )
    assignment_comment["created_at"] = authority.github.assignment_comment.created_at
    assignment_comment["updated_at"] = authority.github.assignment_comment.updated_at
    pull_url = f"https://api.github.com/repos/{REPOSITORY}/pulls/{PR}"
    assignment_api_url = (
        f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{ASSIGNMENT_COMMENT_ID}"
    )
    evidence_api_url = (
        f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{EVIDENCE_COMMENT_ID}"
    )
    responses: dict[str, object] = {
        pull_url: _pull(),
        assignment_api_url: assignment_comment,
        evidence_api_url: _comment(EVIDENCE_COMMENT_ID, EVIDENCE_URL, "qfxyyy", evidence_body),
    }
    transport = FakeTransport(responses)
    return authority, validator.GitHubApiClient(transport=transport), transport


def _replace_response(transport: FakeTransport, suffix: str, value: object) -> None:
    url = next(url for url in transport.responses if url.endswith(suffix))
    transport.responses[url] = value


def test_formal_schemas_are_valid_draft_2020_12() -> None:
    for path in (ASSIGNMENT_SCHEMA_PATH, EVIDENCE_SCHEMA_PATH):
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_git_loader_reads_exact_plan_v3_authority() -> None:
    authority = validator.load_authority_from_git(
        ROOT,
        head=PLAN_V3_HEAD,
        task_path=TASK_PATH.relative_to(ROOT),
        handoff_path=HANDOFF_PATH.relative_to(ROOT),
    )
    assert authority.task_id == "TASK-057"
    assert authority.plan_version == "TASK-057-PLAN-v3"
    assert authority.expected_base == BASE
    assert authority.github.repository == REPOSITORY
    assert [lane.lane for lane in authority.required_lanes] == ["portable", "windows"]
    assert authority.prohibited_lanes == ("windows_miniqmt",)


def test_task_and_handoff_lanes_deep_equal_and_partition_commands() -> None:
    authority = _authority()
    assert validator.authority_errors(_task(), _handoff()) == []
    assert Counter(
        command for lane in authority.required_lanes for command in lane.commands
    ) == Counter(authority.verification_commands)


@pytest.mark.parametrize(
    "field",
    (
        "api_origin",
        "repository",
        "pull_request_number",
        "base_branch",
        "head_branch",
        "authorized_human_logins",
        "assignment_comment",
        "authorized_producers",
    ),
)
def test_missing_github_trust_anchor_fails_closed(field: str) -> None:
    handoff = _handoff()
    del handoff["github_authority"][field]
    assert validator.authority_errors(_task(), handoff)


def test_live_pr_assignment_and_environment_evidence_pass() -> None:
    authority, client, transport = _live_fixture()
    assert (
        validator.validate_live_environment(
            authority=authority,
            expected_head=HEAD,
            evidence_comment=EVIDENCE_URL,
            github=client,
        )
        == []
    )
    assert [url for url, _, _ in transport.calls] == [
        f"https://api.github.com/repos/{REPOSITORY}/pulls/{PR}",
        f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{ASSIGNMENT_COMMENT_ID}",
        f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{EVIDENCE_COMMENT_ID}",
    ]
    assert all(timeout > 0 and max_bytes > 0 for _, timeout, max_bytes in transport.calls)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("state",), "closed"),
        (("draft",), True),
        (("base", "ref"), "release"),
        (("base", "sha"), "a" * 40),
        (("head", "ref"), "other/branch"),
        (("head", "sha"), "b" * 40),
        (("base", "repo", "full_name"), "example/repo"),
    ),
)
def test_live_pr_identity_drift_fails_closed(path: tuple[str, ...], value: object) -> None:
    authority, client, transport = _live_fixture()
    pull = _pull()
    target: dict[str, Any] = pull
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _replace_response(transport, "/pulls/100", pull)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


@pytest.mark.parametrize("case", ("wrong_author", "edited", "digest", "cross_pr"))
def test_human_assignment_comment_must_be_frozen_unedited_and_same_pr(case: str) -> None:
    authority, client, transport = _live_fixture()
    body = _canonical_body(validator.AUTHORITY_SENTINEL, _assignment_document())
    comment = _comment(ASSIGNMENT_COMMENT_ID, ASSIGNMENT_URL, "qifuxiao", body)
    if case == "wrong_author":
        comment["user"]["login"] = "qfxyyy"
    elif case == "edited":
        comment["updated_at"] = "2026-09-02T09:01:00Z"
    elif case == "digest":
        comment["body"] += "\n"
    else:
        comment["issue_url"] = f"https://api.github.com/repos/{REPOSITORY}/issues/999"
    _replace_response(transport, f"/comments/{ASSIGNMENT_COMMENT_ID}", comment)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("repository", "example/repo"),
        ("pull_request_number", 999),
        ("head_branch", "other/branch"),
        ("github_login", "someone-else"),
        ("tool", "Cline"),
        ("os", "Linux"),
        ("pr_head_sha", "a" * 40),
    ),
)
def test_assignment_event_identity_mismatch_fails_closed(field: str, value: object) -> None:
    authority, client, transport = _live_fixture()
    assignment = _assignment_document()
    assignment["events"][0][field] = value
    body = _canonical_body(validator.AUTHORITY_SENTINEL, assignment)
    authority.github.assignment_comment.body_sha256 = hashlib.sha256(
        body.encode("utf-8")
    ).hexdigest()
    comment = _comment(ASSIGNMENT_COMMENT_ID, ASSIGNMENT_URL, "qifuxiao", body)
    comment["created_at"] = authority.github.assignment_comment.created_at
    comment["updated_at"] = authority.github.assignment_comment.updated_at
    _replace_response(transport, f"/comments/{ASSIGNMENT_COMMENT_ID}", comment)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("github_login", "someone-else"),
        ("agent_id", "unassigned-agent"),
        ("role", "Environment Verification Agent"),
        ("tool", "Cline"),
        ("os", "Linux"),
        ("lanes", ["portable"]),
    ),
)
def test_evidence_producer_must_match_active_authorized_assignment(
    field: str, value: object
) -> None:
    authority, client, transport = _live_fixture()
    document = _evidence_document(authority)
    document["producer"][field] = value
    body = _canonical_body(validator.EVIDENCE_SENTINEL, document)
    _replace_response(
        transport,
        f"/comments/{EVIDENCE_COMMENT_ID}",
        _comment(EVIDENCE_COMMENT_ID, EVIDENCE_URL, "qfxyyy", body),
    )
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


def test_linux_assignment_cannot_be_satisfied_by_unrelated_windows_evidence() -> None:
    authority, client, transport = _live_fixture()
    assignment = _assignment_document()
    assignment["events"][0].update(
        {
            "agent_id": "cline-linux-writer",
            "github_login": "linux-login",
            "tool": "Cline",
            "os": "Linux",
            "lanes": ["portable"],
        }
    )
    assignment["authorized_producers"] = [
        {
            "agent_id": "cline-linux-writer",
            "github_login": "linux-login",
            "role": "Implementation Agent",
            "tool": "Cline",
            "os": "Linux",
            "lanes": ["portable"],
        }
    ]
    assignment_body = _canonical_body(validator.AUTHORITY_SENTINEL, assignment)
    authority.github.assignment_comment.body_sha256 = hashlib.sha256(
        assignment_body.encode("utf-8")
    ).hexdigest()
    authority.github.authorized_producers = tuple(assignment["authorized_producers"])
    _replace_response(
        transport,
        f"/comments/{ASSIGNMENT_COMMENT_ID}",
        _comment(ASSIGNMENT_COMMENT_ID, ASSIGNMENT_URL, "qifuxiao", assignment_body),
    )
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


@pytest.mark.parametrize("case", ("edited", "cross_pr", "wrong_author", "bad_body"))
def test_environment_comment_must_be_unedited_same_pr_and_canonical(case: str) -> None:
    authority, client, transport = _live_fixture()
    document = _evidence_document(authority)
    body = _canonical_body(validator.EVIDENCE_SENTINEL, document)
    comment = _comment(EVIDENCE_COMMENT_ID, EVIDENCE_URL, "qfxyyy", body)
    if case == "edited":
        comment["updated_at"] = "2026-09-02T09:01:00Z"
    elif case == "cross_pr":
        comment["issue_url"] = f"https://api.github.com/repos/{REPOSITORY}/issues/999"
    elif case == "wrong_author":
        comment["user"]["login"] = "qifuxiao"
    else:
        comment["body"] = "not canonical"
    _replace_response(transport, f"/comments/{EVIDENCE_COMMENT_ID}", comment)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


def _validate_document(document: dict[str, Any]) -> list[str]:
    authority = _authority()
    return validator.validate_evidence_document(
        document,
        authority=authority,
        expected_head=HEAD,
        active_assignment=_assignment_document()["events"][0],
        comment_author="qfxyyy",
    )


@pytest.mark.parametrize("case", ("missing", "duplicate", "substitute"))
def test_command_coverage_remains_opaque_exact_and_complete(case: str) -> None:
    authority = _authority()
    document = _evidence_document(authority)
    if case == "missing":
        document["records"].pop(0)
    elif case == "duplicate":
        document["records"].append(copy.deepcopy(document["records"][0]))
    else:
        document["records"][0]["command"] += " "
    assert _validate_document(document)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("task_id", "TASK-999"),
        ("plan_version", "TASK-057-PLAN-v2"),
        ("repository", "example/repo"),
        ("pull_request_number", 999),
        ("base_sha", "a" * 40),
        ("head_sha", "b" * 40),
    ),
)
def test_evidence_envelope_identity_must_match_frozen_and_live_authority(
    field: str, value: object
) -> None:
    document = _evidence_document(_authority())
    document[field] = value
    assert _validate_document(document)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("exit_code", 1),
        ("executed", 0),
        ("failed", 1),
        ("skipped", 1),
        ("executed", True),
    ),
)
def test_unsuccessful_or_inconsistent_results_fail_closed(field: str, value: object) -> None:
    document = _evidence_document(_authority())
    document["records"][0][field] = value
    assert _validate_document(document)


def test_windows_lane_requires_windows_assignment_and_capability() -> None:
    document = _evidence_document(_authority())
    record = next(item for item in document["records"] if item["lane"] == "windows")
    record["capabilities"]["windows"] = False
    assert _validate_document(document)


@pytest.mark.parametrize("case", ("sequence", "double_writer", "head"))
def test_assignment_order_single_writer_and_head_binding_fail_closed(case: str) -> None:
    authority = _authority()
    document = _assignment_document()
    if case == "sequence":
        document["events"][0]["sequence"] = 0
    elif case == "double_writer":
        second = copy.deepcopy(document["events"][0])
        second["sequence"] = 2
        second["agent_id"] = "second-writer"
        document["events"].append(second)
    else:
        document["events"][0]["starting_head_sha"] = "a" * 40
    assert validator.validate_assignments(document, authority=authority)


def test_complete_assign_stop_switch_sequence_passes() -> None:
    document = _switched_assignment_document()
    authority = _authority()
    authority.github.authorized_producers = tuple(document["authorized_producers"])

    assert validator.validate_assignments(document, authority=authority) == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("agent_id", "different-writer"),
        ("github_login", "different-login"),
        ("role", "Environment Verification Agent"),
        ("tool", "Cline"),
        ("os", "Linux"),
        ("lanes", ["windows", "portable"]),
    ),
)
def test_stop_must_match_full_active_writer_identity(field: str, value: object) -> None:
    document = _switched_assignment_document()
    document["events"][1][field] = value
    authority = _authority()
    authority.github.authorized_producers = tuple(document["authorized_producers"])

    errors = validator.validate_assignments(document, authority=authority)

    assert errors
    assert any("STOP identity" in error for error in errors)
    assert any("SWITCH requires the previous writer to be stopped" in error for error in errors)


@pytest.mark.parametrize(
    "timestamp",
    (
        "2026-09-02T09:00:00Z",
        "2026-09-02T09:00:00+08:00",
        "2026-09-02T09:00:00-05:30",
        "2026-09-02T09:00:00.123456Z",
        "2026-09-02T07:54:09Z",
    ),
)
def test_rfc3339_timestamps_pass(timestamp: str) -> None:
    assert validator._timestamp_errors(timestamp) == []


@pytest.mark.parametrize(
    "timestamp",
    (
        "2026-09-02 09:00:00+00:00",
        "2026-W36-3T09:00:00+00:00",
        "2026-09-02T09:00:00+0000",
        "2026-09-02T09:00:00",
        "2026-02-30T09:00:00Z",
        "2026-09-02T24:00:00Z",
        "2026-09-02T09:00:00+24:00",
        "2026-09-02T09:00:00+00:60",
        "",
        None,
        0,
    ),
)
def test_non_rfc3339_timestamps_fail_closed(timestamp: object) -> None:
    assert validator._timestamp_errors(timestamp)


@pytest.mark.parametrize(
    "failure",
    (
        validator.GitHubApiError("404 not found"),
        validator.GitHubApiError("403 forbidden"),
        validator.GitHubApiError("429 rate limited"),
        validator.GitHubApiError("timeout"),
        validator.GitHubApiError("redirect forbidden"),
    ),
)
def test_github_api_failures_fail_closed(failure: Exception) -> None:
    authority, client, transport = _live_fixture()
    _replace_response(transport, "/pulls/100", failure)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


@pytest.mark.parametrize(
    "response",
    (
        b"not-json",
        b"{" + b"x" * (validator.MAX_GITHUB_RESPONSE_BYTES + 1) + b"}",
        b'{"state":"open","state":"closed"}',
    ),
    ids=("invalid-json", "oversized", "duplicate-key"),
)
def test_invalid_oversized_or_duplicate_key_json_fails_closed(response: bytes) -> None:
    authority, client, transport = _live_fixture()
    _replace_response(transport, "/pulls/100", response)
    assert validator.validate_live_environment(
        authority=authority,
        expected_head=HEAD,
        evidence_comment=EVIDENCE_COMMENT_ID,
        github=client,
    )


def test_evidence_locator_cannot_inject_cross_repository_or_pr() -> None:
    authority, client, _ = _live_fixture()
    for locator in (
        "https://github.com/example/repo/pull/100#issuecomment-5509999999",
        "https://github.com/qifuxiao/QuantiQmt/pull/999#issuecomment-5509999999",
        "https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5509999999",
    ):
        assert validator.validate_live_environment(
            authority=authority,
            expected_head=HEAD,
            evidence_comment=locator,
            github=client,
        )


def test_cli_removes_caller_reported_pr_branch_head_and_local_assignment_authority() -> None:
    parser = validator._parser()
    options = {option for action in parser._actions for option in action.option_strings}
    assert "--evidence-comment" in options
    assert "--pr-head" not in options
    assert "--pr" not in options
    assert "--branch" not in options
    assert "--assignments" not in options
    assert "--task" not in options
    assert "--handoff" not in options


def test_task057_prohibits_miniqmt_and_broker_side_effects() -> None:
    authority, client, transport = _live_fixture()
    for field in ("miniqmt_connection", "account_query", "simulation_order", "real_money"):
        document = _evidence_document(authority)
        document["records"][0][field] = True
        body = _canonical_body(validator.EVIDENCE_SENTINEL, document)
        _replace_response(
            transport,
            f"/comments/{EVIDENCE_COMMENT_ID}",
            _comment(EVIDENCE_COMMENT_ID, EVIDENCE_URL, "qfxyyy", body),
        )
        assert validator.validate_live_environment(
            authority=authority,
            expected_head=HEAD,
            evidence_comment=EVIDENCE_COMMENT_ID,
            github=client,
        )


@pytest.mark.parametrize(
    "provenance",
    (
        {"source": "unknown", "value": "2026.vendor-r7", "verified": True},
        {"source": "package_metadata", "value": "", "verified": True},
        {"source": "vendor_api", "value": r"C:\\userdata_mini\\account-123", "verified": True},
        {"source": "vendor_api", "value": "secret-token", "verified": True},
        {"source": "vendor_api", "value": "123456789012", "verified": True},
        {"source": "vendor_api", "value": "2026.vendor-r7", "verified": False},
    ),
)
def test_xtquant_unknown_or_sensitive_provenance_fails(provenance: dict[str, Any]) -> None:
    assert validator.xtquant_provenance_errors(provenance)


@pytest.mark.parametrize(
    "provenance",
    (
        {"source": "package_metadata", "value": "2026.vendor-r7", "verified": True},
        {"source": "vendor_api", "value": "release_2026+broker.4", "verified": True},
    ),
)
def test_xtquant_trusted_opaque_provenance_passes(provenance: dict[str, Any]) -> None:
    assert validator.xtquant_provenance_errors(provenance) == []
