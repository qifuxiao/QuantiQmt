"""Validate normative specifications and AI task metadata."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator  # type: ignore[import-untyped,unused-ignore]

ROOT = Path(__file__).resolve().parents[1]
GIT_ROOT = ROOT
SPEC_ROOT = ROOT / "spec"
TASK_ROOT = ROOT / "tasks"
TASK_STATES = {"blocked", "ready", "active", "completed"}
DELIVERY_AXES = {
    "contract_status": {"not_applicable", "draft", "accepted", "superseded"},
    "implementation_status": {"not_applicable", "not_started", "in_progress", "merged"},
    "acceptance_status": {"not_run", "partial", "passed", "unverified"},
    "review_status": {
        "not_required",
        "pending",
        "changes_requested",
        "approved",
        "reported_unverified",
    },
    "release_status": {"not_applicable", "prohibited", "eligible", "released"},
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"^https?://[^\s]+$")
PR_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/\d+$")
GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
COMPLETION_FIELDS = {
    "mode",
    "change_pr",
    "reviewed_head_sha",
    "review_verdict",
    "reviewer",
    "evidence_url",
    "merge_commit_sha",
    "human_authorization_evidence",
}
WAIVER_LIFECYCLE_STATES = {"active", "retired", "expired"}
L4_READINESS_SUCCESSOR = "TASK-046"
L4_SUCCESSOR_TASKS = frozenset(
    {"TASK-017", "TASK-018", "TASK-019", "TASK-020", "TASK-021", "TASK-022"}
)
RISK_SCOPE_SUCCESSOR = "TASK-051"
RISK_HISTORICAL_SCOPE_TASK = "TASK-030"
RISK_SCOPE_REQUIRED_DEPENDENCIES = frozenset({"TASK-015", "TASK-031", "TASK-051"})
RISK_SCOPE_GOVERNANCE_PATH = (
    ROOT / "ai" / "governance" / "risk-validator-integration-scope-task-051.yaml"
)
RISK_SCOPE_BASE_SHA = "63b4c26c3da18b531bfa41f09a624d70dbddecdd"
RISK_SCOPE_TASK053_HEAD_SHA = "89b784116816cf9ac96d59d0a3b52918ae686e1b"
RISK_SCOPE_TASK052_MERGE_SHA = "c3816482f207b985a6c704a66c6c0e0a07f3632d"
RISK_SCOPE_TASK050_MERGE_SHA = "bfa77268941f3814d1856c59094fd8a90e3cda81"
RISK_SCOPE_ACCEPTED_SPEC_VERSION = "0.14.0"
RISK_SCOPE_REPOSITORY = "qifuxiao/QuantiQmt"
RISK_SCOPE_PR_NUMBER = 87
RISK_SCOPE_PR_URL = "https://github.com/qifuxiao/QuantiQmt/pull/87"
RISK_SCOPE_IMPLEMENTING_AGENT = "codex-task-051-implementing-agent"
RISK_SCOPE_PR_AUTHOR = "qifuxiao"
RISK_SCOPE_EXTERNAL_FACT_STATUS = "recorded_after_github_and_human_verification"
RISK_SCOPE_COMPLETION_MODE = "governance_closeout_after_independent_review"
RISK_SCOPE_PENDING_REVIEWER = "pending_independent_github_reviewer"
RISK_SCOPE_PENDING_REVIEWED_HEAD = "pending_exact_reviewed_head"
RISK_SCOPE_PENDING_REVIEW_URL = "pending_github_pull_request_review_url"
RISK_SCOPE_PENDING_MERGE = "pending_merge_commit"
RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION = "pending_human_closeout_authorization"
RISK_SCOPE_EXTERNAL_TIMEOUT_SECONDS = 2.0
RISK_SCOPE_MAX_RESPONSE_BYTES = 512 * 1024
RISK_SCOPE_MAX_REVIEW_PAGES = 10
RISK_SCOPE_MAX_REVIEW_ITEMS = 1000
RISK_SCOPE_GITHUB_API_PR_URL = "https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/87"
RISK_SCOPE_GITHUB_API_REVIEWS_URL = f"{RISK_SCOPE_GITHUB_API_PR_URL}/reviews?per_page=100"
RISK_SCOPE_GITHUB_API_ISSUE_URL = "https://api.github.com/repos/qifuxiao/QuantiQmt/issues/87"
RISK_SCOPE_GITHUB_API_COMPARE_PREFIX = "https://api.github.com/repos/qifuxiao/QuantiQmt/compare"
RISK_SCOPE_GITHUB_API_REVIEW_MERGE_COMPARE_ENDPOINT = (
    f"{RISK_SCOPE_GITHUB_API_COMPARE_PREFIX}/"
    "{reviewed_head_sha}...{merge_commit_sha}?per_page=1&page=1"
)
RISK_SCOPE_GITHUB_API_MERGE_MAIN_COMPARE_ENDPOINT = (
    f"{RISK_SCOPE_GITHUB_API_COMPARE_PREFIX}/{{merge_commit_sha}}...main?per_page=1&page=1"
)
RISK_SCOPE_HEAD_REF = "codex/task-051-risk-validator-scope-successor"
RISK_SCOPE_HUMAN_AUTHORIZERS = frozenset({"qifuxiao"})
RISK_HISTORICAL_TASK_BLOB_OID = "4cc37f6d1805d98bc4f223bfe69d4de5c51b7f8e"
RISK_SCOPE_BOUNDARY_REQUIREMENTS = {
    "verifies": {
        "completion evidence exactly matches this TASK-051 binding",
        "repository and change PR are qifuxiao/QuantiQmt PR 87",
        "Review evidence URL ID exactly matches a PR 87 GitHub Review API object",
        "reviewer is a valid bound GitHub login distinct from implementation agent and PR author",
        "reviewed Head and merge commit are non-placeholder 40-character hexadecimal SHAs",
        "external facts have been recorded as verified before dependency unlock",
        "human closeout authorization is an exact PR 87 GitHub issue comment object",
    },
    "does_not_verify": {
        "GitHub account ownership beyond API object identity and User type",
        "authorization intent beyond the exact required closeout body",
    },
    "external_confirmation_required": {
        "fixed GitHub verifier confirms latest effective Review state on the exact Head",
        "fixed GitHub verifier confirms merge ancestry and exact human authorization object",
    },
}
RISK_HISTORICAL_DELIVERY = {
    "schema_version": 1,
    "contract_status": "accepted",
    "implementation_status": "merged",
    "acceptance_status": "unverified",
    "review_status": "reported_unverified",
    "release_status": "prohibited",
    "remediation_task": "TASK-031",
}
RISK_HISTORICAL_COMPLETION_EVIDENCE = {
    "mode": "historical_git_verified_review_unavailable",
    "change_pr": "https://github.com/qifuxiao/QuantiQmt/pull/44",
    "reviewed_head_sha": "e7c087fc1292f1c57d8352112802ed60f99e9466",
    "review_verdict": "reported_unverified",
    "reviewer": "unverifiable",
    "evidence_url": "unverifiable",
    "merge_commit_sha": "238b0ac2c3c82de88c59a900feca8cbb71d38863",
    "human_authorization_evidence": "unverifiable",
}


@dataclass(frozen=True)
class GitHubJsonResponse:
    """One bounded GitHub JSON response and its validated pagination link."""

    payload: object
    final_url: str
    next_url: str | None


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class GitHubJsonTransport:
    """Bounded, read-only transport for the GitHub facts used by TASK-051."""

    def __init__(self, *, opener: Any | None = None, max_response_bytes: int | None = None) -> None:
        self._opener = opener or urllib.request.build_opener(_RejectRedirects())
        requested_bound = (
            RISK_SCOPE_MAX_RESPONSE_BYTES if max_response_bytes is None else int(max_response_bytes)
        )
        self._max_response_bytes = min(max(requested_bound, 1), RISK_SCOPE_MAX_RESPONSE_BYTES)

    @staticmethod
    def _next_link(headers: Any) -> str | None:
        raw_link = headers.get("Link") if hasattr(headers, "get") else None
        if raw_link is None:
            return None
        if not isinstance(raw_link, str):
            raise ValueError("GitHub Link header must be text")
        next_urls: list[str] = []
        for part in raw_link.split(","):
            match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', part)
            if match is None:
                raise ValueError("malformed GitHub Link header")
            if match.group(2) == "next":
                next_urls.append(match.group(1))
        if len(next_urls) > 1:
            raise ValueError("duplicate GitHub next link")
        return next_urls[0] if next_urls else None

    def get_json(self, url: str, timeout_seconds: float) -> GitHubJsonResponse:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("GitHub API URL is not allowed")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "QuantiQmt-task-051-validator",
            },
        )
        with self._opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise urllib.error.HTTPError(
                    url, response.status, "unexpected GitHub response", response.headers, None
                )
            if response.geturl() != url:
                raise ValueError("GitHub response final URL does not match request")
            body = response.read(self._max_response_bytes + 1)
            if len(body) > self._max_response_bytes:
                raise ValueError("GitHub response exceeds maximum bytes")
            payload = json.loads(body.decode("utf-8"))
            if payload is None:
                raise ValueError("GitHub JSON response must not be null")
            return GitHubJsonResponse(
                payload=payload,
                final_url=url,
                next_url=self._next_link(response.headers),
            )


class GitHubRiskScopeVerifier:
    """Verify TASK-051 facts through a fixed GitHub API contract.

    The only test seam is the concrete JSON transport; callers cannot inject a
    predicate or otherwise decide the result. Network and malformed responses
    fail closed.
    """

    def __init__(
        self,
        *,
        transport: GitHubJsonTransport | None = None,
        timeout_seconds: float = RISK_SCOPE_EXTERNAL_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport or GitHubJsonTransport()
        self._timeout_seconds = min(max(float(timeout_seconds), 0.1), 2.0)

    def _git_returncode(self, *arguments: str) -> int | None:
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=GIT_ROOT,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.returncode

    def _local_git_relationships_do_not_contradict(
        self, reviewed_head: str, merge_commit: str
    ) -> bool:
        """Use available local objects as an extra check, never as shallow-clone authority."""
        reviewed_available = (
            self._git_returncode("cat-file", "-e", f"{reviewed_head}^{{commit}}") == 0
        )
        merge_available = self._git_returncode("cat-file", "-e", f"{merge_commit}^{{commit}}") == 0
        main_available = self._git_returncode("cat-file", "-e", "origin/main^{commit}") == 0
        if (
            reviewed_available
            and merge_available
            and self._git_returncode("merge-base", "--is-ancestor", reviewed_head, merge_commit)
            != 0
        ):
            return False
        return not (
            merge_available
            and main_available
            and self._git_returncode("merge-base", "--is-ancestor", merge_commit, "origin/main")
            != 0
        )

    @staticmethod
    def _compare_url(base: str, head: str) -> str:
        if SHA_RE.fullmatch(base) is None or (head != "main" and SHA_RE.fullmatch(head) is None):
            raise ValueError("compare refs must be bound SHAs or fixed main")
        return f"{RISK_SCOPE_GITHUB_API_COMPARE_PREFIX}/{base}...{head}?per_page=1&page=1"

    def _verify_external_ancestor(self, ancestor: str, descendant: str) -> bool:
        url = self._compare_url(ancestor, descendant)
        response = self._transport.get_json(url, self._timeout_seconds)
        comparison = self._response_payload(response, url)
        if not isinstance(comparison, dict):
            return False
        base_commit = comparison.get("base_commit")
        merge_base = comparison.get("merge_base_commit")
        commits = comparison.get("commits")
        status = comparison.get("status")
        ahead_by = comparison.get("ahead_by")
        behind_by = comparison.get("behind_by")
        total_commits = comparison.get("total_commits")
        if not (
            status in {"ahead", "identical"}
            and type(ahead_by) is int
            and type(behind_by) is int
            and type(total_commits) is int
            and ahead_by >= 0
            and behind_by == 0
            and total_commits >= 0
            and isinstance(base_commit, dict)
            and base_commit.get("sha") == ancestor
            and isinstance(merge_base, dict)
            and merge_base.get("sha") == ancestor
            and isinstance(commits, list)
            and len(commits) <= 1
            and all(
                isinstance(commit, dict) and SHA_RE.fullmatch(str(commit.get("sha"))) is not None
                for commit in commits
            )
            and comparison.get("url") == url.split("?", maxsplit=1)[0]
            and comparison.get("html_url")
            == f"https://github.com/qifuxiao/QuantiQmt/compare/{ancestor}...{descendant}"
        ):
            return False
        if status == "identical":
            return ahead_by == 0 and total_commits == 0 and not commits
        if descendant == "main":
            return ahead_by > 0 and total_commits > 0
        return (
            ahead_by == 1
            and total_commits == 1
            and len(commits) == 1
            and isinstance(commits[0], dict)
            and commits[0].get("sha") == descendant
        )

    @staticmethod
    def _response_payload(response: object, expected_url: str) -> object:
        if not isinstance(response, GitHubJsonResponse) or response.final_url != expected_url:
            raise ValueError("unexpected GitHub transport response")
        return response.payload

    @staticmethod
    def _review_page_number(url: str) -> int:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.github.com"
            or parsed.path != "/repos/qifuxiao/QuantiQmt/pulls/87/reviews"
            or parsed.fragment
        ):
            raise ValueError("review next link escaped the fixed endpoint")
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        if set(query) - {"per_page", "page"} or query.get("per_page") != ["100"]:
            raise ValueError("review next link has invalid pagination parameters")
        page_values = query.get("page", ["1"])
        if len(page_values) != 1 or re.fullmatch(r"[1-9][0-9]*", page_values[0]) is None:
            raise ValueError("review next link has invalid page")
        return int(page_values[0])

    def _get_all_reviews(self) -> list[dict[str, Any]]:
        url: str | None = RISK_SCOPE_GITHUB_API_REVIEWS_URL
        expected_page = 1
        seen: set[str] = set()
        reviews: list[dict[str, Any]] = []
        for _ in range(RISK_SCOPE_MAX_REVIEW_PAGES):
            if url is None or url in seen or self._review_page_number(url) != expected_page:
                raise ValueError("invalid or cyclic review pagination")
            seen.add(url)
            response = self._transport.get_json(url, self._timeout_seconds)
            payload = self._response_payload(response, url)
            if not isinstance(payload, list) or len(payload) > 100:
                raise ValueError("invalid review page")
            if not all(isinstance(item, dict) for item in payload):
                raise ValueError("review page contains non-object item")
            reviews.extend(payload)
            if len(reviews) > RISK_SCOPE_MAX_REVIEW_ITEMS:
                raise ValueError("review item limit exceeded")
            if response.next_url is None:
                return reviews
            url = response.next_url
            expected_page += 1
        raise ValueError("review page limit exceeded")

    @staticmethod
    def _parse_submitted_at(value: Any) -> datetime:
        if (
            not isinstance(value, str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value) is None
        ):
            raise ValueError("review submitted_at is missing or malformed")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo != UTC:
            raise ValueError("review submitted_at must be UTC")
        return parsed

    def _verify_reviews(
        self,
        reviews: list[dict[str, Any]],
        *,
        reviewer: str,
        reviewed_head: str,
        evidence_url: str,
        evidence_id: int,
        identity: dict[str, Any],
    ) -> bool:
        allowed_states = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}
        decisive_states = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
        seen_ids: set[int] = set()
        decisive_by_reviewer: dict[str, tuple[datetime, int, dict[str, Any]]] = {}
        review_by_id: dict[int, dict[str, Any]] = {}
        for item in reviews:
            review_id = item.get("id")
            state = item.get("state")
            user = item.get("user")
            if (
                type(review_id) is not int
                or review_id <= 0
                or review_id in seen_ids
                or state not in allowed_states
                or not isinstance(user, dict)
                or not isinstance(user.get("login"), str)
                or user.get("type") not in {"User", "Bot"}
                or item.get("pull_request_url") != RISK_SCOPE_GITHUB_API_PR_URL
                or item.get("html_url") != f"{RISK_SCOPE_PR_URL}#pullrequestreview-{review_id}"
                or SHA_RE.fullmatch(str(item.get("commit_id"))) is None
            ):
                return False
            submitted_at = self._parse_submitted_at(item.get("submitted_at"))
            seen_ids.add(review_id)
            review_by_id[review_id] = item
            if state == "PENDING":
                return False
            if state in decisive_states:
                key = (submitted_at, review_id, item)
                reviewer_key = user["login"].casefold()
                previous = decisive_by_reviewer.get(reviewer_key)
                if previous is None or key[:2] > previous[:2]:
                    decisive_by_reviewer[reviewer_key] = key
        if any(
            item[2].get("state") == "CHANGES_REQUESTED" for item in decisive_by_reviewer.values()
        ):
            return False
        effective_approvals = [
            item[2]
            for login, item in decisive_by_reviewer.items()
            if item[2].get("state") == "APPROVED"
            and item[2].get("commit_id") == reviewed_head
            and item[2].get("user", {}).get("type") == "User"
            and github_reviewer_is_independent(login, identity)
        ]
        matched = review_by_id.get(evidence_id)
        return (
            bool(effective_approvals)
            and matched in effective_approvals
            and matched is not None
            and matched.get("html_url") == evidence_url
            and matched.get("user", {}).get("login") == reviewer
        )

    def _verify_human_authorization(
        self,
        authorization: dict[str, Any],
        *,
        reviewed_head: str,
        merge_commit: str,
    ) -> bool:
        object_id = authorization.get("object_id")
        evidence_url = authorization.get("evidence_url")
        author = authorization.get("author")
        required_body = authorization.get("required_body")
        if type(object_id) is not int or object_id <= 0:
            return False
        expected_url = f"{RISK_SCOPE_PR_URL}#issuecomment-{object_id}"
        expected_body = (
            "AUTHORIZE TASK-051 CLOSEOUT\n"
            f"reviewed_head_sha: {reviewed_head}\n"
            f"merge_commit_sha: {merge_commit}"
        )
        if (
            authorization.get("object_type") != "issue_comment"
            or evidence_url != expected_url
            or not isinstance(author, str)
            or author.casefold() not in {value.casefold() for value in RISK_SCOPE_HUMAN_AUTHORIZERS}
            or required_body != expected_body
        ):
            return False
        api_url = f"https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/{object_id}"
        response = self._transport.get_json(api_url, self._timeout_seconds)
        comment = self._response_payload(response, api_url)
        user = comment.get("user") if isinstance(comment, dict) else None
        return bool(
            isinstance(comment, dict)
            and type(comment.get("id")) is int
            and comment.get("id") == object_id
            and comment.get("html_url") == evidence_url
            and comment.get("issue_url") == RISK_SCOPE_GITHUB_API_ISSUE_URL
            and comment.get("body") == required_body
            and isinstance(user, dict)
            and user.get("login") == author
            and user.get("type") == "User"
        )

    def verify(self, binding: dict[str, Any], evidence: dict[str, Any]) -> bool:
        try:
            review = binding["required_review"]
            merge = binding["required_merge"]
            identity = binding["implementation_identity"]
            reviewer = review["reviewer"]
            reviewed_head = review["reviewed_head_sha"]
            merge_commit = merge["merge_commit_sha"]
            evidence_url = review["evidence_url"]
            human_auth = binding["human_authorization_evidence"]
            if not all(
                isinstance(value, str)
                for value in (reviewer, reviewed_head, merge_commit, evidence_url)
            ):
                return False
            if reviewed_head == merge_commit:
                return False
            if not isinstance(human_auth, dict):
                return False
            review_match = re.fullmatch(
                rf"{re.escape(RISK_SCOPE_PR_URL)}#pullrequestreview-([1-9][0-9]*)",
                evidence_url,
            )
            if review_match is None:
                return False
            review_id = int(review_match.group(1))
            pull_response = self._transport.get_json(
                RISK_SCOPE_GITHUB_API_PR_URL, self._timeout_seconds
            )
            pull = self._response_payload(pull_response, RISK_SCOPE_GITHUB_API_PR_URL)
            reviews = self._get_all_reviews()
            if not isinstance(pull, dict):
                return False
            base = pull.get("base")
            head = pull.get("head")
            author = pull.get("user")
            merged_by = pull.get("merged_by")
            if not (
                pull.get("html_url") == RISK_SCOPE_PR_URL
                and pull.get("number") == RISK_SCOPE_PR_NUMBER
                and pull.get("state") == "closed"
                and pull.get("merged") is True
                and isinstance(base, dict)
                and base.get("ref") == "main"
                and isinstance(base.get("repo"), dict)
                and base["repo"].get("full_name") == RISK_SCOPE_REPOSITORY
                and isinstance(head, dict)
                and head.get("sha") == reviewed_head
                and head.get("ref") == RISK_SCOPE_HEAD_REF
                and isinstance(head.get("repo"), dict)
                and head["repo"].get("full_name") == RISK_SCOPE_REPOSITORY
                and pull.get("merge_commit_sha") == merge_commit
                and isinstance(author, dict)
                and author.get("login") == RISK_SCOPE_PR_AUTHOR
                and isinstance(merged_by, dict)
                and isinstance(merged_by.get("login"), str)
                and merged_by.get("type") == "User"
            ):
                return False
            if not self._verify_reviews(
                reviews,
                reviewer=reviewer,
                reviewed_head=reviewed_head,
                evidence_url=evidence_url,
                evidence_id=review_id,
                identity=identity,
            ):
                return False
            if not self._verify_external_ancestor(reviewed_head, merge_commit):
                return False
            if not self._verify_external_ancestor(merge_commit, "main"):
                return False
            return self._verify_human_authorization(
                human_auth, reviewed_head=reviewed_head, merge_commit=merge_commit
            ) and self._local_git_relationships_do_not_contradict(reviewed_head, merge_commit)
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ):
            return False


def load_yaml(path: Path) -> Any:
    """Load one YAML document."""
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_json(path: Path) -> Any:
    """Load one JSON document."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def git_blob_oid(content: bytes) -> str:
    """Return the Git blob object ID for exact file bytes."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def extract_front_matter(path: Path) -> dict[str, Any]:
    """Parse YAML front matter from a Markdown task."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if match is None:
        raise ValueError("missing YAML front matter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("front matter must be a mapping")
    return value


def manifest_entries(manifest: dict[str, Any]) -> dict[str, Path]:
    """Return all manifest IDs and their resolved paths."""
    result: dict[str, Path] = {}
    catalogs = manifest.get("catalogs")
    if not isinstance(catalogs, dict):
        return result
    for entries in catalogs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            spec_id = entry.get("id")
            relative_path = entry.get("path")
            if isinstance(spec_id, str) and isinstance(relative_path, str):
                result[spec_id] = SPEC_ROOT / relative_path
    return result


def has_cycle(graph: dict[str, list[str]]) -> bool:
    """Return True when a dependency graph contains a cycle."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def task_files() -> Iterable[Path]:
    """Yield executable task Markdown files."""
    for state in ("backlog", "active", "completed"):
        yield from sorted((TASK_ROOT / state).glob("TASK-*.md"))


def validate_delivery(task_id: str, task: dict[str, Any], path: Path, errors: list[str]) -> None:
    """Validate the independent governance delivery axes and evidence."""
    delivery = task.get("delivery")
    if delivery is None:
        if task.get("status") == "completed":
            errors.append(f"{path.relative_to(ROOT)}: completed task requires delivery metadata")
        return
    if not isinstance(delivery, dict) or delivery.get("schema_version") != 1:
        errors.append(f"{path.relative_to(ROOT)}: delivery.schema_version must be 1")
        return
    for axis, allowed in DELIVERY_AXES.items():
        if delivery.get(axis) not in allowed:
            errors.append(f"{path.relative_to(ROOT)}: invalid delivery {axis}")
    status = task.get("status")
    review = delivery.get("review_status")
    release = delivery.get("release_status")
    if (
        status == "completed"
        and review != "reported_unverified"
        and (
            delivery.get("acceptance_status") != "passed"
            or delivery.get("review_status") not in {"approved", "not_required"}
            or delivery.get("implementation_status") not in {"merged", "not_applicable"}
        )
    ):
        errors.append(f"{path.relative_to(ROOT)}: completed task has invalid delivery combination")
    if review == "reported_unverified":
        if release != "prohibited":
            errors.append(
                f"{path.relative_to(ROOT)}: reported_unverified requires prohibited release"
            )
        if not delivery.get("remediation_task") and not delivery.get("waiver_id"):
            errors.append(
                f"{path.relative_to(ROOT)}: reported_unverified requires remediation_task "
                "or waiver_id"
            )
    if release in {"eligible", "released"} and review == "reported_unverified":
        errors.append(f"{path.relative_to(ROOT)}: unverifiable review cannot unlock or release")
    if status == "completed":
        body = path.read_text(encoding="utf-8")
        if "## Acceptance criteria" not in body:
            errors.append(f"{path.relative_to(ROOT)}: completed task lacks Acceptance criteria")
        elif review != "reported_unverified" and "[x]" not in body:
            errors.append(
                f"{path.relative_to(ROOT)}: completed task lacks checked acceptance evidence"
            )
        evidence = delivery.get("completion_evidence")
        if not isinstance(evidence, dict) or not COMPLETION_FIELDS.issubset(evidence):
            errors.append(f"{path.relative_to(ROOT)}: incomplete completion_evidence")
        else:
            for field in COMPLETION_FIELDS:
                if not isinstance(evidence.get(field), str) or not evidence[field].strip():
                    errors.append(f"{path.relative_to(ROOT)}: empty completion evidence {field}")
            if review == "reported_unverified":
                if evidence.get("review_verdict") != "reported_unverified":
                    errors.append(
                        f"{path.relative_to(ROOT)}: unverified evidence requires "
                        "reported_unverified verdict"
                    )
            else:
                if evidence.get("review_verdict") not in {"APPROVE", "NOT_REQUIRED"}:
                    errors.append(
                        f"{path.relative_to(ROOT)}: review_verdict must be APPROVE or NOT_REQUIRED"
                    )
                for field in ("reviewed_head_sha", "merge_commit_sha"):
                    if not SHA_RE.fullmatch(str(evidence.get(field))):
                        errors.append(f"{path.relative_to(ROOT)}: invalid evidence SHA {field}")
                if not PR_RE.fullmatch(str(evidence.get("change_pr"))):
                    errors.append(f"{path.relative_to(ROOT)}: change_pr must be a GitHub PR URL")
                if not URL_RE.fullmatch(str(evidence.get("evidence_url"))):
                    errors.append(f"{path.relative_to(ROOT)}: evidence_url must be an HTTP(S) URL")
                if evidence.get("reviewer") in {"unverifiable", "reported_unverified"}:
                    errors.append(
                        f"{path.relative_to(ROOT)}: approved evidence requires a reviewer"
                    )


def validate_waiver_entries(
    waivers: list[Any],
    known_task_ids: set[str],
    errors: list[str],
    today: date | None = None,
    task_statuses: dict[str, str] | None = None,
) -> None:
    today = today or date.today()
    required = {
        "task_id",
        "beneficiary_task",
        "rule",
        "reason",
        "owner",
        "expires_on",
        "remediation_task",
        "release_status",
        "kind",
        "one_time",
        "deny_business_unlock",
        "lifecycle_status",
    }
    bootstrap_count = sum(
        isinstance(waiver, dict) and waiver.get("kind") == "bootstrap_exception"
        for waiver in waivers
    )
    if bootstrap_count != 1:
        errors.append("tasks/governance-waivers.yaml: exactly one bootstrap_exception is required")
    expected_bootstrap = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
    }
    for waiver in waivers:
        if not isinstance(waiver, dict) or not required.issubset(waiver):
            errors.append("tasks/governance-waivers.yaml: waiver missing required fields")
            continue
        for field in required - {"one_time", "deny_business_unlock"}:
            if not isinstance(waiver.get(field), str) or not waiver[field].strip():
                errors.append(
                    f"tasks/governance-waivers.yaml: waiver field {field} must be non-empty"
                )
        if waiver.get("task_id") not in known_task_ids:
            errors.append(f"tasks/governance-waivers.yaml: unknown task_id {waiver.get('task_id')}")
        if waiver.get("remediation_task") not in known_task_ids:
            errors.append(
                "tasks/governance-waivers.yaml: unknown remediation_task "
                f"{waiver.get('remediation_task')}"
            )
        if waiver.get("beneficiary_task") not in known_task_ids:
            errors.append(
                "tasks/governance-waivers.yaml: unknown beneficiary_task "
                f"{waiver.get('beneficiary_task')}"
            )
        if not isinstance(waiver.get("one_time"), bool) or not isinstance(
            waiver.get("deny_business_unlock"), bool
        ):
            errors.append("tasks/governance-waivers.yaml: bootstrap flags must be boolean")
        if waiver.get("release_status") != "prohibited":
            errors.append("tasks/governance-waivers.yaml: waiver release_status must be prohibited")
        try:
            expires = date.fromisoformat(str(waiver["expires_on"]))
        except ValueError:
            errors.append(
                f"tasks/governance-waivers.yaml: invalid expires_on for {waiver.get('task_id')}"
            )
            expires = None
        lifecycle = waiver.get("lifecycle_status")
        if lifecycle not in WAIVER_LIFECYCLE_STATES:
            errors.append(
                "tasks/governance-waivers.yaml: lifecycle_status must be active, retired, "
                "or expired"
            )
        elif lifecycle == "active":
            if expires is not None and expires < today:
                errors.append(
                    "tasks/governance-waivers.yaml: active waiver is past expires_on and "
                    "must transition to expired"
                )
            if "retired_on" in waiver or "expired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: active waiver cannot have terminal dates"
                )
            if task_statuses is not None and any(
                task_statuses.get(str(waiver.get(field))) == "completed"
                for field in ("beneficiary_task", "remediation_task")
            ):
                errors.append(
                    "tasks/governance-waivers.yaml: completed remediation requires retired "
                    "waiver lifecycle"
                )
        elif lifecycle == "retired":
            retired_on = parse_waiver_transition_date(waiver, "retired_on", errors)
            if retired_on is not None and retired_on > today:
                errors.append("tasks/governance-waivers.yaml: retired_on cannot be in the future")
            if "expired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: retired waiver cannot have expired_on"
                )
            if (
                task_statuses is not None
                and task_statuses.get(str(waiver.get("remediation_task"))) != "completed"
            ):
                errors.append(
                    "tasks/governance-waivers.yaml: retired waiver remediation_task must be "
                    "completed"
                )
        elif lifecycle == "expired":
            expired_on = parse_waiver_transition_date(waiver, "expired_on", errors)
            if expired_on is not None:
                if expires is not None and expired_on <= expires:
                    errors.append(
                        "tasks/governance-waivers.yaml: expired_on must be after expires_on"
                    )
                if expired_on > today:
                    errors.append(
                        "tasks/governance-waivers.yaml: expired_on cannot be in the future"
                    )
            if "retired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: expired waiver cannot have retired_on"
                )
        if waiver.get("release_status") in {"eligible", "released"}:
            errors.append("tasks/governance-waivers.yaml: waiver cannot permit release")
        if waiver.get("kind") == "bootstrap_exception":
            for field, expected in expected_bootstrap.items():
                if waiver.get(field) != expected:
                    errors.append(
                        "tasks/governance-waivers.yaml: bootstrap field "
                        f"{field} must equal {expected}"
                    )
        elif any(
            field in waiver for field in ("beneficiary_task", "one_time", "deny_business_unlock")
        ):
            errors.append(
                "tasks/governance-waivers.yaml: ordinary waiver cannot carry bootstrap fields"
            )


def parse_waiver_transition_date(
    waiver: dict[str, Any], field: str, errors: list[str]
) -> date | None:
    """Parse a required terminal waiver date without accepting empty or invalid values."""
    value = waiver.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"tasks/governance-waivers.yaml: {field} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"tasks/governance-waivers.yaml: invalid {field}")
        return None


def validate_waivers(errors: list[str]) -> None:
    path = TASK_ROOT / "governance-waivers.yaml"
    if not path.is_file():
        errors.append("tasks/governance-waivers.yaml: required governance waiver registry missing")
        return
    document = load_yaml(path)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        errors.append("tasks/governance-waivers.yaml: schema_version must be 1")
        return
    waivers = document.get("waivers", [])
    if not isinstance(waivers, list):
        errors.append("tasks/governance-waivers.yaml: waivers must be a list")
        return
    task_statuses: dict[str, str] = {}
    for task_path in task_files():
        task = extract_front_matter(task_path)
        task_id = task.get("id")
        status = task.get("status")
        if isinstance(task_id, str) and isinstance(status, str):
            task_statuses[task_id] = status
    validate_waiver_entries(waivers, set(task_statuses), errors, task_statuses=task_statuses)


def validate_active_readme(tasks: dict[str, dict[str, Any]], errors: list[str]) -> None:
    path = TASK_ROOT / "active" / "README.md"
    if not path.is_file():
        errors.append("tasks/active/README.md: missing active projection")
        return
    text = path.read_text(encoding="utf-8")
    listed = set(re.findall(r"当前 active task.\s*(TASK-\d{3})", text))
    listed.update(re.findall(r"(?m)^\s*[-*]\s*(TASK-\d{3})\b", text))
    expected = {task_id for task_id, task in tasks.items() if task.get("status") == "active"}
    if listed != expected:
        errors.append(
            "tasks/active/README.md: active projection mismatch "
            f"(listed={sorted(listed)}, expected={sorted(expected)})"
        )


def delivery_is_unlockable(
    task: dict[str, Any],
    *,
    task_id: str | None = None,
    evidence_binding: dict[str, Any] | None = None,
    external_verifier: GitHubRiskScopeVerifier | None = None,
) -> bool:
    delivery = task.get("delivery")
    resolved_task_id = task_id or task.get("id")
    generally_unlockable = (
        isinstance(delivery, dict)
        and delivery.get("schema_version") == 1
        and delivery.get("implementation_status") in {"merged", "not_applicable"}
        and delivery.get("acceptance_status") == "passed"
        and delivery.get("review_status") in {"approved", "not_required"}
        and delivery.get("release_status") in {"prohibited", "eligible", "released"}
        and completion_evidence_is_trusted(
            delivery,
            task_id=resolved_task_id,
            evidence_binding=evidence_binding,
            external_verifier=external_verifier,
        )
    )
    if not generally_unlockable:
        return False
    if resolved_task_id == RISK_SCOPE_SUCCESSOR:
        if not isinstance(delivery, dict):
            return False
        return task051_completion_evidence_is_bound(delivery, evidence_binding, external_verifier)
    return True


def completion_evidence_is_trusted(
    delivery: dict[str, Any],
    *,
    task_id: str | None = None,
    evidence_binding: dict[str, Any] | None = None,
    external_verifier: GitHubRiskScopeVerifier | None = None,
) -> bool:
    evidence = delivery.get("completion_evidence")
    if not isinstance(evidence, dict) or not COMPLETION_FIELDS.issubset(evidence):
        return False
    if any(
        not isinstance(evidence.get(field), str) or not evidence[field].strip()
        for field in COMPLETION_FIELDS
    ):
        return False
    if evidence.get("review_verdict") not in {"APPROVE", "NOT_REQUIRED"}:
        return False
    generally_trusted = (
        SHA_RE.fullmatch(str(evidence.get("reviewed_head_sha"))) is not None
        and SHA_RE.fullmatch(str(evidence.get("merge_commit_sha"))) is not None
        and PR_RE.fullmatch(str(evidence.get("change_pr"))) is not None
        and URL_RE.fullmatch(str(evidence.get("evidence_url"))) is not None
        and evidence.get("reviewer") not in {"unverifiable", "reported_unverified"}
    )
    if not generally_trusted:
        return False
    if task_id == RISK_SCOPE_SUCCESSOR:
        return task051_completion_evidence_is_bound(delivery, evidence_binding, external_verifier)
    return True


def load_risk_scope_evidence_binding(errors: list[str]) -> dict[str, Any] | None:
    """Load the static TASK-051 evidence binding without claiming external verification."""
    try:
        document = load_yaml(RISK_SCOPE_GOVERNANCE_PATH)
    except Exception as exc:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            f"required TASK-051 evidence binding is unavailable: {exc}"
        )
        return None
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: schema_version must be 1"
        )
        return None
    if document.get("audit_task") != RISK_SCOPE_SUCCESSOR:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "audit_task must be TASK-051"
        )
    repository = document.get("repository")
    if not isinstance(repository, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "repository baseline must be present"
        )
    else:
        expected_repository = {
            "base_branch": "origin/main",
            "base_sha": RISK_SCOPE_BASE_SHA,
            "implementation_branch": "codex/task-051-risk-validator-scope-successor",
        }
        for field, expected_value in expected_repository.items():
            if repository.get(field) != expected_value:
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"repository.{field} must remain {expected_value}"
                )
    concurrent_work = document.get("concurrent_work")
    if not isinstance(concurrent_work, dict) or any(
        concurrent_work.get(field) != expected_value
        for field, expected_value in {
            "observed_branch": "origin/codex/task-053-dependency-sequencing-activation",
            "observed_head_sha": RISK_SCOPE_TASK053_HEAD_SHA,
            "observed_state": "active_in_main",
            "merged_commit_sha": RISK_SCOPE_BASE_SHA,
            "paused_task": "TASK-052",
            "paused_task_path": "tasks/backlog/TASK-052-task-004-delivery-revalidation.md",
            "paused_task_state": "blocked_in_backlog",
            "paused_task_previous_merge_sha": RISK_SCOPE_TASK052_MERGE_SHA,
            "preserved_completed_task": "TASK-050",
            "preserved_completed_merge_sha": RISK_SCOPE_TASK050_MERGE_SHA,
        }.items()
    ):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "concurrent TASK-053/TASK-052 projection or preserved TASK-050 fact is stale"
        )
    authority = document.get("authority")
    accepted_spec = authority.get("accepted_spec") if isinstance(authority, dict) else None
    if (
        not isinstance(accepted_spec, dict)
        or accepted_spec.get("version") != RISK_SCOPE_ACCEPTED_SPEC_VERSION
    ):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            f"authority.accepted_spec.version must be {RISK_SCOPE_ACCEPTED_SPEC_VERSION}"
        )
    elif accepted_spec.get("status") != "accepted":
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "authority.accepted_spec.status must be accepted"
        )
    try:
        manifest = load_yaml(SPEC_ROOT / "manifest.yaml")
        manifest_spec = manifest.get("specification") if isinstance(manifest, dict) else None
        manifest_version = manifest_spec.get("version") if isinstance(manifest_spec, dict) else None
    except Exception:
        manifest_version = None
    if manifest_version != RISK_SCOPE_ACCEPTED_SPEC_VERSION:
        errors.append(
            "spec/manifest.yaml: specification.version must match the accepted TASK-051 "
            f"governance version {RISK_SCOPE_ACCEPTED_SPEC_VERSION}"
        )
        return None
    binding = document.get("successor_evidence_binding")
    if not isinstance(binding, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "successor_evidence_binding must be present"
        )
        return None
    expected = {
        "task_id": RISK_SCOPE_SUCCESSOR,
        "beneficiary_task": "TASK-029",
        "repository": RISK_SCOPE_REPOSITORY,
        "pull_request_number": RISK_SCOPE_PR_NUMBER,
        "change_pr": RISK_SCOPE_PR_URL,
    }
    for field, value in expected.items():
        if binding.get(field) != value:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"successor evidence binding {field} must equal {value}"
            )
    identity = binding.get("implementation_identity")
    if not isinstance(identity, dict) or identity.get("agent") != RISK_SCOPE_IMPLEMENTING_AGENT:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "implementation agent identity is not bound"
        )
    if not isinstance(identity, dict) or identity.get("pull_request_author") != (
        RISK_SCOPE_PR_AUTHOR
    ):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "pull request author identity is not bound"
        )
    review = binding.get("required_review")
    merge = binding.get("required_merge")
    if not isinstance(review, dict) or not isinstance(merge, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "required_review and required_merge bindings must be present"
        )
        return binding
    for field in ("verdict", "reviewer", "reviewed_head_sha", "evidence_url"):
        if field not in review:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"required_review.{field} must be present"
            )
    if "merge_commit_sha" not in merge:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "required_merge.merge_commit_sha must be present"
        )
    if binding.get("external_fact_status") not in {
        "pending_github_and_human_verification",
        RISK_SCOPE_EXTERNAL_FACT_STATUS,
    }:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "external_fact_status must remain pending or recorded-after-verification"
        )
    boundary = binding.get("static_validator_boundary")
    if not isinstance(boundary, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "static validator boundary must declare verifies and external facts"
        )
    else:
        for field, required_values in RISK_SCOPE_BOUNDARY_REQUIREMENTS.items():
            values = boundary.get(field)
            if not isinstance(values, list) or not required_values.issubset(values):
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"static validator boundary {field} is incomplete"
                )
    production_verifier = binding.get("production_external_verifier")
    if not isinstance(production_verifier, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "production external verifier must be explicitly modeled"
        )
    else:
        if production_verifier.get("adapter") != "fixed_github_public_api_task_051_verifier":
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "production verifier adapter must be the fixed GitHub adapter"
            )
        if production_verifier.get("timeout_seconds") != 2:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "production verifier timeout must be 2 seconds"
            )
        expected_endpoints = [
            RISK_SCOPE_GITHUB_API_PR_URL,
            RISK_SCOPE_GITHUB_API_REVIEWS_URL,
            "https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/{comment_id}",
            RISK_SCOPE_GITHUB_API_REVIEW_MERGE_COMPARE_ENDPOINT,
            RISK_SCOPE_GITHUB_API_MERGE_MAIN_COMPARE_ENDPOINT,
        ]
        if production_verifier.get("endpoints") != expected_endpoints:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "production verifier endpoints must remain fixed to PR 87"
            )
        expected_bounds: dict[str, object] = {
            "max_response_bytes": RISK_SCOPE_MAX_RESPONSE_BYTES,
            "max_review_pages": RISK_SCOPE_MAX_REVIEW_PAGES,
            "max_review_items": RISK_SCOPE_MAX_REVIEW_ITEMS,
            "redirect_policy": "reject_all",
            "authorization_header": "not_sent",
        }
        for bound_field, bound_value in expected_bounds.items():
            if production_verifier.get(bound_field) != bound_value:
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"production verifier {bound_field} must be {bound_value}"
                )
        if production_verifier.get("failure_policy") != (
            "network_timeout_rate_limit_404_invalid_json_or_mismatch_denies"
        ):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "production verifier must fail closed"
            )
    external_status = binding.get("external_fact_status")
    if external_status == "pending_github_and_human_verification":
        pending_values = {
            "reviewer": RISK_SCOPE_PENDING_REVIEWER,
            "reviewed_head_sha": RISK_SCOPE_PENDING_REVIEWED_HEAD,
            "evidence_url": RISK_SCOPE_PENDING_REVIEW_URL,
        }
        for field, expected_value in pending_values.items():
            if review.get(field) != expected_value:
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"pending required_review.{field} must remain {expected_value}"
                )
        if review.get("verdict") != "APPROVE":
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "required_review.verdict must remain APPROVE"
            )
        if merge.get("merge_commit_sha") != RISK_SCOPE_PENDING_MERGE:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"pending required_merge.merge_commit_sha must remain {RISK_SCOPE_PENDING_MERGE}"
            )
        if binding.get("human_authorization_evidence") != RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "pending human authorization evidence must remain the explicit placeholder"
            )
    elif external_status == RISK_SCOPE_EXTERNAL_FACT_STATUS:
        if review.get("verdict") != "APPROVE":
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded required_review.verdict must be APPROVE"
            )
        if not isinstance(review.get("reviewer"), str) or not github_reviewer_is_independent(
            review.get("reviewer"), identity
        ):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded reviewer must be a non-placeholder independent GitHub login"
            )
        if not plausible_evidence_sha(review.get("reviewed_head_sha")):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded reviewed_head_sha must be a non-placeholder SHA"
            )
        if not plausible_evidence_sha(merge.get("merge_commit_sha")):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded merge_commit_sha must be a non-placeholder SHA"
            )
        review_url_re = re.compile(
            rf"^{re.escape(RISK_SCOPE_PR_URL)}#pullrequestreview-[1-9][0-9]*$"
        )
        evidence_url = review.get("evidence_url")
        if not isinstance(evidence_url, str) or not review_url_re.fullmatch(evidence_url):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded evidence_url must identify a PR 87 review"
            )
        authorization = binding.get("human_authorization_evidence")
        if not isinstance(authorization, dict):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded human authorization must bind an external GitHub object"
            )
        else:
            object_id = authorization.get("object_id")
            expected_authorization_url = (
                f"{RISK_SCOPE_PR_URL}#issuecomment-{object_id}"
                if type(object_id) is int and object_id > 0
                else None
            )
            expected_authorization_body = (
                "AUTHORIZE TASK-051 CLOSEOUT\n"
                f"reviewed_head_sha: {review.get('reviewed_head_sha')}\n"
                f"merge_commit_sha: {merge.get('merge_commit_sha')}"
            )
            if (
                authorization.get("object_type") != "issue_comment"
                or expected_authorization_url is None
                or authorization.get("evidence_url") != expected_authorization_url
                or authorization.get("author") not in RISK_SCOPE_HUMAN_AUTHORIZERS
                or authorization.get("required_body") != expected_authorization_body
            ):
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    "recorded human authorization object is not exactly bound to TASK-051 facts"
                )
    return binding


def task051_completion_evidence_is_bound(
    delivery: dict[str, Any],
    evidence_binding: dict[str, Any] | None,
    external_verifier: GitHubRiskScopeVerifier | None = None,
    *,
    require_external: bool = True,
) -> bool:
    """Check local binding and optionally require independently supplied facts."""
    if (
        delivery.get("contract_status") != "not_applicable"
        or delivery.get("implementation_status") != "merged"
        or delivery.get("acceptance_status") != "passed"
        or delivery.get("review_status") != "approved"
        or delivery.get("release_status") != "prohibited"
    ):
        return False
    if not isinstance(evidence_binding, dict):
        return False
    if any(
        evidence_binding.get(field) != expected
        for field, expected in {
            "task_id": RISK_SCOPE_SUCCESSOR,
            "beneficiary_task": "TASK-029",
            "repository": RISK_SCOPE_REPOSITORY,
            "pull_request_number": RISK_SCOPE_PR_NUMBER,
            "change_pr": RISK_SCOPE_PR_URL,
        }.items()
    ):
        return False
    if not completion_evidence_is_trusted(delivery):
        return False
    evidence = delivery.get("completion_evidence")
    review = evidence_binding.get("required_review")
    merge = evidence_binding.get("required_merge")
    identity = evidence_binding.get("implementation_identity")
    if not all(isinstance(value, dict) for value in (evidence, review, merge, identity)):
        return False
    assert isinstance(evidence, dict)
    assert isinstance(review, dict)
    assert isinstance(merge, dict)
    assert isinstance(identity, dict)
    if (
        identity.get("agent") != RISK_SCOPE_IMPLEMENTING_AGENT
        or identity.get("pull_request_author") != RISK_SCOPE_PR_AUTHOR
    ):
        return False
    if review.get("verdict") != "APPROVE":
        return False
    if evidence_binding.get("external_fact_status") != RISK_SCOPE_EXTERNAL_FACT_STATUS:
        return False
    reviewer = review.get("reviewer")
    reviewed_head_sha = review.get("reviewed_head_sha")
    merge_commit_sha = merge.get("merge_commit_sha")
    evidence_url = review.get("evidence_url")
    human_authorization = evidence_binding.get("human_authorization_evidence")
    if not github_reviewer_is_independent(reviewer, identity):
        return False
    if not plausible_evidence_sha(reviewed_head_sha) or not plausible_evidence_sha(
        merge_commit_sha
    ):
        return False
    review_url_re = re.compile(rf"^{re.escape(RISK_SCOPE_PR_URL)}#pullrequestreview-[1-9][0-9]*$")
    if not isinstance(evidence_url, str) or review_url_re.fullmatch(evidence_url) is None:
        return False
    if not isinstance(human_authorization, dict):
        return False
    authorization_url = human_authorization.get("evidence_url")
    if (
        not isinstance(authorization_url, str)
        or re.fullmatch(
            rf"{re.escape(RISK_SCOPE_PR_URL)}#issuecomment-[1-9][0-9]*", authorization_url
        )
        is None
    ):
        return False
    expected_evidence = {
        "mode": RISK_SCOPE_COMPLETION_MODE,
        "change_pr": RISK_SCOPE_PR_URL,
        "reviewed_head_sha": reviewed_head_sha,
        "review_verdict": "APPROVE",
        "reviewer": reviewer,
        "evidence_url": evidence_url,
        "merge_commit_sha": merge_commit_sha,
        "human_authorization_evidence": authorization_url,
    }
    if not all(evidence.get(field) == value for field, value in expected_evidence.items()):
        return False
    if not require_external:
        return True
    if external_verifier is None:
        return False
    return external_verifier.verify(evidence_binding, evidence)


def plausible_evidence_sha(value: Any) -> bool:
    """Reject malformed and obvious repeated-pattern placeholder SHAs."""
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        return False
    return not any(value == value[:size] * (40 // size) for size in range(1, 21) if 40 % size == 0)


def is_placeholder_text(value: Any) -> bool:
    """Return whether governance text still carries an unresolved placeholder."""
    return (
        not isinstance(value, str)
        or not value.strip()
        or value
        in {
            "unverifiable",
            "reported_unverified",
            RISK_SCOPE_PENDING_REVIEWER,
            RISK_SCOPE_PENDING_REVIEWED_HEAD,
            RISK_SCOPE_PENDING_REVIEW_URL,
            RISK_SCOPE_PENDING_MERGE,
            RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION,
        }
        or value.startswith("pending_")
        or value.startswith("pending-")
    )


def github_reviewer_is_independent(value: Any, identity: Any) -> bool:
    """Validate reviewer syntax and keep implementation identities out of review evidence."""
    return (
        isinstance(value, str)
        and GITHUB_LOGIN_RE.fullmatch(value) is not None
        and not is_placeholder_text(value)
        and isinstance(identity, dict)
        and value.casefold()
        not in {
            str(identity.get("agent", "")).casefold(),
            str(identity.get("pull_request_author", "")).casefold(),
        }
    )


def bootstrap_allows_dependency(
    dependency: str,
    beneficiary: str,
    waivers: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> bool:
    evaluation_date = today or date.today()
    for waiver in waivers:
        try:
            expires = date.fromisoformat(str(waiver.get("expires_on")))
        except (TypeError, ValueError):
            continue
        if (
            waiver.get("kind") == "bootstrap_exception"
            and waiver.get("lifecycle_status") == "active"
            and waiver.get("one_time") is True
            and waiver.get("deny_business_unlock") is True
            and waiver.get("task_id") == dependency == "TASK-014"
            and waiver.get("beneficiary_task") == beneficiary == "TASK-031"
            and isinstance(waiver.get("rule"), str)
            and bool(waiver["rule"].strip())
            and isinstance(waiver.get("reason"), str)
            and bool(waiver["reason"].strip())
            and waiver.get("owner") == "qfxyyy"
            and expires >= evaluation_date
            and waiver.get("remediation_task") == "TASK-031"
            and waiver.get("release_status") == "prohibited"
        ):
            return True
    return False


def validate_l4_successor_dependencies(tasks: dict[str, dict[str, Any]], errors: list[str]) -> None:
    """Keep the general L4 queue on its fresh readiness gate."""
    present_successors = L4_SUCCESSOR_TASKS.intersection(tasks)
    if present_successors and L4_READINESS_SUCCESSOR not in tasks:
        errors.append(
            f"tasks: {L4_READINESS_SUCCESSOR} successor gate missing for L4 contract queue"
        )
    for task_id in sorted(present_successors):
        dependencies = tasks[task_id].get("depends_on")
        if not isinstance(dependencies, list):
            continue
        if "TASK-014" in dependencies:
            errors.append(
                f"{task_id}: historical TASK-014 readiness dependency must not remain; "
                f"use {L4_READINESS_SUCCESSOR}"
            )
        if L4_READINESS_SUCCESSOR not in dependencies:
            errors.append(
                f"{task_id}: missing {L4_READINESS_SUCCESSOR} readiness successor dependency"
            )


def validate_risk_scope_successor_dependencies(
    tasks: dict[str, dict[str, Any]],
    errors: list[str],
    evidence_binding: dict[str, Any] | None = None,
    external_verifier: GitHubRiskScopeVerifier | None = None,
) -> None:
    """Require the fresh Risk scope gate without rewriting its historical predecessor."""
    task029 = tasks.get("TASK-029")
    if isinstance(task029, dict):
        if task029.get("status") not in {"blocked", "active"}:
            errors.append("TASK-029 queue status must be blocked or human-activated active")
        if RISK_SCOPE_SUCCESSOR not in tasks:
            errors.append(f"tasks: {RISK_SCOPE_SUCCESSOR} successor gate missing for TASK-029")
        dependencies = task029.get("depends_on")
        if isinstance(dependencies, list):
            if len(dependencies) != len(RISK_SCOPE_REQUIRED_DEPENDENCIES) or set(
                dependencies
            ) != set(RISK_SCOPE_REQUIRED_DEPENDENCIES):
                errors.append(
                    "TASK-029: required scope dependencies must be TASK-015, TASK-031, TASK-051"
                )
            if RISK_SCOPE_SUCCESSOR not in dependencies:
                errors.append(
                    f"TASK-029: missing {RISK_SCOPE_SUCCESSOR} scope successor dependency"
                )
            for rejected in (RISK_HISTORICAL_SCOPE_TASK, L4_READINESS_SUCCESSOR):
                if rejected in dependencies:
                    errors.append(
                        f"TASK-029: {rejected} cannot replace or bypass {RISK_SCOPE_SUCCESSOR}"
                    )

    task030 = tasks.get(RISK_HISTORICAL_SCOPE_TASK)
    if not isinstance(task030, dict):
        errors.append("TASK-030 historical record must remain present")
    else:
        if task030.get("status") != "completed":
            errors.append("TASK-030 historical queue status must remain completed")
        delivery = task030.get("delivery")
        if not isinstance(delivery, dict):
            errors.append("TASK-030 historical delivery metadata must remain present")
        else:
            for field, expected in RISK_HISTORICAL_DELIVERY.items():
                if delivery.get(field) != expected:
                    errors.append(
                        f"TASK-030 historical {field.removesuffix('_status')} must remain "
                        f"{expected}"
                    )
            evidence = delivery.get("completion_evidence")
            if not isinstance(evidence, dict):
                errors.append("TASK-030 historical completion evidence must remain present")
            else:
                for field, expected in RISK_HISTORICAL_COMPLETION_EVIDENCE.items():
                    if evidence.get(field) != expected:
                        errors.append(
                            "TASK-030 historical completion evidence "
                            f"{field} must remain {expected}"
                        )

    task005 = tasks.get("TASK-005")
    if isinstance(task005, dict) and task005.get("status") != "blocked":
        errors.append("TASK-005 queue status must remain blocked")

    task051 = tasks.get(RISK_SCOPE_SUCCESSOR)
    if isinstance(task051, dict) and task051.get("status") == "completed":
        delivery = task051.get("delivery")
        if (
            isinstance(delivery, dict)
            and delivery.get("review_status") in {"approved", "not_required"}
            and not task051_completion_evidence_is_bound(
                delivery, evidence_binding, external_verifier
            )
        ):
            errors.append("TASK-051 evidence does not match its governance binding")


def validate_json_schemas(errors: list[str]) -> None:
    for path in sorted(SPEC_ROOT.rglob("*.schema.json")):
        try:
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # validation boundary intentionally reports every file
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON Schema: {exc}")


def validate_yaml_files(errors: list[str]) -> None:
    for base in (SPEC_ROOT, TASK_ROOT):
        for path in sorted(base.rglob("*.yaml")):
            try:
                load_yaml(path)
            except Exception as exc:
                errors.append(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")


def validate_manifest(errors: list[str]) -> dict[str, Path]:
    manifest = load_yaml(SPEC_ROOT / "manifest.yaml")
    if not isinstance(manifest, dict):
        errors.append("spec/manifest.yaml: root must be a mapping")
        return {}
    entries = manifest_entries(manifest)
    if not entries:
        errors.append("spec/manifest.yaml: no catalog entries")
    for spec_id, path in entries.items():
        if not path.is_file():
            errors.append(f"spec/manifest.yaml: {spec_id} path does not exist: {path}")
    return entries


def validate_tasks(
    specs: dict[str, Path],
    errors: list[str],
    *,
    today: date | None = None,
) -> None:
    """Validate task metadata with a fixed external verifier for closeout activation."""
    evaluation_date = today or date.today()
    tasks: dict[str, dict[str, Any]] = {}
    task_paths: dict[str, Path] = {}
    waiver_document = load_yaml(TASK_ROOT / "governance-waivers.yaml")
    waivers = waiver_document.get("waivers", []) if isinstance(waiver_document, dict) else []
    if not isinstance(waivers, list):
        waivers = []
    for path in task_files():
        try:
            task = extract_front_matter(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or re.fullmatch(r"TASK-\d{3}", task_id) is None:
            errors.append(f"{path.relative_to(ROOT)}: invalid task id")
            continue
        if task_id in tasks:
            errors.append(f"duplicate task id: {task_id}")
        tasks[task_id] = task
        task_paths[task_id] = path
        if task_id == RISK_HISTORICAL_SCOPE_TASK:
            try:
                historical_oid = git_blob_oid(path.read_bytes())
            except OSError:
                historical_oid = None
            if historical_oid != RISK_HISTORICAL_TASK_BLOB_OID:
                errors.append("TASK-030 historical file bytes do not match immutable Git blob")
        status = task.get("status")
        expected_dir = (
            {
                "blocked": "backlog",
                "ready": "backlog",
                "active": "active",
                "completed": "completed",
            }.get(status)
            if isinstance(status, str)
            else None
        )
        if status not in TASK_STATES or expected_dir != path.parent.name:
            errors.append(f"{path.relative_to(ROOT)}: status must match its queue directory")
        for field in ("status", "depends_on", "spec_refs", "allowed_paths", "forbidden_paths"):
            if field not in task:
                errors.append(f"{path.relative_to(ROOT)}: missing {field}")
        for spec_id in task.get("spec_refs", []):
            if spec_id not in specs:
                errors.append(f"{path.relative_to(ROOT)}: unknown spec ref {spec_id}")
        verification = task.get("verification")
        if not isinstance(verification, dict) or not verification.get("commands"):
            errors.append(f"{path.relative_to(ROOT)}: verification.commands must not be empty")
        validate_delivery(task_id, task, path, errors)

    graph: dict[str, list[str]] = {}
    for task_id, task in tasks.items():
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{task_paths[task_id].relative_to(ROOT)}: depends_on must be a list")
            continue
        graph[task_id] = [str(value) for value in dependencies]
        for dependency in graph[task_id]:
            if dependency not in tasks:
                unknown_dep_path = task_paths[task_id].relative_to(ROOT)
                errors.append(f"{unknown_dep_path}: unknown dependency {dependency}")
    if has_cycle(graph):
        errors.append("tasks: dependency graph contains a cycle")
    validate_l4_successor_dependencies(tasks, errors)
    risk_scope_binding = None
    if "TASK-029" in tasks or RISK_SCOPE_SUCCESSOR in tasks:
        risk_scope_binding = load_risk_scope_evidence_binding(errors)

    # Ordinary active queues never access the network.  A completed TASK-051
    # closeout is the sole point at which the fixed GitHub verifier is used.
    external_verifier = None
    task051 = tasks.get(RISK_SCOPE_SUCCESSOR)
    if isinstance(task051, dict) and task051.get("status") == "completed":
        external_verifier = GitHubRiskScopeVerifier()
    validate_risk_scope_successor_dependencies(tasks, errors, risk_scope_binding, external_verifier)

    bootstrap_entries = [
        waiver
        for waiver in waivers
        if isinstance(waiver, dict) and waiver.get("kind") == "bootstrap_exception"
    ]
    trusted_bootstrap_waivers: list[dict[str, Any]] = []
    if bootstrap_entries:
        waiver_errors: list[str] = []
        validate_waiver_entries(
            waivers,
            set(tasks),
            waiver_errors,
            today=evaluation_date,
            task_statuses={task_id: str(task.get("status")) for task_id, task in tasks.items()},
        )
        errors.extend(waiver_errors)
        if not waiver_errors:
            trusted_bootstrap_waivers = bootstrap_entries

    index = load_yaml(TASK_ROOT / "index.yaml")
    indexed = index.get("tasks", []) if isinstance(index, dict) else []
    indexed_ids: set[str] = set()
    for entry in indexed:
        if not isinstance(entry, dict):
            errors.append("tasks/index.yaml: each task entry must be a mapping")
            continue
        task_id = entry.get("id")
        indexed_path = entry.get("path")
        if isinstance(task_id, str):
            if task_id in indexed_ids:
                errors.append(f"tasks/index.yaml: duplicate task id {task_id}")
            indexed_ids.add(task_id)
        if not isinstance(indexed_path, str) or not (TASK_ROOT / indexed_path).is_file():
            errors.append(f"tasks/index.yaml: missing path for {task_id}: {indexed_path}")
        if task_id in task_paths and indexed_path != str(
            task_paths[task_id].relative_to(TASK_ROOT)
        ).replace("\\", "/"):
            errors.append(f"tasks/index.yaml: path mismatch for {task_id}")
        if task_id in tasks and entry.get("status") != tasks[task_id].get("status"):
            errors.append(f"tasks/index.yaml: status mismatch for {task_id}")
    missing = set(tasks) - indexed_ids
    extra = indexed_ids - set(tasks)
    if missing:
        errors.append(f"tasks/index.yaml: unindexed tasks: {sorted(missing)}")
    if extra:
        errors.append(f"tasks/index.yaml: entries without task files: {sorted(extra)}")
    for task_id, task in tasks.items():
        for dependency in task.get("depends_on", []):
            dependency_task = tasks.get(dependency)
            if task.get("status") == "active" and (
                not isinstance(dependency_task, dict)
                or dependency_task.get("status") != "completed"
                or (
                    not delivery_is_unlockable(
                        dependency_task,
                        task_id=dependency,
                        evidence_binding=risk_scope_binding,
                        external_verifier=external_verifier,
                    )
                    and not bootstrap_allows_dependency(
                        dependency,
                        task_id,
                        trusted_bootstrap_waivers,
                        today=evaluation_date,
                    )
                )
            ):
                errors.append(
                    f"{task_id}: dependency {dependency} lacks trusted completed delivery; "
                    "activation denied"
                )
    validate_active_readme(tasks, errors)


def validate_error_catalog(errors: list[str]) -> None:
    catalog = load_yaml(SPEC_ROOT / "contracts" / "errors" / "catalog.yaml")
    entries = catalog.get("errors", []) if isinstance(catalog, dict) else []
    codes: set[str] = set()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("error catalog: each entry must be a mapping")
            continue
        code = entry.get("code")
        name = entry.get("name")
        if not isinstance(code, str) or re.fullmatch(r"QQ-[A-Z]+-\d{4}", code) is None:
            errors.append(f"error catalog: invalid code {code}")
        elif code in codes:
            errors.append(f"error catalog: duplicate code {code}")
        else:
            codes.add(code)
        if not isinstance(name, str) or not name:
            errors.append(f"error catalog: invalid name {name}")
        elif name in names:
            errors.append(f"error catalog: duplicate name {name}")
        else:
            names.add(name)


def validate_message_catalog(errors: list[str]) -> None:
    catalog_path = SPEC_ROOT / "contracts" / "catalog.yaml"
    catalog = load_yaml(catalog_path)
    messages = catalog.get("messages", []) if isinstance(catalog, dict) else []
    names: set[str] = set()
    for entry in messages:
        if not isinstance(entry, dict):
            errors.append("contract catalog: each message must be a mapping")
            continue
        name = entry.get("name")
        status = entry.get("status")
        schema = entry.get("schema")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.v[1-9][0-9]*", name) is None
        ):
            errors.append(f"contract catalog: invalid message name {name}")
        elif name in names:
            errors.append(f"contract catalog: duplicate message name {name}")
        else:
            names.add(name)
        if status not in {"active", "planned", "deprecated"}:
            errors.append(f"contract catalog: invalid status for {name}: {status}")
        if status == "active":
            if not isinstance(schema, str):
                errors.append(f"contract catalog: active message {name} requires schema")
            elif not (catalog_path.parent / schema).is_file():
                errors.append(f"contract catalog: schema does not exist for {name}: {schema}")


def validate_state_machines(errors: list[str]) -> None:
    for path in sorted((SPEC_ROOT / "state-machines").glob("*.yaml")):
        document = load_yaml(path)
        machine = document.get("machine") if isinstance(document, dict) else None
        if not isinstance(machine, dict):
            errors.append(f"{path.relative_to(ROOT)}: missing machine mapping")
            continue
        states = machine.get("states")
        initial = machine.get("initial")
        transitions = machine.get("transitions")
        if not isinstance(states, dict) or initial not in states:
            errors.append(f"{path.relative_to(ROOT)}: invalid initial state")
            continue
        if not isinstance(transitions, list):
            errors.append(f"{path.relative_to(ROOT)}: transitions must be a list")
            continue
        seen: set[tuple[str, str, str]] = set()
        for transition in transitions:
            if not isinstance(transition, dict):
                errors.append(f"{path.relative_to(ROOT)}: transition must be a mapping")
                continue
            source = transition.get("from")
            event = transition.get("event")
            target = transition.get("to")
            if source not in states or target not in states or not isinstance(event, str):
                errors.append(f"{path.relative_to(ROOT)}: invalid transition {transition}")
                continue
            key = (str(source), event, str(target))
            if key in seen:
                errors.append(f"{path.relative_to(ROOT)}: duplicate transition {key}")
            seen.add(key)


def validate_markdown_links(errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if re.match(r"^(https?://|mailto:)", target):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link {target}")


def main() -> int:
    errors: list[str] = []
    validate_yaml_files(errors)
    validate_json_schemas(errors)
    specs = validate_manifest(errors)
    validate_tasks(specs, errors)
    validate_waivers(errors)
    validate_error_catalog(errors)
    validate_message_catalog(errors)
    validate_state_machines(errors)
    validate_markdown_links(errors)
    if errors:
        print("Specification validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Specification validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
