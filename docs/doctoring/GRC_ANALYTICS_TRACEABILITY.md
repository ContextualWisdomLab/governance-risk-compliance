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

## Research traceability

The architecture uses stable standards for provenance and graph validation rather than treating retrieved text as self-authenticating truth. W3C PROV-O is a Recommendation for representing entities, activities, agents, derivations, and provenance relationships. W3C SHACL is a Recommendation for validating RDF graphs against explicit shapes and is therefore the normative baseline for future ontology/Evidence Graph conformance; later SHACL drafts are not silently treated as released requirements. These standards support the product contract's requirement to retain source/origin, relation status, and validation evidence instead of collapsing all retrieved material into one untyped chunk store.

SearXNG's current Search API documentation (`2026.8.29+d226b78bc`) describes a metasearch query interface and configurable result formats. It does not make returned snippets authoritative evidence. The GRC contract therefore treats search output as candidate discovery only and requires a separate source-fetch, validation, provenance, authority, and citation receipt before external material enters the Evidence Graph.

Lewis et al. (2020) introduced retrieval-augmented generation as a combination of parametric and non-parametric memory while explicitly identifying provenance and world-knowledge updating as open problems for knowledge-intensive generation. That research supports using retrieval as an evidence-access mechanism, not as a replacement for deterministic semantic measures, source validation, authorization, or governance truth. NIST AI 600-1 supplies a current cross-sectoral GenAI risk-management profile, while OWASP LLM01:2025 explicitly notes that RAG and fine-tuning do not fully mitigate prompt-injection risk. Accordingly, the GRC design treats external and retrieved instructions as untrusted data, preserves deterministic authorization/tool boundaries, and requires evidence-bound synthesis rather than prompt authority.

### APA 7 references

Autio, C., Schwartz, R., Dunietz, J., Jain, S., Stanley, M., Tabassi, E., Hall, P., & Roberts, K. (2024). *Artificial intelligence risk management framework: Generative artificial intelligence profile* (NIST AI 600-1). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.AI.600-1

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-T., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*. https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html

OWASP GenAI Security Project. (2025). *LLM01:2025 prompt injection*. https://genai.owasp.org/llmrisk/llm01-prompt-injection/

SearXNG contributors. (2026). *Search API* (Documentation version 2026.8.29+d226b78bc). Retrieved September 1, 2026, from https://docs.searxng.org/dev/search_api.html

World Wide Web Consortium. (2013). *PROV-O: The PROV ontology*. https://www.w3.org/TR/prov-o/

World Wide Web Consortium. (2017). *Shapes Constraint Language (SHACL)*. https://www.w3.org/TR/shacl/

## Verification performed for this slice

The Analytics contract and architecture suites preserve the repository's 100% owned-production statement and branch coverage requirement. Review-driven regression coverage verifies DST-fold ordering by actual instant, valid extreme-offset boundary dates without UTC-conversion overflow, malformed runtime intents as typed abstentions instead of exceptions, resource bounds before collection scans, strict Analytics dependency ownership, and the non-overridable read-only plan invariant.

The exact-head Product lane exposed a real 99.67% coverage regression after the resource-bound repair. The repair removed one unreachable duplicate tuple-shape branch and added the missing malformed-measure regression rather than lowering the coverage denominator or threshold. Repository-hosted Product and central required workflows remain authoritative for integration, dependency, SAST, security, and independent-review evidence on each new exact pull-request head.

## Deferred acceptance evidence

This first slice intentionally does not implement the authoritative read projection, ontology resolver, context-graph adapter, LineageWeave ACL, SearXNG research connector, primary-source validator, Evidence Graph, SQL/DSL executor, contextual-orchestrator call, result/query-receipt persistence, document retrieval, provider trace, buyer UI, or production evaluation corpus. Issue #61 owns those follow-up slices. Until the deterministic read projection exists, a semantically admitted but unavailable field must return `insufficient_evidence`; until a source is fetched and validated, a search result or snippet cannot satisfy an evidence requirement.

A new Analytics interface/bounded-context projection also requires Context Fabric / Enterprise Architecture owner-path registration using released context-graph identity/authority/truth-status/bitemporal/provenance contracts. The fleet loop does not mutate `context-graph-contracts` or `enterprise-architecture-core` while their dedicated Context Fabric writer is active; that owner path must record the canonical object/reference and architecture projection separately.

`docs/product-technical-gap-baseline.md` is a large historical live-state register whose current protected copy predates this slice and also contains historical ruleset observations. It must be refreshed as a full-document reconciliation from live GitHub evidence; it must not be replaced by a stub or partially reconstructed file.
