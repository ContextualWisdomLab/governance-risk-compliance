# GRC Analytics traceability

Snapshot date: 2026-08-31

## Change coordinate

- Repository: `ContextualWisdomLab/governance-risk-compliance`
- Protected base observed before the slice: `develop@85da4e1c64e5b46ca3a11ca71654a82b57366a3e`
- Product gap: Issue #61, `[P0 Analytics] Add deterministic, purpose-bound GRC LLM analytics`
- Decision: ADR 0012, `docs/adr/0012-grc-analytics-supporting-bounded-context.md`
- Product contract: `docs/product/grc-analytics-query-contract.md`
- Intent schema: `cwl.grc.analytics.intent.v1`
- Query-plan schema: `cwl.grc.analytics.query-plan.v1`
- Read-model coordinate: `cwl.grc.analytics.read-model.v1`

## Requirement-to-implementation map

| Requirement | Implementation evidence | Verification evidence |
| --- | --- | --- |
| Analytics is a read-only Supporting Bounded Context | `cwl_grc/analytics/domain`, `cwl_grc/analytics/application`, ADR 0012 | `tests/test_analytics_architecture.py` |
| GRC owns no interactive model-provider credential/client in this context | ADR 0012 and AGENTS Analytics rules; no provider adapter exists in the slice | architectural import rejection for `openai`, `anthropic`, `httpx`, `requests` |
| Natural-language orchestration goes through contextual-orchestrator ACL | ADR 0012 and `ARCHITECTURE.md` context map | no direct provider integration is present in the first slice |
| Raw model SQL is not an execution contract | `AnalyticsQueryPlan` has semantic fields only; product contract defines future safe executor | `test_build_query_plan_preserves_verified_scope_without_sql` |
| Tenant/workspace/principal/purpose scope is explicit | `AnalyticsPlanningContext` and immutable `AnalyticsQueryPlan` | query-plan contract tests assert exact verified coordinates |
| Question content is not required in deterministic planning | intent carries bounded SHA-256 `question_hash` | invalid hashes fail closed in contract tests |
| Semantic dimensions/measures are allowlisted and versioned | `DIMENSION_CODES`, `MEASURE_CODES`, schema-version constants | unsupported and duplicate fields fail `unsupported_analysis` |
| Effective/business time and system-recorded time stay distinct | `TimeAxis`, `AnalyticsTimeRange` | timezone, axis, and interval regressions |
| Unauthorized fields fail closed | permitted-field subset check | `not_authorized / field_policy_denied` regression |
| Authorized but unavailable facts do not become guesses | available-field subset check | `insufficient_evidence / projection_field_unavailable` regression |
| Query work is bounded before execution | max 500 result rows; bounded filter operators/value cardinality | row/filter bound regressions |
| Domain layer does not depend on application/database/provider implementation | explicit DDD package boundary | AST architectural fitness tests |
| New domain behavior does not accumulate in generic technical buckets | named Analytics domain/application paths | fitness test rejects `utils/helpers/common/services/misc` files |

## Authority invariants

The semantic plan is not a GRC decision. It cannot publish policy, approve a control or exception, accept risk, close an audit finding, dispose evidence, certify compliance, or change tenant/security authority. Those operations remain separate authoritative domain commands with their existing maker-checker/human authorization boundaries.

Framework requirements, evidence existence, and evidence bindings are not automatically control-effectiveness or compliance truth. Measures such as residual risk, control effectiveness, evidence freshness, and aggregates are admitted semantic names only; an authorized deterministic projection must supply the value before analysis may proceed.

## Verification performed for this slice

A clean replicated slice run executed 29 tests and measured 100% statement and branch coverage over the new `cwl_grc.analytics` production package. The slice was also checked for Python lines longer than the repository Ruff limit after the final test edits. Repository-hosted Product and central required workflows remain authoritative for integration, dependency, SAST, security, and independent-review evidence after a pull request is opened.

## Deferred acceptance evidence

This first slice intentionally does not implement the read projection, SQL/DSL executor, contextual-orchestrator call, result/query-receipt persistence, document RAG, provider trace, buyer UI, or production evaluation corpus. Issue #61 owns those follow-up slices. Until the deterministic read projection exists, a semantically admitted but unavailable field must return `insufficient_evidence`.

`docs/product-technical-gap-baseline.md` is a large historical live-state register whose current protected copy predates this slice and also contains historical ruleset observations. It must be refreshed as a full-document reconciliation from live GitHub evidence; it must not be replaced by a stub or partially reconstructed file.
