# Hourly review-repair caller

## Decision

GRC owns one small scheduled caller and remains independently runnable. The
central `ContextualWisdomLab/.github` reusable workflow owns queue inspection,
OpenCode/NVIDIA NIM model execution, dispatch authorization, exact-head checks,
and the fail-closed write boundary. GRC does not copy the scheduler or any
provider credential.

The caller runs at minute 53 of every UTC hour and can also be started with
`workflow_dispatch`. It scans the `develop`-based GRC pull-request queue, sends
at most one bounded repair dispatch, and waits two hours before retrying the
same pull-request head. It never approves or merges a pull request.

## Immutable central contract

The caller pins the central workflow source to:

```text
ContextualWisdomLab/.github/.github/workflows/pr-review-fix-scheduler.yml
@55a8b576725451dfe0a21a57d36a2f1a41619b24
```

When the central workflow changes, update this pin only after reviewing and
testing the new central exact head. The organization variable
`OPENCODE_REPOSITORY_DISPATCH_TARGETS` must contain the exact target
`ContextualWisdomLab/governance-risk-compliance`; otherwise the central workflow
must fail closed and record that the target is not allowlisted.

## Credential and trust boundary

- The caller grants read-only repository contents and OIDC token exchange only
  to the called central workflow.
- The caller does not grant contents or pull-request write permission.
- `COPILOT_GITHUB_TOKEN` is not used.
- The central workflow keeps review-agent credentials separate from its bounded
  repair path and must re-read the live pull-request head before any repair push.
- A repair push is not independent approval, a successful check, a merge, or a
  release decision.

## Operator next action

Open **Actions → Hourly GRC Review Repair** to inspect the latest run. If the
central worker publishes a same-repository repair, re-fetch the exact head,
review the changed files, rerun local and hosted checks, and obtain the required
independent approvals before any protected merge.

The local GRC preview and importable `cwl_grc` package work without this caller;
the workflow is an operational integration, not a production identity boundary.
