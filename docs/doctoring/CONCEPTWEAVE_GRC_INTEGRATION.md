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
- GRC Analytics parent: `ContextualWisdomLab/governance-risk-compliance#62`, current stack coordinate `72e0120085430a269a73c0503bcab307fd2e645c`
- GRC semantic-client stacked implementation: `ContextualWisdomLab/governance-risk-compliance#64`
- ConceptWeave Generation vertical: `ContextualWisdomLab/ConceptWeave#2`
- ConceptWeave Client/release contract: `ContextualWisdomLab/ConceptWeave#3`

These issue, PR, and branch-head coordinates are traceability aids, not immutable runtime contract identifiers. Implementations must bind released semantic artifacts to their own version/digest/provenance coordinates, and live GitHub state must be re-read before integration.

## TDD evidence

The GRC child started with a test-only specification. Exact head `15162eb4d8bca7fcbe8249524b47c7f6b6729b8a` was checked out by Product workflow run `33481862830`; lint and docstring gates passed, while pytest failed during collection with `ModuleNotFoundError` for the intentionally absent `cwl_grc.analytics.application.semantic_model`. This is the RED evidence for the new boundary.

The initial production implementation introduced `SemanticModelClientPort`, immutable `SemanticReleaseRef`, publication-state coordinates, and fail-closed `require_published_release`.

A later degraded-mode regression found that malformed non-string digest input could escape the consumer boundary as a raw Python exception. Test-only exact head `994b7d99627b49391f6a36790fe2ea39d01ab48a` was checked out by Product workflow run `33490857219`, job `99801746540`; lint and docstrings passed, then tests/coverage failed. This is the RED evidence for the typed malformed-release failure contract required by GRC #63 acceptance criterion 6.

The minimal causal repair validates digest type/length/hex shape before regex evaluation and raises `SemanticReleaseValidationError` for malformed release coordinates. Exact source-fix head `e7a97bd406ad97db4a36f6a1746e6bbc6b288374` passed Product workflow run `33491038085`, job `99802333337`, including exact-source verification, runner hardening, hash-locked install, Ruff, docstrings, tests/coverage, compile, lock freshness, and clean-tree verification.

Documentation-only commits after that source-fix head do not transfer its hosted evidence to a later exact PR head. The current exact head must always be revalidated before review or integration.

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

If ConceptWeave or an online matching service is unavailable, GRC may continue core policy/control/evidence transactions and may consume a locally cached release whose version, integrity, authorization applicability, and support window are still valid. It must not silently fall back to an unvalidated ontology, Naive RAG, raw vector similarity, or an LLM-generated semantic model. Proposed, superseded, unknown-version, malformed, or integrity-invalid release coordinates must fail semantic analysis closed with an actionable typed outcome while authoritative GRC operations continue.
