# ADR 0005: Bind GRC-owned records to the verified Keyverse tenant

## Status

Accepted for the tenant-isolation slice stacked after verified HTTP principals.

## Context

The access-token and route-enforcement slices prove a Keyverse principal and derive an exact tenant claim, but the first product schema stored policies, policy editions, evidence, bindings, and audit events without tenant ownership. Application-only filtering would still permit a direct SQL writer, migration defect, or future code path to create a child row whose `tenant_id` disagrees with its parent.

The public control catalog is shared reference data. Policy bodies, policy mappings, evidence payloads, evidence bindings, and audit events are customer-owned records and must not reveal another tenant's existence or accept another tenant's identifiers.

## Decision

1. Persist a non-null `tenant_id` on every GRC-owned policy, evidence, binding, and audit record. In Keyverse mode it comes only from the verified signed principal. The fixed `local_development` tenant exists solely for the loopback-only standalone compatibility profile and for backfilling pre-tenant preview data.
2. Require `grc.policy.read` for policy and policy-gap reads whenever Keyverse authentication is configured. Filter every protected read by the verified tenant.
3. Return `404 Not Found` for cross-tenant policy or evidence identifiers so an authorized caller cannot distinguish another tenant's object from a nonexistent object.
4. Define tenant-parent relationships as paired keys. New schemas use named composite `ForeignKeyConstraint` relationships for policy document → policy version → policy mapping and evidence record → evidence binding. Pairing the columns is essential; independent single-column keys do not express that both values belong to the same parent row.
5. Install idempotent SQLite and PostgreSQL tenant-parent guards so databases created before the composite constraints receive the same fail-closed behavior without rewriting protected history.
6. Keep `control_framework`, `control_item`, and `authorization_purpose` outside the tenant-owned set. They are shared catalog or authorization vocabulary, not customer records.
7. Keep the loopback-only network boundary. Tenant isolation is necessary but is not sufficient to authorize remote deployment; verified issuer loading, authorization decisions, production deployment controls, and operator evidence remain separate gates.

## Consequences

- Same-tenant policy authoring, revision, evidence creation, binding, and gap reads remain available.
- Cross-tenant list reads return no records, and guessed cross-tenant mutation identifiers fail as not found.
- Database constraints or equivalent guards reject mismatched tenant-parent relationships even when the application layer is bypassed.
- Existing preview rows are assigned to `local_development`; they are not automatically attributed to a real customer tenant.
- Future PostgreSQL row-level security may add defense in depth, but it cannot replace composite relationship integrity or verified application authorization.

## Rejected alternatives

- **Caller-supplied tenant headers**: rejected because they are not identity or authorization evidence.
- **Application filters only**: rejected because database writers and future code paths could create structurally inconsistent cross-tenant rows.
- **One global policy/evidence namespace with authorization only at export time**: rejected because it leaks existence and creates unsafe internal joins.
- **Blanket masking of evidence**: rejected because authorized GRC work needs exact values; the control is tenant- and purpose-bound access, encryption, retention, and audit.

## Verification

The regression suite must prove:

- all tenant-owned models require `tenant_id`;
- unauthenticated or under-scoped policy reads fail in Keyverse mode;
- tenant B cannot list, revise, gap-query, or bind tenant A records;
- direct database inserts cannot pair a tenant B child with a tenant A policy or evidence parent;
- local standalone behavior remains confined to `local_development`;
- production statement and branch coverage and public docstrings remain 100%.

## References

Joint Task Force. (2020). *Security and privacy controls for information systems and organizations* (NIST Special Publication 800-53, Revision 5; Release 5.2.0). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-53r5

SQLAlchemy authors. (2026). *Defining constraints and indexes* (SQLAlchemy 2.0.51 documentation). https://docs.sqlalchemy.org/en/20/core/constraints.html
