# ConceptWeave ↔ GRC integration traceability

Snapshot date: 2026-09-01

## Product responsibility map

| Responsibility | Authoritative owner | GRC integration rule |
| --- | --- | --- |
| GRC policy/control/risk/audit/evidence facts | `governance-risk-compliance` | Never copied into ConceptWeave as a competing operational ledger |
| Semantic-model generation and publication | `ConceptWeave` | Consume only published versioned release/client contracts |
| Production model/provider routing | `contextual-orchestrator` | No direct provider SDK or credential in GRC or ConceptWeave feature code |
| Lineage inference/provenance expansion | `LineageWeave` | Preserve observed/inferred/proposed status; never auto-promote to GRC truth |
| Semantic catalog/search/governance plane | `semantic-data-portal` | Catalog and distribute published artifacts; do not duplicate generation |
| External search candidate discovery | SearXNG adapter | Snippets are candidates, not evidence; fetch and validate original sources |

## Cross-repository coordinates

- GRC integration issue: `ContextualWisdomLab/governance-risk-compliance#63`
- GRC Analytics parent: `ContextualWisdomLab/governance-risk-compliance#62`
- GRC semantic-client stacked implementation: `ContextualWisdomLab/governance-risk-compliance#64`
- ConceptWeave Generation vertical: `ContextualWisdomLab/ConceptWeave#2`
- ConceptWeave Client/release contract: `ContextualWisdomLab/ConceptWeave#3`

These issue and PR numbers are navigation aids, not immutable runtime contract identifiers. Implementations must bind released semantic artifacts to their own version/digest/provenance coordinates.

## TDD evidence

The GRC child started with a test-only specification. Exact head `15162eb4d8bca7fcbe8249524b47c7f6b6729b8a` was checked out by Product workflow run `33481862830`; lint and docstring gates passed, while pytest failed during collection with `ModuleNotFoundError` for the intentionally absent `cwl_grc.analytics.application.semantic_model`. This is the RED evidence for the new boundary.

The production implementation introduced `SemanticModelClientPort`, immutable `SemanticReleaseRef`, publication-state coordinates, and fail-closed `require_published_release`. Exact implementation head `d4bb099ac2f68fa7e0d25904fc9b44717b056095` passed Product workflow run `33482003991`, including exact-source verification, Ruff, Interrogate 100%, tests/branch coverage at repository threshold, compile, lock freshness, and clean-tree verification.

Any later head movement invalidates those run identities as merge evidence; the current exact head must be revalidated.

## Required end-to-end acceptance

A production-complete integration requires all of the following:

1. ConceptWeave publishes a stable `semantic_release` contract and Rust-first reference client from #3.
2. GRC implements an ACL/adapter against that published contract rather than a guessed private endpoint.
3. GRC can validate a release offline, including version, digest, provenance, publication state, and compatibility.
4. GRC rejects proposed, superseded, malformed, unknown-version, or integrity-invalid releases for authoritative semantic analysis.
5. Concept resolution and physical mappings do not widen Keyverse tenant/workspace/purpose authorization.
6. GRC deterministic query results remain reproducible for the same GRC snapshot + semantic release + query contract.
7. A ConceptWeave release diff identifies GRC queries/reports whose semantic assumptions changed.
8. Inferred/proposed ConceptWeave or LineageWeave relations cannot mutate authoritative GRC records.
9. LLM-assisted generation/matching/query interpretation routes only through `contextual-orchestrator` and remains proposed evidence.
10. The systematic GRC investigation path keeps GRC facts, semantic assertions, lineage inference, and external-source evidence distinguishable in the final Evidence Graph and query receipt.

## Degraded mode

If ConceptWeave or an online matching service is unavailable, GRC may continue core policy/control/evidence transactions and may consume a locally cached release whose version, integrity, authorization applicability, and support window are still valid. It must not silently fall back to an unvalidated ontology, Naive RAG, raw vector similarity, or an LLM-generated semantic model. If no valid semantic release is available, semantic analysis fails closed with an actionable typed outcome while authoritative GRC operations continue.
