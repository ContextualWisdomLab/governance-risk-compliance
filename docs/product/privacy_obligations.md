# Privacy obligations: product requirements and technical action register

Status: Proposed implementation baseline for GRC #69, 2026-09-09. The scope is
Korean PIPA and applicable implementing rules, independently of advertisements.
Additional jurisdictions or sector statutes require their own applicability
review. No row below is a declaration that CWL or a customer is legally compliant.

## Product result and responsibility

An officer must be able to connect a specific legal requirement and its
applicability to an implemented control, actual test/deployment evidence,
responsible role and corrective action. Product data remains with its owner.
GRC owns obligations, applicability, control conclusions, management decisions
and corrective verification. Shared schemas remain with context-graph-contracts;
released contracts, not sibling branch source or direct SQL, are consumed.

A tenant is not necessarily one legal entity. An identity account is not a
legal CPO appointment. A source snapshot is not a deployed control. Artifact
presence is not control effectiveness. A read receipt is not a management
approval, and a budget approval is not expenditure or verified remediation.

## Legal and implementation work packages

The article references below identify required review/work scopes, not new
seeded framework identifiers. Exact subordinate rules and entity facts must
accompany an approved applicability decision. See [sources](../doctoring/privacy_law_sources.md).

| Work package | Statutory review scope | Canonical owner and implementation acceptance |
| --- | --- | --- |
| Processing inventory and lawful scope | Articles 15–18, 20; purpose and minimization | Each product records categories, purpose, legal basis, sources/recipients and authority; SDP references assets/flows without copying values; GRC reviews applicability. Consent is not presumed to be the only lawful basis. |
| Special data and children | Articles 22, 22-2, 23, 24, 24-2 | Product-specific restricted intake, necessary separate consent or statutory basis, representative verification where applicable, no unauthorized collection. Test default denial and actual authorized use. |
| Processor and international-transfer governance | Articles 26, 28-8 | GRC stores assessed obligations and contract references; product/CO applies approved processor/account/endpoint conditions. Test each fallback and modality; unknown/expired terms cannot authorize a new personal-data transfer. |
| Access authority and secure sessions | Article 29; L2 Articles 5–6 | Keyverse owns authenticated principals; product enforces tenant/purpose/resource access. This change repairs only GRC's existing local HTTP boundary. No remote PII deployment before the identity stack and operational verification. |
| Encryption and key custody | Article 29; L2 encryption requirements | Keyverse-owned credential/key service integration and scoped references; no secret payload in logs, URLs or checked-in configuration. Durable evidence key recovery/rotation needs real rehearsal; an environment-key preview is not that implementation. |
| Access records and detection | Articles 28–29; L2 access-record requirements | Each processing owner records protected, attributable access evidence; Wardnet consumes security observations. Statutory access records are distinct from sampled operational traces; suppressing raw prompts in telemetry does not authorize deleting required audit evidence. |
| Retention, destruction and recovery | Article 21; L2 destruction requirements | Product deletes/disposes data according to reviewed grounds; track chunks, embeddings, indexes, caches, exports, backups and provider copies. Verify restoration cannot resurrect erased records. A legal hold needs lawful scope, reason, reviewer and review date, not an unlimited toggle. |
| Notices and data-subject requests | Articles 30, 35–38; L6 procedure review | Product-owned intake, proportionate requester/representative verification, access/correction/erasure/restriction and reasoned responses. Test partial failures, other-person data separation and evidence receipts. Portability and automated-decision duties need their own conditions, not universal flags. |
| Incident assessment and response | Article 34 plus L3 transitional provisions | Wardnet supplies observations; GRC owns factual assessment and legal notification/report decisions. Preserve observed, occurred, awareness and submission times separately. Unknown impact is not no impact; notification and regulator reporting are distinct. |
| CPO and management accountability | Article 31; L3 Articles 30-3 and 31 | Actual appointment/qualification and required board/reporting evidence; immutable submitted report revision, review, decision, resources, action owner and retest. No self-appointed CPO inferred from an administrator role. |
| Workforce and processor oversight | Articles 26 and 28 | Actual training, staff access review, contractor controls and evidence; Orgmetra/learning products retain their own records; GRC consumes scoped receipts. |
| Conditional impact assessment/certification | Article 33; L3 Article 32-2 | Evaluate public-body/scale and other actual statutory conditions. Do not apply PIA or mandatory ISMS-P to every company; do not claim certified because tests pass. Certification change starts 2027-07-01, not 2026-09-11. |

All work packages remain open for organizational and deployed evidence. The
existing GRC identity/internal-control/applicability stacks must be reconciled,
not replaced. No generic risk-acceptance approval waives a mandatory legal duty.

## Implemented source slice and acceptance

`cwl_grc/remote_access.py` and `create_app` integration now propose direct-peer,
local-authority and browser-context checks before body consumption or handler
execution. Present-empty forwarding, ambiguous headers, mismatched/null
origins and unsupported WebSockets fail closed. Authorized preview payloads
remain byte-preserved. Responses traversing the guard are non-cacheable and
cannot be framed. See the [Proposed ADR](../adr/proposals/privacy_request_boundary.md).

`tests/test_privacy_boundary.py` exercises the production middleware directly.
`tests/test_privacy_routes.py` is the full-product route/state regression.
Existing form tests add an explicit legitimate same-origin request, retaining
all original domain assertions. There is no global test header or policy bypass.

## Technical contracts for remaining work

An applicability decision must bind legal-source revision, exact article,
legal-entity reference, processing-activity reference, valid interval, review
state and evidence reference. `unknown` and `not_applicable` differ; the latter
requires reviewed grounds. Published source date, effective date, observation
time and incident applicability clock are not one field.

A control conclusion must bind owner release/digest, deployment configuration
reference, test execution and period, observed outcomes, missing/failed
collection counts and verifier. Missing observations are unassessed, never a
zero-failure denominator or compliant score. Generated narrative cannot change
verified data or promote an inference into legal approval.

Interoperability uses authenticated owner APIs and versioned events, with
idempotent receipts and tenant-bound opaque references. No personal values in
public source, issue bodies, event broadcasts or ordinary LLM traces. Approved
work can retrieve exact necessary values through a purpose-authorized owner;
blanket masking is not the substitute for an access and lifetime boundary.

## Release and organizational closure

Local module GREEN → full locked Product GREEN → security and independent
current-head review → protected integration → immutable release → deployed
control test → reviewed applicability/organizational evidence. These are separate
states, not synonyms. Maintain GRC #69 until all applicable work packages meet
their criteria; source repair alone must not close it.
