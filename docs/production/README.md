# Production readiness evidence

`production-readiness.json` is the repository-owned, machine-readable register for the production target. It is deliberately separate from ordinary Product CI: green tests cannot prove that identity, tenant isolation, data lifecycle, recovery, release, operations, API, risk, and audit-product obligations are complete.

The register is **not self-certification**. Ordinary validation may succeed while `production_ready` is `false`. Release mode remains non-zero until every required gate is `ready`, has no blockers, and cites repository evidence whose exact SHA-256 digest matches the checked-out file.

## Gate contract

Every gate has a stable `id`, `title`, `priority`, `status`, `owner`, canonical `issue_url`, `required_evidence`, current `blockers`, and completed `evidence`.

- Priorities are `P0`, `P1`, or `P2`.
- Statuses are `blocked`, `in_progress`, or `ready`.
- `blocked` and `in_progress` gates must name at least one current blocker.
- `ready` gates must have no blockers and at least one verified evidence object.
- The manifest belongs exactly to `ContextualWisdomLab/governance-risk-compliance` and targets `production`.
- The gate-ID set and each gate’s reviewed priority/issue mapping are closed and versioned.
- Unknown replacement gates, missing gates, ambiguous strings, and silent normalization are rejected.

The initial gate set is:

| Gate ID | Priority | Canonical issue |
| --- | --- | --- |
| `identity-tenant-authorization` | P0 | #4 |
| `postgresql-lifecycle` | P0 | #8 |
| `evidence-lifecycle-recovery` | P0 | #9 |
| `release-artifact-provenance` | P0 | #10 |
| `operability-observability` | P0 | #11 |
| `api-contract` | P1 | #12 |
| `risk-management` | P1 | #13 |
| `audit-management` | P1 | #14 |
| `readiness-evidence-contract` | P0 | #15 |

## Evidence object contract

Schema version 1 accepts only repository-file evidence:

```json
{
  "kind": "repository_file",
  "path": "docs/production/readiness-evidence-index.json",
  "sha256": "64-lowercase-hexadecimal-characters"
}
```

The validator requires exactly those three fields.

- `path` is an unambiguous POSIX-style repository-relative path: no absolute path, `.` or `..`, backslashes, `.git` authority, or path escape.
- The target must exist inside the supplied repository root, resolve to a regular readable file, and may not escape through a symlink.
- `sha256` must equal the lowercase hexadecimal result of SHA-256 over the exact current file bytes.

The readiness-contract gate cites `docs/production/readiness-evidence-index.json`. That index records the reviewed component paths and their Git blob object IDs as repository coordinates; validation recomputes those coordinates from the supplied tree, while the manifest binds the exact index bytes with SHA-256. Git object IDs are not accepted as the cryptographic evidence field.

This binds the claim to exact reviewed file content in the exact checked-out tree. It does **not** replace release-artifact digests, SBOMs, provenance attestations, or signatures; those remain separate issue #10 controls.

Opaque strings such as `verified`, PR prose, model judgments, status names, stale workflow results, and predecessor-head evidence are not valid evidence. Adding another evidence kind requires an explicit schema-version decision, validator implementation, realistic regressions, and updated documentation; unknown kinds fail closed.

## Commands

Validate the manifest, evidence schema, repository paths, and SHA-256 bindings:

```bash
uv run python -c \
  'from cwl_grc.production_readiness import main; raise SystemExit(main())' \
  docs/production/production-readiness.json \
  --repository-root .
```

Require every gate for a release decision:

```bash
uv run python -c \
  'from cwl_grc.production_readiness import main; raise SystemExit(main())' \
  docs/production/production-readiness.json \
  --repository-root . \
  --require-ready
```

| Exit code | Meaning | Next action |
| ---: | --- | --- |
| `0` | Manifest and SHA-256 evidence bindings are valid; in release mode every gate is ready. | Continue through the remaining protected release controls. |
| `1` | Manifest and evidence bindings are valid, but at least one production gate is non-ready. | Work the listed canonical issues; do not release. |
| `2` | JSON, gate contract, evidence object, repository path, or SHA-256 digest is invalid. | Repair the evidence contract before using its result. |

The ordinary GitHub workflow intentionally omits `--require-ready`; it proves only structural and evidence-binding integrity. A manually requested or release workflow using `--require-ready` must fail until all gates genuinely satisfy their evidence obligations.

## Updating a gate

1. Implement the canonical issue on an exact branch head.
2. Collect exact-current-head Product, security, review, migration, recovery, and operational evidence required by that gate.
3. Persist the deterministic evidence file in this repository.
4. Calculate the SHA-256 digest of the exact current evidence file and add a `repository_file` object.
5. Remove only blockers proven resolved on the integrated head.
6. Mark the gate `ready` only when no blocker remains.
7. Run ordinary validation and `--require-ready`; the latter must still fail if any other gate remains non-ready.
8. Revalidate every live branch, review, security, and release rule before merge or release.

The manifest is a decision input, not an authorization system. It cannot override Keyverse, tenant/purpose/resource authorization, branch protection, independent review, centrally owned security controls, or release governance.
