# Organization OpenTelemetry evidence runbook

Use this runbook when accepting or reviewing telemetry for the first-party
service boundary. The next action after each failed step is shown explicitly;
do not treat a local in-memory metric reader as production monitoring.

## 1. Confirm the approved collector boundary

1. Configure `OTEL_EXPORTER_OTLP_ENDPOINT` only with the approved collector
   endpoint in the deployment secret/configuration store.
2. Confirm the collector accepts OTLP HTTP traces and metrics and forwards them
   to the approved trace and metric backends.
3. Record the collector version, observation window, and delivery result in the
   review evidence. Never record endpoint credentials or raw telemetry.

If the collector is unavailable, remove the endpoint from the deployment,
return the service to its bounded local no-export mode, and keep the instance
out of production acceptance.

## 2. Verify the first-party service contract

| Boundary | Required evidence |
| --- | --- |
| `cwl-grc` | Request span/metric, authorization denial, database transaction, pool, and recovery contracts; route-template cardinality remains bounded. |
| `lineageweave` | HTTP and Valkey access spans use the shared post session correlation and contain no post body, prompt, provider response, or secret. |
| `contextual-orchestrator` | Gateway request, workflow, agent, and provider spans preserve the caller session correlation without recording prompt/answer content or credentials. |
| Valkey access | Calling-service spans identify the Valkey dependency with bounded database attributes; server-native exporter evidence is added only when the deployment actually provides one. |

For each boundary, verify W3C `traceparent` propagation, an ordinary success
operation, an error operation, and the documented rollback/no-export path.
Attach aggregate counts and pass/fail results, not customer titles, names,
post identifiers, prompts, answers, tokens, or provider payloads.

## 3. Bind the result in GRC

1. Create one encrypted evidence record through the existing
   `evidence_binding` purpose boundary.
2. Include only the service names, contract version, observation window,
   collector delivery result, metric/route contract result, propagation result,
   redaction result, and operator next action.
3. Bind the evidence to the applicable official control and establish the
   reviewed control test. A direct evidence binding remains `unassessed` until
   that control test concludes.

Do not create a telemetry table, copy raw spans, or use a composite application
session key as a substitute for the normalized evidence and control model.

## 4. Recovery and re-verification

When a collector or service exporter fails, preserve the failure reason and
observation window, switch to the approved no-export mode, and restore the
collector before retrying. Re-run all four boundary checks after any exporter,
collector, route-template, session-correlation, or Valkey client change.

The GRC `/healthz`, `/readyz`, and `/startupz` probes remain the deployment
admission checks. A successful probe without collector acceptance is not
production telemetry evidence.
