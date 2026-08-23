# Product and technical gap baseline

Snapshot (document generation date): 2026-08-23, Asia/Seoul  
Repository: `ContextualWisdomLab/governance-risk-compliance`  
Protected `develop`: `a747077757484c880fccf76e30cac068c593d3b0`  
Collaborators: `seonghobae` only; independent review remains the merge blocker.  
Re-query every exact head before merge or push. This file records **observed** live state at generation time.

## Officer-visible next actions

1. Keep this process on loopback. Do not expose CWL GRC remotely.
2. When a Keyverse verifier is configured, present a Bearer `at+jwt` access token, author or revise the next official-control policy, then attach the next evidence on an uncovered mapped control (for example CSAP `10.2.1`).
3. After a mutation, join the append-only `audit_event` to issuer, client, tenant, subject, purpose, `allow`, and `X-Request-ID`. The raw access token must not appear in audit rows.
4. Follow `docs/runbooks/keyverse-deployment-hardening.md` for local-preview migration `0003_audit_attribution`, JWKS rotation, issuer outage, clock skew, and emergency read-only. That runbook does not make this kernel a production deployment.
5. Independent non-author review is required before any protected merge. GitHub check latency is not a stop: continue G-01 / Issue #4 on a stacked branch.

Highest-leverage remaining Issue #4 slice after this attribution work: a production start profile that refuses to boot without a Keyverse verifier (no header-identity local preview), plus encrypted transport admission. Do not enable remote production exposure.

## Open pull requests (re-query before merge)

Direct to `develop` unless noted. Heads below were observed during this generation; they move.

| PR | Head (observed) | Base | Draft | Notes |
| --- | --- | --- | --- | --- |
| #17 | `7b4adbe0964e12e4b31e197ab10a63aabf0f593c` | develop | no | Production-readiness evidence gate. Merge-ready pending independent review / hosted checks. |
| #18 | `35d3e55ccd2c5e89efec6c28b7613f1d605cac13` | develop | no | PostgreSQL schema lifecycle. Merge-ready pending independent review / hosted checks. |
| #19 | live `docs/product-technical-gap-baseline` branch | develop | no | Gap baseline refresh. Re-query exact head. |
| #34 | `ed1e6222df0ff021fb72d40d79a242bae71754c4` | develop | no | Officer workspace design authority. Merge-ready pending independent review / hosted checks. |
| #37 | `9fffa505512d4cf7eccbb6cd240dab6a1e8acb73` | develop | no | Catalog provenance. Merge-ready pending independent review / hosted checks. |
| #38 | `c1445d7105ee7366794a0acb0d0507777850ce9e` | develop | no | Keyverse token replay guard. Parent of #55. Merge-ready pending independent review / hosted checks. |
| #41 | `2346afe6a063f502517ee235d6c3e87488da8357` | internal-control feature base | no | Internal-control SAST remediation. Stacked, not direct-to-develop. |
| #43 | `f41c387c62998de2d136ce8f4a110b4cb22906ac` | develop | no | Hourly GRC review-repair workflow. Merge-ready pending independent review / hosted checks. |
| #51 | `1a8f90dd15f37ffc86b8a0efd217a8b2812e5f99` | develop | no | OpenTelemetry request boundary. Merge-ready pending independent review / hosted checks. |
| #53 | `976945dbbe22b0b8fa7893150e2723738a0ff484` | develop | no | Version-one policy API. Merge-ready pending independent review / hosted checks. |
| #54 | `3e972f4de9e9a1f5a17379ac93b33bdcb2b0f4cf` | #34 | **Draft** | Workspace posture preview. Do not mark Ready without exact-head evidence. |
| #55 | `531121b44424b6b7d68d84f722c6e91eaffd4c2b` | #38 | no | Keyverse Bearer HTTP, tenant-owned persistence, OpenAPI `KeyverseBearer`, typed `AccessTokenScopeError` 403. Parent of this attribution slice. |

Central `.github` #1257 (OSV fork preserve) remains open and is not this repository.

Merge rule: protected merge only with required checks **and** independent non-author approval at that exact head. Self-APPROVE, `--admin`, force-push, dummy-commit, and Draft-as-Ready without exact-head evidence are unused. While the only collaborator is the author, merge-ready plus recorded independent-review blocker is the honest bar.

## Open issues

| Issue | Title | Status |
| --- | --- | --- |
| #4 | Keyverse OIDC and tenant-scoped authorization before remote deployment | Open (P0). JWT kernel, OIDC loader, HTTP Bearer, tenant persistence, OpenAPI, and audit attribution are in the #38/#55 stack. Remaining: production-profile fail-closed start, encrypted transport, remote admission. |
| #8 | PostgreSQL schema lifecycle | Open (P0). Body on #18. |
| #9 | Evidence-key rotation, retention, legal hold | Open (P0). |
| #10 | Hardened signed artifacts / protected release | Open (P0). |
| #11 | Readiness probes, telemetry, SLOs, incident runbooks | Open (P0). |
| #12 | Versioned production API contracts | Open (P1). Body on #53. |
| #13 | Risk register | Open (P1). |
| #14 | Audit programs / sampling / findings | Open (P1). |
| #15 | Production-readiness evidence gate | Open (P0). Body on #17. |
| #27 | Separate external requirements and internal controls | Open (P0). |
| #28 | Obligation register / applicability | Open (P1). |
| #29 | Catalog ingestion / OSCAL / OLIR | Open (P1). |
| #30 | Tenant-scoped compliance workspace | Open (P1). Body on #34 / Draft #54. |

## Shipped kernel versus remaining G-01

Shipped on the Keyverse stack (PRs #38 and #55, plus this attribution slice):

- Closed RFC 9068 Keyverse access-token verification (ADR 0003).
- Bounded OIDC/JWKS loader (ADR 0004).
- HTTP Bearer enforcement, subject-as-actor, officer-home isolation (ADR 0005).
- `tenant_identifier` on policy, evidence, and audit (ADR 0006).
- OpenAPI `KeyverseBearer` (`at+jwt`) with `grc.policy.read|write` and `grc.evidence.write` (ADR 0007).
- `audit_event` issuer, client, correlation, and `allow` without raw token copy (ADR 0008); local-preview runbook.

Still not production:

- Loopback-only HTTP; forwarded and non-loopback traffic return 503.
- Local preview without a verifier still treats `X-Actor-Id` as a declaration.
- No Keyverse-backed admission of customer traffic.
- No second identity store. Consume Keyverse; do not fork it.

## ADR- and research-derived gaps

Functional: versioned policy, official catalogs, evidence bind, and gap query exist. Residual-risk scoring, audit-engagement body, OSCAL/OLIR source-text redistribution, and remote production exposure are out of this slice.

PRD/TRD: officer copy must state the next action and distinguish local developer preview from production. Official catalog identifiers only (CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, COSO 2017).

UML/runtime: `cwl_grc` FastAPI + SQLite/PostgreSQL kernel. Do not rewrite this kernel to Rust/GPU in this iteration.

## Standards already cited

Doctoring references already include RFC 9068, RFC 9700, OpenID Connect Core/Discovery errata set 2, and the official control catalogs. This iteration adds no new standard; it implements Issue #4 item 7 (audit attribution) and item 10 (deployment-hardening runbooks) against those citations.
