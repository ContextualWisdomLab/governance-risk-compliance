# ADR 0011: Separate external requirements from internal controls

## Status

Proposed; requires independent review and protected merge at the exact source
head. The local implementation is a buyer-slice data and kernel contract, not
production authorization or release evidence.

## Context

The first slice treated a direct `control_evidence_binding` as coverage. That
collapses four different facts: an external requirement, an organization’s
control design, a scoped implementation, and evidence used by a dated test.
It can therefore imply effectiveness without a reviewed internal control or a
design/operating conclusion. It also cannot represent reviewed many-to-many
crosswalks or preserve legacy bindings without rewriting history.

COSO’s 2013 Internal Control—Integrated Framework is the control-design basis.
NIST’s OSCAL Control Mapping Model v1.2.3 is the interoperability basis for
machine-readable relationships among control sources; its relationship model
includes equivalence, subset, superset, intersection, and explicit gaps.
Official references are recorded in `docs/doctoring/REFERENCES.md`.

Applicability and regulatory-change truth is deliberately handled by ADR 0012;
this decision starts after an obligation has been linked to an internal control
and does not make a framework mapping a legal applicability decision.

## Decision

1. Keep `control_framework` and `control_item` as the shared official external
   catalog. Do not copy external control bodies into tenant-owned records.
2. Store tenant-owned `control_objective`, reusable
   `internal_control_definition`, immutable `control_definition_version`, and
   scoped `control_implementation` rows separately.
3. Store temporal `control_owner_assignment` rows and require accountable,
   operator, or reviewer ownership to be explicit.
4. Store reviewed `control_requirement_mapping` rows as a many-to-many relation
   with `equivalent_to`, `subset_of`, `superset_of`, or `intersects_with`.
   Missing mappings do not mean that two requirements have no relationship.
5. Store design or operating `control_test_plan`, completed historical
   `control_test_execution`, immutable `control_test_result`,
   `control_exception`, and `control_deficiency` rows separately.
6. Store purpose-approved `evidence_usage` against a specific implementation
   and completed test. Evidence outside the test period cannot satisfy it.
   A legacy direct binding is backfilled as `unassessed` compatibility data and
   never creates an effectiveness conclusion.
7. Project external requirements through explicit statuses:
   `unknown`, `unassessed`, `implemented_not_tested`, `design_effective`,
   `operating_effective`, `ineffective`, `exception`, `stale`, and
   `not_applicable`. Only `operating_effective` and an authorized
   `not_applicable` are absent from an uncovered query.
8. Enforce tenant-parent identity with composite foreign keys in SQLite and
   PostgreSQL, enable SQLite foreign keys, and protect immutable definition
   versions, mappings, test history, results, and evidence usage at the
   database boundary.
9. Keep the existing HTTP bind route as a compatibility path. It stores a
   legacy direct binding and tells the officer to establish the control test;
   stable internal-control APIs remain a later authenticated contract after
   the identity and API-boundary issues are complete.

## Consequences

- Direct evidence is no longer mistaken for operating effectiveness.
- A single internal control can map to many official controls, and several
  internal controls can map to one official control without duplicating catalog
  text.
- The migration is additive and preserves exact legacy evidence and PII. It
  records an explicit compatibility classification rather than inventing test
  outcomes.
- The current officer UI is server-rendered and remains a local preview. No
  Figma or Storybook component-system work is introduced by this backend/domain
  slice; add those artifacts when the tenant workspace and evidence-room UI is
  implemented.
- Temporal history and immutable rows support reproducible audit reconstruction.
  Physical partitioning, load testing, and production export/read models remain
  deployment gates rather than unverified claims.

## Verification

- `tests/test_internal_controls.py` exercises the complete SQLite workflow,
  status projection, rejection paths, migration backfill, immutable triggers,
  and cross-tenant composite keys.
- PostgreSQL 18 runtime probing covers schema creation, seed data, evidence
  usage, operating effectiveness, composite tenant rejection, and immutable
  result mutation rejection.
- Product CI remains the source of truth for exact-head lint, docstring, test,
  branch coverage, compile, lock, and clean-tree checks.
