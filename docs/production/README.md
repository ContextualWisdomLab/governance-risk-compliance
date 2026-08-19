# Production readiness evidence

`production-readiness.json` is the repository-owned, versioned register of the evidence
required before CWL GRC may be promoted as a production service. It is deliberately
separate from the ordinary Product workflow: green unit tests do not prove that identity,
data lifecycle, recovery, release, operations, API, risk, and audit-product obligations are
complete.

This register is **not self-certification**. A gate may be marked `ready` only when its
canonical issue has concrete implementation evidence and the exact release head still
satisfies independent review and centrally owned security checks.

## Gate contract

Every gate has a stable `id`, `title`, `priority`, `status`, `owner`, canonical `issue_url`,
`required_evidence`, current `blockers`, and completed `evidence`.

- Priorities are `P0`, `P1`, or `P2`.
- Statuses are `blocked`, `in_progress`, or `ready`.
- `blocked` and `in_progress` gates must name at least one current blocker.
- `ready` gates must have no blockers and must name concrete evidence.
- The manifest belongs to `ContextualWisdomLab/governance-risk-compliance` and targets
  `production`; foreign issue URLs or repository identities are rejected.

## Validate the evidence contract

Run ordinary validation on every change:

```bash
uv run python -c \
  'from cwl_grc.production_readiness import main; raise SystemExit(main())' \
  docs/production/production-readiness.json
```

Ordinary validation exits successfully when the manifest is structurally and internally
valid, even when the emitted `production_ready` value is `false`. That behavior lets pull
requests improve one gate without pretending the whole product is ready.

Release promotion must use fail-closed mode:

```bash
uv run python -c \
  'from cwl_grc.production_readiness import main; raise SystemExit(main())' \
  docs/production/production-readiness.json --require-ready
```

`--require-ready` exits with code `1` while any validated gate is not `ready`. Invalid JSON
or an inconsistent contract exits with code `2`. The command emits deterministic JSON so a
release workflow can preserve the exact blocker set as evidence.

## Updating a gate

1. Update the canonical issue first with current-head implementation and verification evidence.
2. Change only the corresponding manifest gate; do not hide work by deleting a required gate.
3. Keep non-ready blockers concrete and current.
4. Mark a gate ready only after its implementation evidence exists and no gate-local blocker remains.
5. Re-run the Product and Production Readiness workflows on the exact pull-request head.
6. Release only when `--require-ready` succeeds and independent review/security evidence is current.

The initial register intentionally reports CWL GRC as not production-ready. Issue #4 and
issues #8 through #14 remain the authoritative work queues; issue #15 owns only this evidence
contract and validator.
