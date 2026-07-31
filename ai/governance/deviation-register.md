# Governance deviation register

The entries below are recorded only. TASK-031 does not change business code, schemas, workflows or normative specifications to resolve them.

| Deviation | Record-only statement | Suggested remediation |
| --- | --- | --- |
| ADR-0008 persistence | Persistence authority/lifecycle evidence is not reconstructed here; no historical approval is invented. | TASK-039: reconcile ADR-0008 with persistence/outbox ownership. |
| Risk Bloom deduplication | Permanent deduplication semantics and bounded-memory operation are not simultaneously evidenced; TASK-031 does not choose a policy. | TASK-040: define retention, replay and bounded-memory safety. |
| manifest/docs lifecycle | Manifest and explanatory documentation lifecycle evidence is incomplete; no contract or docs rewrite is made here. | TASK-041: establish version, migration and docs lifecycle gates. |
| Strategy event activation | `strategy.state_changed` activation/readiness remains a planned gap and does not release TASK-008. | TASK-042: complete Market readiness and event activation review. |

Every suggested task is advisory and remains unactivated until a human governance decision creates or activates it.
