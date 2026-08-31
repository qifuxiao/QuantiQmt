# Codex Handoff for Cline

## Authority and frozen identity

- Use the root and path-local `AGENTS.md`, `spec/README.md`, `spec/manifest.yaml`,
  the single active task, and all task `spec_refs` for authority discovery.
- Read the task's Codex Plan for the Plan version and Planning Base.
- Read the Codex-authored Handoff Record for the sole frozen
  Implementation/Repair Base, expected PR Base, task blob, stage paths, and
  Codex-only paths.
- A moving ref may only be checked against a frozen SHA; it must not supply,
  derive, or rewrite that SHA.

## Pre-implementation gates

- Fetch, use the named existing branch, and require a clean worktree.
- Verify the Handoff topology and blobs against the supplied exact Head before any repair change.
- Verify Planning Base ancestry, exact Base/PR Base/merge-base identity, task
  blob identity, dependencies, and the complete Base...Head path set.
- Bind validation commands to the supplied exact Head, never an ambient moving
  `HEAD` substituted for it.

## Git and path constraints

- Modify only paths allowed by both the Handoff Record and active task; reject
  every task-forbidden path and both sides of a rename.
- Never modify a Codex-only path.
- Do not rebase, force-push, push directly to `main`, create a replacement PR,
  or change task/spec scope.

## PLAN_BLOCKED

- Stop and report `PLAN_BLOCKED` with the failing command, exit code, and
  evidence when any authority, identity, topology, cleanliness, dependency,
  scope, design, verification, or permission gate fails.
- Do not improvise a bypass or weaken a fail-closed check.

## Implementation Report

- Report Plan and Packet versions; Planning Base; Handoff commit/blob; expected
  Base; GitHub PR Base/Head; branch and PR URL.
- Report changed files, the complete expected-Base...Head path audit,
  per-acceptance evidence, every command and exit code,
  first-failure/final-pass evidence, passed/failed/skipped counts, unverified
  scope, risks, and spec deviations.

## PR mechanics and lifecycle authority

- Commit and push normally to the existing implementation branch, then wait
  for all GitHub checks and report their links and final states.
- Do not self-approve, merge, close out, or change task lifecycle state.
- Independent Review supplies evidence and a verdict only. Authorization is
  human-only: only a human may authorize activation, merge, closeout, or
  active-to-completed transition.
- Automation may mechanically execute a separately recorded and verifiable
  human authorization; automation is never an alternative authorizer.
