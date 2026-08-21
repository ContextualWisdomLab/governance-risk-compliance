# ADR 0008: Admit only truthful local-preview readiness

## Status

Accepted for the first operational-readiness slice.

## Context

The service previously exposed one constant `/healthz` body. That was useful as
a liveness signal but could not distinguish a live process from an instance with
an unavailable database, incomplete schema, missing catalog seeds, missing
database guards, or unusable evidence-key material. Request failures also had no
safe correlation contract.

## Decision

1. Keep `/healthz` dependency-free and constant. Add `/readyz` for current
   database, schema-receipt, seed, integrity-guard, evidence-key, identity, and
   lifecycle checks. Add `/startupz` for the checks that admitted the process.
2. Run the same startup checks before `create_app()` returns. A failed check
   raises a reason-coded error; a persistent store still requires durable key
   material through the existing encryption contract.
3. Admit only `local_preview` in this slice. Production configuration fails
   closed until the remote Keyverse boundary is implemented; a configured
   Keyverse verifier is still supported for local protected-route tests.
4. Give PostgreSQL connections a three-second connection timeout. Readiness
   returns `503` with stable reason codes and no exception, schema, key, or
   evidence details.
5. Generate or preserve bounded `X-Request-ID` and valid W3C `traceparent`
   values. Return the request reference on application and validation errors.
6. Emit JSON request logs containing service, version, environment, correlation,
   route, outcome, status, and latency. Verified tenant/actor pairs are one-way
   referenced; raw tokens, keys, plaintext, bodies, and unrelated PII are not
   logged.
7. Mark the process draining during router shutdown and reject new mutating
   requests while keeping liveness available. In-flight request completion and
   pool disposal remain the server runtime's bounded shutdown responsibility.

## Consequences

- Operators can route traffic only to an instance whose local dependencies and
  integrity guards are currently usable.
- Kubernetes-style probes can distinguish process liveness, startup admission,
  and dependency readiness. See the official [Kubernetes probe guidance](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
- Local logs can correlate failures without becoming an evidence or identity
  exfiltration channel.
- OpenTelemetry exporters, request/database metrics, SLOs, burn-rate alerts,
  dashboards, and full incident runbooks remain follow-up platform integration;
  this ADR does not claim production observability certification.

## Verification

Tests cover healthy and failed database/schema/seed/guard/key checks, production
startup refusal, drain behavior, valid and malformed correlation headers,
safe HTTP validation/error responses, hashed principal logs, and PostgreSQL
connection-timeout construction. The complete local suite remains at 100%
statement and branch coverage.
