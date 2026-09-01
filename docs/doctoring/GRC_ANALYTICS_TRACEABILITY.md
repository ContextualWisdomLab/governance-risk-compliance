# GRC Analytics traceability

Snapshot date: 2026-09-01

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
| GRC owns no interactive model-provider credential/client in this context | ADR 0012 and AGENTS Analytics rules; no provider adapter exists in the slice | architectural import fitness allows only stdlib or `cwl_grc.analytics` |
| Natural-language orchestration goes through contextual-orchestrator ACL | ADR 0012 and `ARCHITECTURE.md` context map | no direct provider integration is present in the first slice |
| End-state analysis is Ontology + Semantic Layer + provenance/lineage + validated external research, not Naive RAG | product query contract defines the evidence path and authority split | implementation deliberately deferred; Issue #61 owns ontology/resolver/research/Evidence Graph slices |
| SearXNG snippets are discovery candidates, never evidence | product query contract requires source fetch/validation/provenance before Evidence Graph admission | connector/validator acceptance deferred to Issue #61 |
| LineageWeave evidence remains observed/inferred evidence rather than authoritative GRC truth | product query contract requires a versioned port/ACL and preserved truth status | LineageWeave adapter/parity acceptance deferred to Issue #61 |
| Cross-product identity/authority/truth-status/provenance coordinates use released context-graph contracts rather than copied tables | product query contract names `context-graph-contracts` as the candidate Shared Kernel boundary | released-contract dependency/conformance remains deferred and requires Context Fabric owner evidence |
| Raw model SQL is not an execution contract | `AnalyticsQueryPlan` has semantic fields only; product contract defines future safe executor | `test_build_query_plan_preserves_verified_scope_without_sql` |
| Query-plan read-only authority cannot be caller-overridden | `AnalyticsQueryPlan.read_only` is a frozen `init=False` field | constructor-signature and plan-value regression in `test_analytics_malformed_intent.py` |
| Tenant/workspace/principal/purpose scope is explicit | `AnalyticsPlanningContext` and immutable `AnalyticsQueryPlan` | query-plan contract tests assert exact verified coordinates |
| Untrusted runtime intent shapes fail closed before typed operations | `_validate_intent_shape`, filter/time-range shape checks, safe identifier validation | malformed hash, dimension/measure/filter/time-range/row-limit/identifier regressions |
| Question content is not required in deterministic planning | intent carries bounded SHA-256 `question_hash` | invalid hashes fail closed in contract tests |
| Semantic dimensions/measures are allowlisted and versioned | `DIMENSION_CODES`, `MEASURE_CODES`, schema-version constants | unsupported and duplicate fields fail `unsupported_analysis` |
| Future semantic measures publish source fields, deterministic formula, null/time semantics, authorization scope, and version | product query contract | executor/read-model measure catalogue deferred to Issue #61 |
| Effective/business time and system-recorded time stay distinct | `TimeAxis`, `AnalyticsTimeRange` | optional-range, timezone, axis, interval, DST-fold, and extreme-offset regressions |
| Temporal ordering does not overflow at representable datetime boundaries | unbounded integer instant key derived from ordinal/time minus UTC offset | `datetime.min +14:00` and `datetime.max -14:00` regressions |
| Unauthorized fields fail closed | permitted-field subset check | `not_authorized / field_policy_denied` regression |
| Authorized but unavailable facts do not become guesses | available-field subset check | `insufficient_evidence / projection_field_unavailable` regression |
| Query work is bounded before execution | max 500 result rows; max 64 filters; max 100 values per filter; bounded dimension/measure collections | resource-bound regressions |
| Domain/application do not depend on flat kernel/database/provider/third-party implementation | explicit DDD package boundary | AST fitness checks both `import` and absolute `from ... import ...` forms |
| New domain behavior does not accumulate in generic technical buckets | named Analytics domain/application paths | fitness test rejects `utils/helpers/common/services/misc` files |

## Authority invariants

The semantic plan is not a GRC decision. It cannot publish policy, approve a control or exception, accept risk, close an audit finding, dispose evidence, certify compliance, or change tenant/security authority. Those operations remain separate authoritative domain commands with their existing maker-checker/human authorization boundaries.

Framework requirements, evidence existence, ontology relations, lineage inference, search results, and evidence bindings are not automatically control-effectiveness or compliance truth. The minimum future relation states are `authoritative`, `observed`, `inferred`, `proposed`, `superseded`, and `rejected`; Analytics or `contextual-orchestrator` may not promote an inferred/proposed relation into authoritative truth. Measures such as residual risk, control effectiveness, evidence freshness, and aggregates are admitted semantic names only; an authorized deterministic projection must supply the value before analysis may proceed.

Prompt-injection strings contained in internal documents, external pages, search snippets, metadata, or evidence attachments are evidence data only. They cannot change tenant/purpose authorization, query policy, source-validation policy, or tool authority.

## Verification performed for this slice

The Analytics contract and architecture suites preserve the repository's 100% owned-production statement and branch coverage requirement. Review-driven regression coverage verifies DST-fold ordering by actual instant, valid extreme-offset boundary dates without UTC-conversion overflow, malformed runtime intents as typed abstentions instead of exceptions, resource bounds before collection scans, strict Analytics dependency ownership, and the non-overridable read-only plan invariant.

The exact-head Product lane exposed a real 99.67% coverage regression after the resource-bound repair. The repair removed one unreachable duplicate tuple-shape branch and added the missing malformed-measure regression rather than lowering the coverage denominator or threshold. Repository-hosted Product and central required workflows remain authoritative for integration, dependency, SAST, security, and independent-review evidence on each new exact pull-request head.

## Deferred acceptance evidence

This first slice intentionally does not implement the authoritative read projection, ontology resolver, context-graph adapter, LineageWeave ACL, SearXNG research connector, primary-source validator, Evidence Graph, SQL/DSL executor, contextual-orchestrator call, result/query-receipt persistence, document retrieval, provider trace, buyer UI, or production evaluation corpus. Issue #61 owns those follow-up slices. Until the deterministic read projection exists, a semantically admitted but unavailable field must return `insufficient_evidence`; until a source is fetched and validated, a search result or snippet cannot satisfy an evidence requirement.

A new Analytics interface/bounded-context projection also requires Context Fabric / Enterprise Architecture owner-path registration using released context-graph identity/authority/truth-status/bitemporal/provenance contracts. The fleet loop does not mutate `context-graph-contracts` or `enterprise-architecture-core` while their dedicated Context Fabric writer is active; that owner path must record the canonical object/reference and architecture projection separately.

`docs/product-technical-gap-baseline.md` is a large historical live-state register whose current protected copy predates this slice and also contains historical ruleset observations. It must be refreshed as a full-document reconciliation from live GitHub evidence; it must not be replaced by a stub or partially reconstructed file.
