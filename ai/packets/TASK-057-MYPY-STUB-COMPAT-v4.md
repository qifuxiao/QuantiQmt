# TASK-057 mypy stub compatibility Repair Packet

## Packet identity and authority

- Task: `TASK-057`
- Plan: `TASK-057-PLAN-v4`
- Packet identity: `TASK-057-MYPY-STUB-COMPAT-v4`
- Stage: `packet-only bootstrap`
- Repository: `qifuxiao/QuantiQmt`
- Expected Base / PR Base: `872aa7666f8811ad3a1e49b671a9c1290085330a`
- Repair branch: `codex/task-057-mypy-stub-compat-repair`
- Reviewed Plan v4 Head: `543428885cd9e2f3f0a623bc21dd6b7aac3fb987`
- Plan v4 PR: <https://github.com/qifuxiao/QuantiQmt/pull/104>
- Independent Plan v4 Review: <https://github.com/qifuxiao/QuantiQmt/pull/104#pullrequestreview-5097366199>
- Plan v4 sequence authority: <https://github.com/qifuxiao/QuantiQmt/pull/103#issuecomment-5511521778>
- Prior Repair authorization: <https://github.com/qifuxiao/QuantiQmt/pull/103#issuecomment-5511244715>

This document bootstraps PR identity only. It is not an implementation change or an
assignment. The canonical Human assignment is `pending`, Repair v4 Handoff is
`pending`, and the Implementation Agent is `pending` and unassigned. No implementation
writer or single-writer authority exists before Human publishes the canonical assignment
on the packet-only Repair PR.

## Repair objective

The future repair is limited to making the `jsonschema` typing imports in exactly these
files compatible with both supported typing environments:

- `scripts/validate_specs.py`
- `scripts/validate_agent_environment.py`

The same exact Repair Head must be tested in both of these environments:

1. `jsonschema` installed without `types-jsonschema`.
2. `jsonschema` installed with `types-jsonschema`.

Both environments must execute this original command unchanged and record exit code 0:

```text
poetry run mypy src scripts
```

Installing, removing, or synchronizing `types-jsonschema` to manufacture either result is
not evidence. Each record must describe the environment that actually exists and bind its
result to the same exact Repair Head.

## Candidate design gate

The following narrow annotation is a candidate only and is not approved as the final
implementation by this Packet:

```python
# type: ignore[import-untyped,unused-ignore]
```

It may be adopted only after actual testing demonstrates that it passes the unchanged
mypy command in both required environments without changing runtime behavior. If that
proof fails, implementation must stop and return for Coordinator and Human direction;
the assigned agent may not broaden the design autonomously.

## Prohibited changes and actions

This Packet does not authorize any of the following:

- a bare `# type: ignore`;
- disabling or weakening `warn_unused_ignores`;
- modifying mypy configuration or the original verification command;
- using `Any` or dynamic imports to evade type checking;
- changing validator runtime behavior;
- adding, removing, or synchronizing installation of `types-jsonschema`;
- modifying `pyproject.toml`, `poetry.lock`, or `poetry.toml`;
- modifying CI, `spec/`, business code, or a completed task;
- modifying `TASK-057-IMPLEMENTATION-v1.yaml`, `TASK-057-REPAIR-v2.yaml`, or
  `TASK-057-REPAIR-v3.yaml`;
- creating `ai/handoffs/TASK-057-REPAIR-v4.yaml` during bootstrap;
- modifying any Python script or test during bootstrap;
- accessing Mini QMT, querying an account, or sending or cancelling an order;
- self-review, Approval, merge, closeout, release, or next-task activation.

## Frozen lifecycle order

The only authorized sequence is:

1. Create this packet-only Repair PR from the exact Expected Base.
2. Human publishes an unedited canonical assignment on that Repair PR.
3. Coordinator creates the add-only Repair v4 Handoff, freezing the existing PR,
   assignment, exact Base/Starting Head, writer identity, paths, commands, and evidence
   requirements.
4. The assigned Implementation Agent's first writer action synchronizes the Coordinator
   Handoff commit into the Repair PR without rewriting it.
5. Only then may the assigned agent implement the minimal repair test-first.
6. Produce two-environment evidence for the same exact Repair Head.
7. Obtain green CI for that exact Head.
8. Obtain an independent Review of that exact Head.
9. Human alone may merge the Repair PR.
10. A separately authorized, pure-governance closeout follows from the then-current main.

Any missing, reordered, edited, or identity-drifting authority leaves the workflow
blocked. In particular, implementation must not begin while assignment or Repair v4
Handoff remains pending.

## Packet-only bootstrap acceptance

- The branch starts at `872aa7666f8811ad3a1e49b671a9c1290085330a`.
- Its first commit adds only this file.
- The resulting PR targets `main` at the exact Expected Base.
- Human assignment, Repair v4 Handoff, implementation, two-environment evidence, CI,
  Review, merge, and closeout all remain pending after PR creation.
