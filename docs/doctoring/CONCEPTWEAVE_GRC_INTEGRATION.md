# ConceptWeave ↔ GRC integration traceability

Snapshot date: 2026-09-02

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
- GRC Analytics parent: `ContextualWisdomLab/governance-risk-compliance#62`, live stack coordinate `dbe7f5d42db0bb1b24d8a0b51eae5032d098d7f5` at this snapshot
- GRC semantic-client stacked implementation: `ContextualWisdomLab/governance-risk-compliance#64`; its exact head is intentionally re-read before every integration decision because this Draft is active
- ConceptWeave Generation vertical: `ContextualWisdomLab/ConceptWeave#2`
- ConceptWeave Client/release owner path: `ContextualWisdomLab/ConceptWeave#3`; current Rust-first Client Draft is PR #5 at `ebf7acc9963e841073bbd700f118faade741ed2b` at this snapshot
- ConceptWeave foundation dependency: PR #1 at `bba351b77bf5f1ab5cfd55979fbb2bd158f78b81` at this snapshot

These issue, PR, and branch-head coordinates are traceability aids, not immutable runtime contract identifiers. Implementations must bind released semantic artifacts to their own version/digest/provenance coordinates, and live GitHub state must be re-read before integration. Open ConceptWeave PR heads are supplier-development evidence only; GRC must not treat them as a released runtime dependency.

## TDD evidence

The GRC child started with a test-only specification. Exact head `15162eb4d8bca7fcbe8249524b47c7f6b6729b8a` was checked out by Product workflow run `33481862830`; lint and docstring gates passed, while pytest failed during collection with `ModuleNotFoundError` for the intentionally absent `cwl_grc.analytics.application.semantic_model`. This is the RED evidence for the new boundary.

The initial production implementation introduced `SemanticModelClientPort`, immutable `SemanticReleaseRef`, publication-state coordinates, and fail-closed `require_published_release`.

A later degraded-mode regression found that malformed non-string digest input could escape the consumer boundary as a raw Python exception. Test-only exact head `994b7d99627b49391f6a36790fe2ea39d01ab48a` was checked out by Product workflow run `33490857219`, job `99801746540`; lint and docstrings passed, then tests/coverage failed. This is the RED evidence for the typed malformed-release failure contract required by GRC #63 acceptance criterion 6.

The minimal causal repair validates digest type/length/hex shape before regex evaluation and raises `SemanticReleaseValidationError` for malformed release coordinates. Exact source-fix head `e7a97bd406ad97db4a36f6a1746e6bbc6b288374` passed Product workflow run `33491038085`, job `99802333337`, including exact-source verification, runner hardening, hash-locked install, Ruff, docstrings, tests/coverage, compile, lock freshness, and clean-tree verification.

A further consumer-boundary defect allowed a published release with empty, whitespace-only, or non-string `release_id` / `schema_version` coordinates to pass local validation. The test-only exact head `5c78844f784cf87f8ec000bdcc9927fa26530923` was checked out by Product workflow run `33495770373`, job `99817487833`; exact-source verification, Ruff, and docstrings passed before the tests/coverage step failed on all six malformed coordinate cases. The causal source repair rejects those incomplete coordinates with `SemanticReleaseValidationError` before any supplier adapter can be invoked. Exact source-fix head `7f617feb8da8c5c5066eaf2027bbfae678eb2664` passed Product workflow run `33495993046`, job `99818202657`, including exact-source verification, runner hardening, hash-locked install, Ruff, docstrings, tests/branch coverage, compile, lock freshness, and clean-tree verification.

The resource-boundary regression was also test-first. Exact test-only head `f1751a97873691beb24419224bef8182521e0755` added 1025-character `release_id` and `schema_version` cases. Product `33541318575` / job `99967978864` checked out that exact head, passed lint and docstrings, and failed tests/coverage because the oversized coordinates were still normalized and accepted. Minimal source-fix head `966762af502365b3a230597c04ac12dc1928ab3e` caps both coordinates at 1024 characters before `.strip()` and passed exact-head Product `33541503511`. The 1024-character cap is a GRC-owned operational resource bound, not a guessed ConceptWeave schema rule; a released supplier contract may impose stricter compatibility constraints.

These local coordinate-shape checks do not guess ConceptWeave's wire schema. Supported schema versions, release provenance, signature policy, support window, declared digest syntax, digest-to-content integrity, deterministic release diff, concept/relation resolution, mappings, dimensions and measures remain bound to the generic published Client contract. ConceptWeave PR #5 already exercises Rust-first offline admission, deterministic release diff and exact serialized-byte digest verification, but it is Draft and unreleased, so GRC still does not implement a concrete supplier adapter against that moving head.

Documentation-only commits after a source-fix head do not transfer its hosted evidence to a later exact PR head. The current exact head must always be revalidated before review or integration.

## Required end-to-end acceptance

A production-complete integration requires all of the following:

1. ConceptWeave publishes a stable `semantic_release` contract and Rust-first reference client from #3 / its protected successor.
2. GRC implements an ACL/adapter against that published contract rather than a guessed private endpoint.
3. GRC can validate a release offline, including version, digest, provenance, publication state, support policy and compatibility.
4. GRC rejects proposed, superseded, malformed, unknown-version, unsupported, or integrity-invalid releases for authoritative semantic analysis.
5. Concept resolution and physical mappings do not widen Keyverse tenant/workspace/purpose authorization.
6. GRC deterministic query results remain reproducible for the same GRC snapshot + semantic release + query contract.
7. A ConceptWeave release diff identifies GRC queries/reports whose semantic assumptions changed without automatically mutating GRC truth.
8. Inferred/proposed ConceptWeave or LineageWeave relations cannot mutate authoritative GRC records.
9. LLM-assisted generation/matching/query interpretation routes only through `contextual-orchestrator` and remains proposed evidence.
10. The systematic GRC investigation path keeps GRC facts, semantic assertions, lineage inference, and external-source evidence distinguishable in the final Evidence Graph and query receipt.

## Degraded mode

If ConceptWeave or an online matching service is unavailable, GRC may continue core policy/control/evidence transactions and may consume a locally cached release only when its version, integrity, provenance, authorization applicability and support window are still valid under the released client contract. It must not silently fall back to an unvalidated ontology, Naive RAG, raw vector similarity, or an LLM-generated semantic model. Proposed, superseded, unknown-version, unsupported, malformed, or integrity-invalid release coordinates must fail semantic analysis closed with an actionable typed outcome while authoritative GRC operations continue.
