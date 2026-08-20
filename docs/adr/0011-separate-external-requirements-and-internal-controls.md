# ADR 0011: Separate external requirements from internal controls

- Status: Proposed
- Date: 2026-08-20
- Decision owners: CWL GRC maintainers
- Related issues: #13, #14, #27, #28, #29, #30

## Context

The first GRC slice intentionally used one compact path:

```text
policy_version
→ policy_control_mapping
→ control_item
→ control_evidence_binding
→ evidence_record
```

That path is useful for proving policy authoring, official identifier validation,
encrypted evidence storage, and a simple uncovered-requirement query. It is not
sufficient as the final enterprise GRC model.

`control_item` currently represents an externally published catalog requirement,
for example a CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001, NIST SP 800-53, or COSO
entry. An external requirement is not the same object as:

- the organization's reusable internal-control definition;
- one deployed implementation of that control;
- a design- or operating-effectiveness test;
- an exception or deficiency; or
- evidence used for a particular test and approved purpose.

Binding any artifact directly to an external requirement can therefore create a
false-positive coverage signal. It can also force future risk and audit features
to treat framework requirements as the controls that actually mitigate risk or
were tested in an engagement.

## Decision

CWL GRC will preserve `control_framework` and `control_item` as the external
requirement catalog and add a separate, normalized internal-control layer.

The intended trace is:

```text
regulatory_source / catalog_release
→ external requirement (`control_item`)
→ reviewed requirement mapping
→ internal-control definition and immutable version
→ tenant-scoped control implementation
→ control test plan and execution
→ design / operating effectiveness result
→ purpose-bound evidence usage
→ exception / deficiency / remediation
```

### External requirement catalog

`control_framework` and `control_item` remain shared catalog objects. Their
identity is edition-specific and source-governed. They do not carry tenant
implementation state or effectiveness conclusions.

### Internal-control definition

An `internal_control_definition` is a reusable organization-authored control.
A published `control_definition_version` is immutable. It records the control
objective, type, execution mode, expected frequency, expected evidence, and
reviewed wording without copying an external framework body.

### Control implementation

A `control_implementation` is tenant-scoped and links a control-definition
version to a referenced application, process, organization, data asset,
provider, or other approved scope. It records implementation status and
inherited/shared-responsibility boundaries. Those referenced domain bodies stay
in their authoritative CWL systems.

### Requirement mapping

A `control_requirement_mapping` is many-to-many and version-aware. It preserves
source and target release identities, reviewer, rationale, method, evidence,
and relation semantics. Compatible semantics include `equivalent_to`,
`equal_to`, `subset_of`, `superset_of`, `intersects_with`, and an explicitly
reviewed `no_relationship`.

An absent mapping does not mean there is no relationship. Automated or LLM
mappings remain proposed until an authorized reviewer approves them.

### Test and effectiveness truth

Control effectiveness is derived from an approved test plan and immutable test
execution/result, not from evidence presence alone. Design effectiveness and
operating effectiveness are distinct results. A test records period, method,
population/sample where relevant, performer, reviewer, conclusion, rationale,
and next-test obligation.

### Evidence usage

`evidence_record` remains the authoritative encrypted artifact. An
`evidence_usage` record states why and where that evidence was used, including
its approved purpose, implementation, test execution, procedure or finding,
period, reviewer, and reuse decision. The same artifact may support multiple
approved uses without duplicating plaintext.

Existing `control_evidence_binding` rows become a compatibility input. Migration
must preserve them as legacy unassessed evidence links and must not invent an
internal control, implementation, or effectiveness result.

## Consequences

### Positive

- A single internal control can satisfy several external requirements without
  duplicating the control body or evidence.
- Several controls can jointly satisfy one requirement.
- Risk assessments can consume actual implementation and effectiveness truth.
- Audits can distinguish criteria from the control being tested.
- Evidence presence no longer implies effectiveness.
- Requirement editions and internal-control history can evolve independently.
- OSCAL control-mapping exchange can be supported without making OSCAL or any
  external framework the internal database model.

### Costs

- The simple uncovered-control query becomes a compatibility projection and
  requires explicit status semantics.
- Migrations must preserve first-slice data without overstating assurance.
- API and UI work must expose `unknown`, `unassessed`, `design_effective`,
  `operating_effective`, `ineffective`, `exception`, and `stale` accurately.
- Risk, audit, obligation, and buyer-workspace work must depend on this model.

## Rejected alternatives

### Treat every external requirement as an internal control

Rejected because external sources and organization-designed controls have
independent ownership, versioning, applicability, implementation, and test
lifecycles.

### Copy one control for every framework mapping

Rejected because it duplicates semantics, evidence, ownership, and remediation
and makes cross-framework change impact unreliable.

### Keep direct evidence binding as the final effectiveness model

Rejected because an artifact can be irrelevant, stale, outside the test period,
insufficient, or evidence of a failed control.

### Build a second evidence store for testing and audit

Rejected because encrypted `evidence_record` remains the authoritative artifact.
Purpose-bound usage records provide context without copying plaintext.

## Implementation sequence

1. Merge the production foundations in #4, #8, #9, and #12 as their exact-head
   gates permit.
2. Implement #27 as the control-model foundation.
3. Migrate first-slice evidence bindings as unassessed compatibility records.
4. Update risk #13 and audit #14 to consume internal-control implementation and
   effectiveness truth.
5. Implement obligation/applicability #28 and catalog interoperability #29.
6. Build the buyer workspace and controlled export surface in #30.

## Standards and source constraints

The design follows COSO internal-control separation and the NIST OSCAL Control
Mapping Model's machine-readable many-to-many relationship semantics. External
source text remains subject to its publisher's licensing and redistribution
rules. This ADR does not authorize copying licensed standards or claiming
certification.
