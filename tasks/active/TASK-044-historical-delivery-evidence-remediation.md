---
id: TASK-044
title: Remediate historical delivery evidence trust
status: active
depends_on: []
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/active/README.md
  - tasks/active/TASK-044-historical-delivery-evidence-remediation.md
  - tasks/completed/TASK-014-implementation-readiness.md
  - tasks/completed/TASK-015-risk-contracts.md
  - tasks/completed/TASK-030-risk-validator-integration-scope.md
  - tasks/index.yaml
  - ai/governance/**
forbidden_paths:
  - src/**
  - spec/**
  - docs/**
  - migrations/**
  - tests/**
  - scripts/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

Restore machine-trusted delivery evidence for the historical prerequisite tasks that currently prevent safe activation of the contract-development queue.

## Scope

- Audit TASK-014, TASK-015, and TASK-030 against repository Git history and GitHub facts available to the authorized reviewer.
- Preserve unknown historical facts as `reported_unverified`/`unverifiable`; never infer an approval, review, CI result, or human authorization.
- If a historical task can be remediated with auditable evidence, update only its delivery metadata and record the exact evidence in `ai/governance/**`.
- Prove through the existing validator that ready candidates remain blocked until every dependency has trusted completed delivery.

## Non-goals

- No business implementation, runtime code, schema, migration, or public contract changes.
- No activation of TASK-005, TASK-017, TASK-018, TASK-020, TASK-022, or TASK-029 during this task.
- No waiver creation or extension; the retired TASK-014 bootstrap waiver remains retired and release-prohibited.

## Acceptance criteria

- [ ] TASK-014, TASK-015, and TASK-030 each have an auditable evidence assessment tied to exact PR/head/merge/review facts.
- [ ] Unknown historical facts remain explicitly unverified; no historical approval or CI result is fabricated.
- [ ] Any evidence promoted to trusted completed delivery has a valid reviewer, review URL, exact reviewed head, merge commit, and human authorization.
- [ ] The validator and governance evidence demonstrate that ready candidates cannot activate through missing or reported-unverified dependencies.
- [ ] TASK-005 and TASK-029 remain blocked; no business task is activated or released.
- [ ] All verification commands pass and the final diff stays within the allowed paths.

## Required evidence

- Exact before/after delivery fields for TASK-014/015/030.
- GitHub Review/CI URLs and exact SHAs when independently verifiable; `unverifiable` otherwise.
- A governance audit explaining why each historical fact is trusted or remains blocked.
- Validator output proving no ready-label or historical waiver bypasses dependency trust.

## Evidence

- The machine-readable audit at `ai/governance/historical-delivery-evidence-task-044.yaml` records exact PR, head, merge, Review, CI, and authorization facts queried from GitHub on 2026-08-06.
- TASK-014 remains `reported_unverified` / `prohibited`: implementation PR #21 and closeout PR #22 both have empty GitHub Review lists, and PR #22 does not provide independently auditable human closeout authorization.
- TASK-015 is remediated to trusted completed delivery: closeout PR #27 has a formal `APPROVED` Review by qifuxiao on final head `1ab0baf11c8514736249200214fcaf79c9fec3ad`, exact Review URL, 4/4 successful CI, merge commit `7ae7e8a4f780b32d72f5a24a42d240f417f1e460`, and explicit human authorization in the PR body. Release remains prohibited.
- TASK-030 remains `reported_unverified` / `prohibited`: scope PR #42 and closeout PR #44 both have empty GitHub Review lists, and PR #44 does not provide independently auditable human closeout authorization.
- Existing validator integration tests reject ready dependencies, missing delivery, `reported_unverified` delivery, terminal/invalid bootstrap waivers, and wrong beneficiaries. The retired TASK-014 waiver is unchanged and cannot unlock business activation.
- TASK-005 and TASK-029 remain blocked. TASK-017, TASK-018, TASK-020, and TASK-022 remain backlog/ready candidates only and are not active; TASK-014 remains untrusted, so their activation gate stays fail-closed.

## Risks and rollback

- If any historical evidence cannot be independently established, keep the task blocked and preserve `release_status: prohibited`.
- Rollback may restore only governance metadata and audit records; it must not alter business code or normative contracts.
