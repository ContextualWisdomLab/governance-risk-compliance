# Evidence request workflow

The evidence-request slice lets a compliance officer request a defined
evidence package from one contributor and record a separate review outcome.
It is a local-preview contract behind the existing loopback boundary; it is
not an auditor data room or production identity claim.

## Workflow

```text
requester creates scope/period/fields/due/reuse policy
    -> named contributor submits an existing same-tenant evidence record
    -> different reviewer accepts or rejects with an audit event
```

`POST /evidence-requests` requires `compliance_governance` and, in Keyverse
mode, `grc.compliance.write`. The request stores metadata-only field names;
it never copies or masks evidence payloads. `POST
/evidence-requests/{id}/submissions` links an existing same-tenant artifact.
`POST /evidence-requests/{id}/review` records `accepted` or `rejected` and
requires a rejection reason for the latter. `GET /evidence-requests` returns
request metadata and append-only audit history without payload text.

The state contract is `requested`, `submitted`, `accepted`, or `rejected`.
Rejected requests are terminal in this first slice; a corrected package uses a
new request so audit history cannot be confused with a prior submission.
Reuse is explicit as `single_use` or `reusable`; downstream evidence use still
requires its own purpose and control-test contract.

`GET /compliance-workspace` now includes exact evidence-request rows,
state-count posture, and deterministic next actions. Risks, audit programs,
controlled exports, data-room access, and automated disposition remain
explicitly outside the projection.
