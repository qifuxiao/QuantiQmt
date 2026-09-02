"""Validate TASK-057 evidence against frozen authority and live GitHub objects.

Task and Repair Handoff command strings remain opaque exact values. Production network
access is restricted to bounded, non-redirecting HTTPS GET requests to the fixed GitHub
API origin; tests inject a transport and never use the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import yaml
from jsonschema.validators import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PurePosixPath(
    "tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
)
HANDOFF_PATH = PurePosixPath("ai/handoffs/TASK-057-REPAIR-v3.yaml")
ASSIGNMENT_SCHEMA = ROOT / "ai/schemas/agent-assignment.schema.yaml"
EVIDENCE_SCHEMA = ROOT / "ai/schemas/agent-environment-evidence.schema.yaml"
SUPPORTED_LANES = {"portable", "windows", "windows_miniqmt"}
TASK057_REQUIRED_LANES = ("portable", "windows")
TASK057_PROHIBITED_LANES = ("windows_miniqmt",)
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_TIMEOUT_SECONDS = 10.0
MAX_GITHUB_RESPONSE_BYTES = 262_144
AUTHORITY_SENTINEL = "QUANTIQMT_GITHUB_AUTHORITY_V1"
EVIDENCE_SENTINEL = "QUANTIQMT_ENVIRONMENT_EVIDENCE_V1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")
TOOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
SENSITIVE_VERSION_RE = re.compile(
    r"(?:userdata_mini|account|acct|credential|secret|token|password|passwd|pwd|api[-_]?key)",
    re.IGNORECASE,
)
OPAQUE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class LaneRequirement:
    lane: str
    capability: str
    minimum_records: int
    commands: tuple[str, ...]


@dataclass
class AssignmentCommentIdentity:
    id: int
    url: str
    api_url: str
    issue_url: str
    author_login: str
    created_at: str
    updated_at: str
    body_sha256: str
    sentinel: str
    schema_version: int


@dataclass
class GitHubAuthority:
    api_origin: str
    repository: str
    pull_request_number: int
    base_branch: str
    head_branch: str
    authorized_human_logins: tuple[str, ...]
    assignment_comment: AssignmentCommentIdentity
    authorized_producers: tuple[dict[str, Any], ...]


@dataclass
class Authority:
    task_id: str
    plan_version: str
    expected_base: str
    expected_pr_base: str
    task_blob: str
    superseded_head: str
    verification_commands: list[str]
    required_lanes: tuple[LaneRequirement, ...]
    prohibited_lanes: tuple[str, ...]
    github: GitHubAuthority


class GitHubApiError(ValueError):
    """A bounded GitHub read failed and must fail the validation closed."""


Transport = Callable[[str, dict[str, str], float, int], bytes]


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _parse_front_matter(text: str) -> dict[str, Any]:
    match = FRONT_MATTER_RE.match(text.replace("\r\n", "\n"))
    if match is None:
        raise ValueError("active task is missing YAML front matter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("active task front matter must be a mapping")
    return value


def _load_yaml_text(text: str, label: str) -> dict[str, Any]:
    value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a YAML mapping")
    return value


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _schema_errors(document: object, path: Path) -> list[str]:
    schema = _load_yaml_text(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
    validator = Draft202012Validator(schema)
    return [
        f"schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(document), key=lambda item: list(item.absolute_path)
        )
    ]


def _required_lane_errors(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    names: list[str] = []
    for index, raw_lane in enumerate(value):
        lane = _mapping(raw_lane)
        if lane is None:
            errors.append(f"{label}[{index}] must be a mapping")
            continue
        name = lane.get("lane")
        if not isinstance(name, str) or name not in SUPPORTED_LANES:
            errors.append(f"{label}[{index}] has an unknown lane")
        else:
            names.append(name)
        if lane.get("capability") != name:
            errors.append(f"{label}[{index}] capability must match lane")
        minimum_records = lane.get("minimum_records")
        if type(minimum_records) is not int or minimum_records < 1:
            errors.append(f"{label}[{index}] minimum_records must be a positive integer")
        commands = lane.get("commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"{label}[{index}] commands must be a non-empty list")
        elif any(not isinstance(command, str) or not command for command in commands):
            errors.append(f"{label}[{index}] commands must contain exact non-empty strings")
        elif len(commands) != len(set(commands)):
            errors.append(f"{label}[{index}] commands contain duplicates")
    if len(names) != len(set(names)):
        errors.append(f"{label} contains duplicate lanes")
    return errors


def _producer_errors(value: object, *, label: str) -> list[str]:
    producer = _mapping(value)
    if producer is None:
        return [f"{label} must be a mapping"]
    errors: list[str] = []
    checks = (
        ("agent_id", AGENT_RE),
        ("github_login", LOGIN_RE),
        ("tool", TOOL_RE),
    )
    for field, pattern in checks:
        raw = producer.get(field)
        if not isinstance(raw, str) or pattern.fullmatch(raw) is None:
            errors.append(f"{label}.{field} is invalid")
    if producer.get("role") not in {
        "Implementation Agent",
        "Environment Verification Agent",
    }:
        errors.append(f"{label}.role is invalid")
    if producer.get("os") not in {"Windows", "Linux", "macOS"}:
        errors.append(f"{label}.os is invalid")
    lanes = producer.get("lanes")
    if (
        not isinstance(lanes, list)
        or not lanes
        or len(lanes) != len(set(str(item) for item in lanes))
        or any(not isinstance(lane, str) or lane not in SUPPORTED_LANES for lane in lanes)
    ):
        errors.append(f"{label}.lanes must be unique supported lanes")
    return errors


def _github_authority_errors(value: object) -> list[str]:
    github = _mapping(value)
    if github is None:
        return ["Handoff github_authority must be a mapping"]
    errors: list[str] = []
    if github.get("api_origin") != GITHUB_API_ORIGIN:
        errors.append("GitHub API origin must be fixed to https://api.github.com")
    repository = github.get("repository")
    if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
        errors.append("GitHub repository identity is invalid")
        repository = "invalid/invalid"
    pr = github.get("pull_request_number")
    if type(pr) is not int or pr < 1:
        errors.append("GitHub pull request number is invalid")
        pr = 0
    for field in ("base_branch", "head_branch"):
        branch = github.get(field)
        if not isinstance(branch, str) or BRANCH_RE.fullmatch(branch) is None:
            errors.append(f"GitHub {field} is invalid")
    human_logins = github.get("authorized_human_logins")
    if (
        not isinstance(human_logins, list)
        or not human_logins
        or len(human_logins) != len(set(str(item) for item in human_logins))
        or any(
            not isinstance(item, str) or LOGIN_RE.fullmatch(item) is None for item in human_logins
        )
    ):
        errors.append("authorized Human logins must be a non-empty unique list")
        human_logins = []

    comment = _mapping(github.get("assignment_comment"))
    if comment is None:
        errors.append("GitHub assignment_comment must be a mapping")
    else:
        comment_id = comment.get("id")
        if type(comment_id) is not int or comment_id < 1:
            errors.append("assignment comment id is invalid")
            comment_id = 0
        expected_url = f"https://github.com/{repository}/pull/{pr}#issuecomment-{comment_id}"
        expected_api_url = f"{GITHUB_API_ORIGIN}/repos/{repository}/issues/comments/{comment_id}"
        expected_issue_url = f"{GITHUB_API_ORIGIN}/repos/{repository}/issues/{pr}"
        for field, expected in (
            ("url", expected_url),
            ("api_url", expected_api_url),
            ("issue_url", expected_issue_url),
        ):
            if comment.get(field) != expected:
                errors.append(f"assignment comment {field} is not frozen to the target PR")
        author = comment.get("author_login")
        if author not in human_logins:
            errors.append("assignment comment author is not an authorized Human")
        created = comment.get("created_at")
        updated = comment.get("updated_at")
        if not isinstance(created, str) or not isinstance(updated, str) or created != updated:
            errors.append("assignment comment must freeze equal created/updated timestamps")
        digest = comment.get("body_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"^[0-9a-f]{64}$", digest) is None:
            errors.append("assignment comment body SHA-256 is invalid")
        if comment.get("sentinel") != AUTHORITY_SENTINEL:
            errors.append("assignment comment sentinel is invalid")
        if comment.get("schema_version") != 1:
            errors.append("assignment comment schema version is invalid")

    producers = github.get("authorized_producers")
    if not isinstance(producers, list) or not producers:
        errors.append("authorized_producers must be a non-empty list")
    else:
        for index, producer in enumerate(producers):
            errors.extend(_producer_errors(producer, label=f"authorized_producers[{index}]"))
        identities = [item.get("agent_id") for item in producers if isinstance(item, Mapping)]
        if len(identities) != len(set(str(identity) for identity in identities)):
            errors.append("authorized producer agent identities must be unique")
    return errors


def authority_errors(task: Mapping[str, Any], handoff: Mapping[str, Any]) -> list[str]:
    """Validate frozen task/Handoff authority without caller identity input."""

    errors: list[str] = []
    task_id = task.get("id")
    if task_id != "TASK-057" or task.get("status") != "active":
        errors.append("the exact active task must be TASK-057")
    if (
        handoff.get("task_id") != task_id
        or handoff.get("packet_version") != "TASK-057-REPAIR-v3"
        or handoff.get("plan_version") != "TASK-057-PLAN-v3"
    ):
        errors.append("Repair Handoff identity does not match TASK-057 Plan v3")
    for field in ("expected_base_sha", "expected_pr_base_sha", "task_blob_sha"):
        raw = handoff.get(field)
        if not isinstance(raw, str) or SHA_RE.fullmatch(raw) is None:
            errors.append(f"Handoff {field} must be an exact SHA")
    if handoff.get("expected_base_sha") != handoff.get("expected_pr_base_sha"):
        errors.append("Handoff Base and PR Base must be identical")
    repair_context = _mapping(handoff.get("repair_context"))
    superseded = repair_context.get("superseded_head_sha") if repair_context else None
    if not isinstance(superseded, str) or SHA_RE.fullmatch(superseded) is None:
        errors.append("Repair Handoff superseded Head must be an exact SHA")
    errors.extend(_github_authority_errors(handoff.get("github_authority")))

    verification = _mapping(task.get("verification"))
    if verification is None:
        return [*errors, "task verification must be a mapping"]
    commands = verification.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("verification.commands must be a non-empty list")
        commands = []
    elif any(not isinstance(command, str) or not command for command in commands):
        errors.append("verification.commands must contain exact non-empty strings")
    elif len(commands) != len(set(commands)):
        errors.append("verification.commands must not contain duplicates")

    task_lanes = verification.get("required_lanes")
    handoff_lanes = handoff.get("required_lanes")
    errors.extend(_required_lane_errors(task_lanes, label="task required_lanes"))
    errors.extend(_required_lane_errors(handoff_lanes, label="Handoff required_lanes"))
    if task_lanes != handoff_lanes:
        errors.append("task and Handoff required_lanes must be deep-equal")

    task_prohibited = verification.get("prohibited_lanes")
    handoff_prohibited = handoff.get("prohibited_lanes")
    if not isinstance(task_prohibited, list) or not task_prohibited:
        errors.append("task prohibited_lanes must be a non-empty list")
        task_prohibited = []
    if not isinstance(handoff_prohibited, list) or not handoff_prohibited:
        errors.append("Handoff prohibited_lanes must be a non-empty list")
        handoff_prohibited = []
    if task_prohibited != handoff_prohibited:
        errors.append("task and Handoff prohibited_lanes must be deep-equal")
    if any(not isinstance(lane, str) or lane not in SUPPORTED_LANES for lane in task_prohibited):
        errors.append("prohibited_lanes contains an unknown lane")
    if len(task_prohibited) != len(set(task_prohibited)):
        errors.append("prohibited_lanes contains duplicates")

    valid_task_lanes = task_lanes if isinstance(task_lanes, list) else []
    lane_names = tuple(
        raw_lane.get("lane")
        for raw_lane in valid_task_lanes
        if isinstance(raw_lane, Mapping) and isinstance(raw_lane.get("lane"), str)
    )
    if task_id == "TASK-057" and lane_names != TASK057_REQUIRED_LANES:
        errors.append("TASK-057 required lanes must be exactly portable and windows")
    if task_id == "TASK-057" and tuple(task_prohibited) != TASK057_PROHIBITED_LANES:
        errors.append("TASK-057 must prohibit windows_miniqmt")

    lane_commands: list[str] = []
    for raw_lane in valid_task_lanes:
        if isinstance(raw_lane, Mapping) and isinstance(raw_lane.get("commands"), list):
            lane_commands.extend(
                command for command in raw_lane["commands"] if isinstance(command, str)
            )
    if Counter(lane_commands) != Counter(
        command for command in commands if isinstance(command, str)
    ):
        errors.append("required-lane commands must exactly partition verification.commands")
    if len(lane_commands) != len(set(lane_commands)):
        errors.append("required-lane command partition contains duplicates")
    return errors


def build_authority(task: Mapping[str, Any], handoff: Mapping[str, Any]) -> Authority:
    errors = authority_errors(task, handoff)
    if errors:
        raise ValueError("; ".join(errors))
    verification = task["verification"]
    lanes = tuple(
        LaneRequirement(
            lane=raw_lane["lane"],
            capability=raw_lane["capability"],
            minimum_records=raw_lane["minimum_records"],
            commands=tuple(raw_lane["commands"]),
        )
        for raw_lane in verification["required_lanes"]
    )
    github_raw = handoff["github_authority"]
    comment_raw = github_raw["assignment_comment"]
    comment = AssignmentCommentIdentity(**comment_raw)
    github = GitHubAuthority(
        api_origin=github_raw["api_origin"],
        repository=github_raw["repository"],
        pull_request_number=github_raw["pull_request_number"],
        base_branch=github_raw["base_branch"],
        head_branch=github_raw["head_branch"],
        authorized_human_logins=tuple(github_raw["authorized_human_logins"]),
        assignment_comment=comment,
        authorized_producers=tuple(
            dict(producer) for producer in github_raw["authorized_producers"]
        ),
    )
    return Authority(
        task_id=task["id"],
        plan_version=handoff["plan_version"],
        expected_base=handoff["expected_base_sha"],
        expected_pr_base=handoff["expected_pr_base_sha"],
        task_blob=handoff["task_blob_sha"],
        superseded_head=handoff["repair_context"]["superseded_head_sha"],
        verification_commands=list(verification["commands"]),
        required_lanes=lanes,
        prohibited_lanes=tuple(verification["prohibited_lanes"]),
        github=github,
    )


def load_authority_from_git(
    repo: Path,
    *,
    head: str,
    task_path: Path | PurePosixPath = TASK_PATH,
    handoff_path: Path | PurePosixPath = HANDOFF_PATH,
) -> Authority:
    """Read the unique active task and frozen Repair v3 Handoff from an exact tree."""

    repo = repo.resolve()
    resolved_head = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}")
    task_posix = PurePosixPath(task_path).as_posix()
    handoff_posix = PurePosixPath(handoff_path).as_posix()
    if task_posix != TASK_PATH.as_posix() or handoff_posix != HANDOFF_PATH.as_posix():
        raise ValueError("task and Handoff paths are fixed by TASK-057 Plan v3")
    task_files = _git(repo, "ls-tree", "-r", "--name-only", resolved_head, "--", "tasks/active")
    active: list[str] = []
    for path in task_files.splitlines():
        if not path.endswith(".md") or path.endswith("/README.md"):
            continue
        candidate = _parse_front_matter(_git(repo, "show", f"{resolved_head}:{path}"))
        if candidate.get("status") == "active":
            active.append(path)
    if active != [task_posix]:
        raise ValueError(
            f"exact Git Head must contain one active task at {task_posix}; got {active}"
        )
    task = _parse_front_matter(_git(repo, "show", f"{resolved_head}:{task_posix}"))
    handoff = _load_yaml_text(
        _git(repo, "show", f"{resolved_head}:{handoff_posix}"), "Repair Handoff"
    )
    authority = build_authority(task, handoff)
    actual_blob = _git(repo, "rev-parse", f"{resolved_head}:{task_posix}")
    if actual_blob != authority.task_blob:
        raise ValueError("active task blob does not match the frozen Repair Handoff")
    return authority


def xtquant_provenance_errors(value: object) -> list[str]:
    provenance = _mapping(value)
    if provenance is None:
        return ["xtquant provenance must be a mapping"]
    errors: list[str] = []
    if provenance.get("source") not in {"package_metadata", "vendor_api"}:
        errors.append("xtquant provenance source is not trusted")
    opaque = provenance.get("value")
    if not isinstance(opaque, str) or OPAQUE_VERSION_RE.fullmatch(opaque) is None:
        errors.append("xtquant provenance value must be an opaque sanitized token")
    elif SENSITIVE_VERSION_RE.search(opaque) or (opaque.isdigit() and len(opaque) >= 6):
        errors.append("xtquant provenance value may contain sensitive or account data")
    if provenance.get("verified") is not True:
        errors.append("xtquant provenance must be verified")
    return errors


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > MAX_GITHUB_RESPONSE_BYTES:
        raise GitHubApiError(f"{label} exceeds the response-size limit")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GitHubApiError(f"{label} is not canonical UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GitHubApiError(f"{label} JSON root must be an object")
    return value


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _stdlib_https_get(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> bytes:
    parsed = urlsplit(url)
    if f"{parsed.scheme}://{parsed.netloc}" != GITHUB_API_ORIGIN:
        raise GitHubApiError("GitHub API request origin is not allowed")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise GitHubApiError("GitHub API request URL is not canonical")
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise GitHubApiError(f"GitHub API returned HTTP {status}")
            if response.geturl() != url:
                raise GitHubApiError("GitHub API redirects are forbidden")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > max_bytes:
                raise GitHubApiError("GitHub API response exceeds the size limit")
            body = bytes(response.read(max_bytes + 1))
    except urllib.error.HTTPError as exc:
        raise GitHubApiError(f"GitHub API returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if isinstance(exc, GitHubApiError):
            raise
        raise GitHubApiError(f"GitHub API GET failed: {exc}") from exc
    if len(body) > max_bytes:
        raise GitHubApiError("GitHub API response exceeds the size limit")
    return body


class GitHubApiClient:
    """Fixed-origin, bounded GitHub API reader with injectable transport."""

    def __init__(
        self,
        *,
        transport: Transport = _stdlib_https_get,
        token: str | None = None,
    ) -> None:
        self._transport = transport
        self._token = token

    def get(self, path: str) -> dict[str, Any]:
        if not path.startswith("/repos/") or any(part in path for part in ("?", "#", "..", "//")):
            raise GitHubApiError("GitHub API path is not allowed")
        url = f"{GITHUB_API_ORIGIN}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "QuantiQmt-TASK-057-validator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            raw = self._transport(url, headers, GITHUB_TIMEOUT_SECONDS, MAX_GITHUB_RESPONSE_BYTES)
        except GitHubApiError:
            raise
        except Exception as exc:
            raise GitHubApiError(f"GitHub API transport failed: {exc}") from exc
        return _parse_json_object(raw, label=path)

    def pull(self, authority: GitHubAuthority) -> dict[str, Any]:
        return self.get(f"/repos/{authority.repository}/pulls/{authority.pull_request_number}")

    def comment(self, authority: GitHubAuthority, comment_id: int) -> dict[str, Any]:
        return self.get(f"/repos/{authority.repository}/issues/comments/{comment_id}")


def _canonical_document(body: object, *, sentinel: str) -> dict[str, Any]:
    if not isinstance(body, str):
        raise ValueError("canonical GitHub comment body must be text")
    pattern = re.compile(
        rf"\A{re.escape(sentinel)}\r?\n```json\r?\n(.*?)\r?\n```\Z",
        re.DOTALL,
    )
    match = pattern.fullmatch(body)
    if match is None:
        raise ValueError("canonical GitHub comment format is invalid")
    try:
        value = json.loads(match.group(1), object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"canonical GitHub comment JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("canonical GitHub comment JSON root must be an object")
    return value


def _nested(mapping: Mapping[str, Any], *keys: str) -> object:
    current: object = mapping
    for key in keys:
        value = _mapping(current)
        if value is None:
            return None
        current = value.get(key)
    return current


def _pull_errors(pull: Mapping[str, Any], *, authority: Authority, expected_head: str) -> list[str]:
    github = authority.github
    checks = (
        ("number", pull.get("number"), github.pull_request_number),
        ("state", pull.get("state"), "open"),
        ("draft", pull.get("draft"), False),
        ("base branch", _nested(pull, "base", "ref"), github.base_branch),
        ("base SHA", _nested(pull, "base", "sha"), authority.expected_pr_base),
        ("base repository", _nested(pull, "base", "repo", "full_name"), github.repository),
        ("head branch", _nested(pull, "head", "ref"), github.head_branch),
        ("head SHA", _nested(pull, "head", "sha"), expected_head),
        ("head repository", _nested(pull, "head", "repo", "full_name"), github.repository),
    )
    return [
        f"live PR {label} does not match frozen authority"
        for label, actual, expected in checks
        if actual != expected
    ]


def _comment_errors(
    comment: Mapping[str, Any],
    *,
    authority: Authority,
    comment_id: int,
    expected_url: str,
    expected_author: str | None,
    frozen_created: str | None = None,
    frozen_updated: str | None = None,
) -> list[str]:
    github = authority.github
    expected_issue = (
        f"{GITHUB_API_ORIGIN}/repos/{github.repository}/issues/{github.pull_request_number}"
    )
    expected_api_url = f"{GITHUB_API_ORIGIN}/repos/{github.repository}/issues/comments/{comment_id}"
    errors: list[str] = []
    for label, actual, expected in (
        ("id", comment.get("id"), comment_id),
        ("API URL", comment.get("url"), expected_api_url),
        ("URL", comment.get("html_url"), expected_url),
        ("issue URL", comment.get("issue_url"), expected_issue),
        ("author", _nested(comment, "user", "login"), expected_author),
    ):
        if expected is not None and actual != expected:
            errors.append(f"GitHub comment {label} does not match frozen authority")
    created = comment.get("created_at")
    updated = comment.get("updated_at")
    if not isinstance(created, str) or updated != created:
        errors.append("GitHub comment must be unedited (created_at == updated_at)")
    else:
        errors.extend(f"GitHub comment {error}" for error in _timestamp_errors(created))
    if frozen_created is not None and created != frozen_created:
        errors.append("GitHub comment created_at does not match frozen authority")
    if frozen_updated is not None and updated != frozen_updated:
        errors.append("GitHub comment updated_at does not match frozen authority")
    return errors


def validate_assignments(document: object, *, authority: Authority) -> list[str]:
    """Validate the canonical ordered assignment document and active writer."""

    errors = _schema_errors(document, ASSIGNMENT_SCHEMA)
    root = _mapping(document)
    if root is None:
        return errors
    expected_root = {
        "task_id": authority.task_id,
        "plan_version": authority.plan_version,
        "repository": authority.github.repository,
        "pull_request_number": authority.github.pull_request_number,
        "base_branch": authority.github.base_branch,
        "head_branch": authority.github.head_branch,
        "expected_base_sha": authority.expected_base,
        "starting_head_sha": authority.superseded_head,
    }
    for field, expected in expected_root.items():
        if root.get(field) != expected:
            errors.append(f"assignment {field} does not match frozen authority")
    if root.get("authorized_producers") != list(authority.github.authorized_producers):
        errors.append("assignment authorized_producers do not match the frozen Handoff")

    events = root.get("events")
    if not isinstance(events, list) or not events:
        return errors or ["assignment events must be non-empty"]
    active: Mapping[str, Any] | None = None
    stopped: Mapping[str, Any] | None = None
    last_sequence = 0
    assigned_agents: set[str] = set()
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event)
        if event is None:
            continue
        prefix = f"assignment event {index}"
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence <= last_sequence:
            errors.append(f"{prefix}: sequence must be strictly increasing")
        else:
            last_sequence = sequence
        for field, expected in (
            ("task_id", authority.task_id),
            ("repository", authority.github.repository),
            ("pull_request_number", authority.github.pull_request_number),
            ("head_branch", authority.github.head_branch),
        ):
            if event.get(field) != expected:
                errors.append(f"{prefix}: {field} identity does not match")
        agent = event.get("agent_id")
        kind = event.get("event")
        if kind == "ASSIGN":
            if active is not None:
                errors.append(f"{prefix}: ASSIGN would create two active writers")
            if assigned_agents:
                errors.append(f"{prefix}: later writers must use SWITCH")
            if not (
                event.get("starting_head_sha")
                == event.get("pr_head_sha")
                == authority.superseded_head
            ):
                errors.append(f"{prefix}: ASSIGN starting Head must equal frozen PR Head")
            active = event
            stopped = None
            if isinstance(agent, str):
                assigned_agents.add(agent)
        elif kind == "STOP":
            if active is None or active.get("agent_id") != agent:
                errors.append(f"{prefix}: STOP must name the active writer")
            if event.get("stop_head_sha") != event.get("pr_head_sha"):
                errors.append(f"{prefix}: STOP Head must equal the then-current PR Head")
            stopped = event
            active = None
        elif kind == "SWITCH":
            if active is not None:
                errors.append(f"{prefix}: SWITCH requires the previous writer to be stopped")
            if stopped is None:
                errors.append(f"{prefix}: SWITCH requires a preceding STOP event")
            else:
                if event.get("previous_agent_id") != stopped.get("agent_id"):
                    errors.append(f"{prefix}: SWITCH previous agent does not match STOP")
                if not (
                    stopped.get("stop_head_sha")
                    == event.get("previous_agent_stop_head_sha")
                    == event.get("starting_head_sha")
                    == event.get("pr_head_sha")
                ):
                    errors.append(f"{prefix}: STOP, SWITCH and PR Heads must match")
            if event.get("next_agent_id") != agent:
                errors.append(f"{prefix}: SWITCH next agent does not match")
            if isinstance(agent, str):
                if agent in assigned_agents:
                    errors.append(f"{prefix}: agent identity cannot be reused")
                assigned_agents.add(agent)
            active = event
            stopped = None
    if active is None:
        errors.append("assignment event collection must end with exactly one active writer")
    elif not any(
        all(
            active.get(field) == producer.get(field)
            for field in ("agent_id", "github_login", "role", "tool", "os", "lanes")
        )
        for producer in authority.github.authorized_producers
    ):
        errors.append("active assignment is not an authorized evidence producer")
    return errors


def _active_assignment(document: Mapping[str, Any]) -> Mapping[str, Any] | None:
    active: Mapping[str, Any] | None = None
    events = document.get("events")
    if not isinstance(events, list):
        return None
    for raw_event in events:
        event = _mapping(raw_event)
        if event is None:
            continue
        if event.get("event") in {"ASSIGN", "SWITCH"}:
            active = event
        elif event.get("event") == "STOP":
            active = None
    return active


def _timestamp_errors(value: object) -> list[str]:
    if not isinstance(value, str):
        return ["timestamp must be RFC3339 with an explicit timezone"]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ["timestamp must be a real RFC3339 datetime"]
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ["timestamp must include an explicit timezone"]
    return []


def validate_evidence_document(
    document: object,
    *,
    authority: Authority,
    expected_head: str,
    active_assignment: Mapping[str, Any] | None,
    comment_author: object,
) -> list[str]:
    """Validate one canonical evidence document against frozen and live identity."""

    errors = _schema_errors(document, EVIDENCE_SCHEMA)
    root = _mapping(document)
    if root is None:
        return errors
    expected_root = {
        "task_id": authority.task_id,
        "plan_version": authority.plan_version,
        "repository": authority.github.repository,
        "pull_request_number": authority.github.pull_request_number,
        "base_sha": authority.expected_base,
        "head_sha": expected_head,
    }
    for field, expected in expected_root.items():
        if root.get(field) != expected:
            errors.append(f"evidence {field} does not match frozen/live authority")
    assignment_locator = _mapping(root.get("assignment_comment")) or {}
    if assignment_locator.get("id") != authority.github.assignment_comment.id:
        errors.append("evidence assignment comment id does not match frozen authority")
    if assignment_locator.get("url") != authority.github.assignment_comment.url:
        errors.append("evidence assignment comment URL does not match frozen authority")

    producer = _mapping(root.get("producer")) or {}
    if not any(
        dict(producer) == dict(authorized) for authorized in authority.github.authorized_producers
    ):
        errors.append("evidence producer is not authorized by the frozen Handoff")
    if comment_author != producer.get("github_login"):
        errors.append("evidence comment author does not match producer GitHub login")
    if producer.get("role") == "Implementation Agent" and (
        active_assignment is None
        or any(
            active_assignment.get(field) != producer.get(field)
            for field in ("agent_id", "github_login", "role", "tool", "os", "lanes")
        )
    ):
        errors.append("Implementation Agent producer is not the active assignment")

    records = root.get("records")
    if not isinstance(records, list) or not records:
        return errors or ["environment evidence records must be non-empty"]
    lane_by_name = {lane.lane: lane for lane in authority.required_lanes}
    observed_by_lane: dict[str, list[str]] = {lane: [] for lane in lane_by_name}
    raw_producer_lanes = producer.get("lanes")
    producer_lanes: list[Any] = raw_producer_lanes if isinstance(raw_producer_lanes, list) else []
    for index, raw_record in enumerate(records):
        record = _mapping(raw_record)
        if record is None:
            continue
        prefix = f"evidence record {index}"
        lane = record.get("lane")
        if not isinstance(lane, str):
            errors.append(f"{prefix}: lane must be a supported string")
            continue
        if lane in authority.prohibited_lanes:
            errors.append(f"{prefix}: prohibited lane {lane} cannot satisfy TASK-057")
        if lane not in lane_by_name:
            errors.append(f"{prefix}: lane is not required by frozen authority")
        else:
            observed_by_lane[lane].append(str(record.get("command", "")))
        if lane not in producer_lanes:
            errors.append(f"{prefix}: producer is not authorized for lane {lane}")
        if record.get("requirement") != "required":
            errors.append(f"{prefix}: required-lane evidence must say required")

        capabilities = _mapping(record.get("capabilities")) or {}
        if lane == "portable" and capabilities.get("portable") is not True:
            errors.append(f"{prefix}: portable capability is missing")
        if lane in {"windows", "windows_miniqmt"} and (
            producer.get("os") != "Windows" or capabilities.get("windows") is not True
        ):
            errors.append(f"{prefix}: Windows evidence requires actual Windows capability")
        if lane == "windows_miniqmt":
            for capability in (
                "miniqmt_available",
                "userdata_mini_verified",
                "unique_session_verified",
                "simulation_account_allowlisted",
            ):
                if capabilities.get(capability) is not True:
                    errors.append(f"{prefix}: Mini QMT capability {capability} is missing")
            errors.extend(
                f"{prefix}: {error}" for error in xtquant_provenance_errors(record.get("xtquant"))
            )
        elif record.get("xtquant") is not None:
            errors.extend(
                f"{prefix}: {error}" for error in xtquant_provenance_errors(record.get("xtquant"))
            )

        counts: dict[str, int] = {}
        for field in ("executed", "passed", "failed", "skipped"):
            value = record.get(field)
            if type(value) is int and value >= 0:
                counts[field] = value
        if len(counts) == 4:
            if counts["executed"] <= 0:
                errors.append(f"{prefix}: executed count must be positive")
            if counts["executed"] != counts["passed"] + counts["failed"] + counts["skipped"]:
                errors.append(f"{prefix}: result counts are inconsistent")
            if counts["failed"] != 0:
                errors.append(f"{prefix}: failed count must be zero")
            if counts["skipped"] != 0:
                errors.append(f"{prefix}: skip is not allowed by frozen TASK-057 lanes")
        if record.get("exit_code") != 0:
            errors.append(f"{prefix}: exit code must be zero")
        errors.extend(f"{prefix}: {error}" for error in _timestamp_errors(record.get("timestamp")))
        if record.get("real_money") is not False:
            errors.append(f"{prefix}: real-money activity is always prohibited")
        for field in ("miniqmt_connection", "account_query", "simulation_order"):
            if record.get(field) is not False:
                errors.append(f"{prefix}: TASK-057 prohibits {field}")

    for lane_name, requirement in lane_by_name.items():
        observed = observed_by_lane[lane_name]
        expected = list(requirement.commands)
        if len(observed) < requirement.minimum_records:
            errors.append(f"lane {lane_name}: insufficient evidence records")
        if Counter(observed) != Counter(expected):
            missing = list((Counter(expected) - Counter(observed)).elements())
            unexpected = list((Counter(observed) - Counter(expected)).elements())
            if missing:
                errors.append(f"lane {lane_name}: missing exact commands: {missing}")
            if unexpected:
                errors.append(f"lane {lane_name}: unexpected or duplicate commands: {unexpected}")
        if len(observed) != len(set(observed)):
            errors.append(f"lane {lane_name}: duplicate command evidence is forbidden")
    return errors


def _evidence_comment_id(locator: int | str, *, authority: Authority) -> int:
    if type(locator) is int and locator > 0:
        return locator
    if isinstance(locator, str):
        expected_prefix = (
            f"https://github.com/{authority.github.repository}/pull/"
            f"{authority.github.pull_request_number}#issuecomment-"
        )
        if locator.startswith(expected_prefix):
            suffix = locator.removeprefix(expected_prefix)
            if suffix.isdigit() and int(suffix) > 0:
                return int(suffix)
    raise ValueError("evidence comment locator must identify the frozen repository and PR")


def validate_live_environment(
    *,
    authority: Authority,
    expected_head: str,
    evidence_comment: int | str,
    github: GitHubApiClient,
) -> list[str]:
    """Read live PR/comments and validate the complete canonical evidence set."""

    try:
        pull = github.pull(authority.github)
        errors = _pull_errors(pull, authority=authority, expected_head=expected_head)
        if errors:
            return errors

        frozen_comment = authority.github.assignment_comment
        assignment_comment = github.comment(authority.github, frozen_comment.id)
        errors.extend(
            _comment_errors(
                assignment_comment,
                authority=authority,
                comment_id=frozen_comment.id,
                expected_url=frozen_comment.url,
                expected_author=frozen_comment.author_login,
                frozen_created=frozen_comment.created_at,
                frozen_updated=frozen_comment.updated_at,
            )
        )
        assignment_body = assignment_comment.get("body")
        if isinstance(assignment_body, str):
            digest = hashlib.sha256(assignment_body.encode("utf-8")).hexdigest()
            if digest != frozen_comment.body_sha256:
                errors.append("assignment comment raw body digest does not match Handoff")
        else:
            errors.append("assignment comment body is missing")
        if errors:
            return errors
        assignment_document = _canonical_document(assignment_body, sentinel=AUTHORITY_SENTINEL)
        errors.extend(validate_assignments(assignment_document, authority=authority))
        if errors:
            return errors
        assignment_root = _mapping(assignment_document)
        active = _active_assignment(assignment_root) if assignment_root else None

        evidence_id = _evidence_comment_id(evidence_comment, authority=authority)
        evidence_url = (
            f"https://github.com/{authority.github.repository}/pull/"
            f"{authority.github.pull_request_number}#issuecomment-{evidence_id}"
        )
        evidence_api_object = github.comment(authority.github, evidence_id)
        errors.extend(
            _comment_errors(
                evidence_api_object,
                authority=authority,
                comment_id=evidence_id,
                expected_url=evidence_url,
                expected_author=None,
            )
        )
        if errors:
            return errors
        evidence_document = _canonical_document(
            evidence_api_object.get("body"), sentinel=EVIDENCE_SENTINEL
        )
        errors.extend(
            validate_evidence_document(
                evidence_document,
                authority=authority,
                expected_head=expected_head,
                active_assignment=active,
                comment_author=_nested(evidence_api_object, "user", "login"),
            )
        )
        return errors
    except (GitHubApiError, OSError, ValueError) as exc:
        return [f"live GitHub authority validation failed: {exc}"]


def _token_from_environment() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate frozen TASK-057 evidence against live GitHub authority."
    )
    parser.add_argument("--evidence-comment", required=True)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        resolved_head = _git(ROOT, "rev-parse", "--verify", f"{args.head}^{{commit}}")
        authority = load_authority_from_git(ROOT, head=resolved_head)
        resolved_base = _git(ROOT, "rev-parse", "--verify", f"{args.base_ref}^{{commit}}")
        if resolved_base != authority.expected_base:
            raise ValueError("base-ref does not resolve to the frozen expected Base")
        merge_base = _git(ROOT, "merge-base", resolved_base, resolved_head)
        if merge_base != authority.expected_base:
            raise ValueError("expected Base is not the exact merge-base of the validated Head")
        errors = validate_live_environment(
            authority=authority,
            expected_head=resolved_head,
            evidence_comment=args.evidence_comment,
            github=GitHubApiClient(token=_token_from_environment()),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Agent environment validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Agent environment validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Agent environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
