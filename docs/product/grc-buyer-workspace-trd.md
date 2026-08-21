# GRC buyer workspace — bounded TRD

## Authority and scope

- Issue: #30
- Figma: `ta1jjWSjmADz2BFxka9UPs`
- ADR: 0012

The first slice is a static, dependency-light UI fixture paired with Storybook. It proves state semantics, component reuse, responsive behavior, print preservation, and exact-value alternatives. It is **not production evidence** for authentication, authorization, API integration, exports, or deployment.

## Runtime boundary

`apps/grc-workspace/index.html` and `styles.css` own only presentation. They contain no credentials, tenant identifiers from a caller, persistence, API mutation logic, or duplicated GRC truth. Connected work must derive tenant, actor, role, and purpose from the verified Keyverse principal and consume reviewed GRC contracts rather than fixture text.

The workspace is a projection. Obligation/applicability truth is owned by #28, internal-control/effectiveness truth by #27, evidence retention/disclosure by #9, stable API behavior by #12, and risk/audit workflows by #13/#14.

## Design runtime

Storybook is pinned at 10.5.10 with `@storybook/web-components-vite` and `@storybook/addon-a11y`; `package-lock.json` and `mise.toml` pin the transitive npm graph and Node 24.18.0. Stories import the real `index.html` main element as raw markup and only select fixture state visibility, preventing Storybook from becoming a second markup authority. The exact-head workflow builds Storybook and runs a Chromium interaction check. These remain design evidence rather than release evidence.

Supported design states in this slice:

- compliance officer desktop;
- compliance officer mobile;
- stale evidence;
- access denied;
- unknown applicability;
- not-assessed control test;
- blocked deficiency;
- exact-value table;
- reduced motion;
- forced colors;
- print/PDF-oriented rendering.

## Verification

`tests/test_buyer_workspace_design_contract.py` is intentionally added before the implementation artifacts. It requires the Figma source, Storybook inventory, semantic states, next actions, exact-value table, focus visibility, 44 px action target, reduced-motion handling, responsive layout, print contract, lockfile, and browser gate. `tests/buyer-workspace.spec.mjs` verifies keyboard action edges, mobile overflow containment, action sizing, print behavior, and the truthful preview boundary.

The repository Product workflow should continue to run the Python regression suite at 100% owned production statement/branch coverage. A dedicated Storybook build lane must run on the exact PR head before the design runtime is considered merge-ready.

## Security and privacy

The fixture contains synthetic organization and evidence labels only. It must not ingest real PII or imply authorization. `access denied` is represented as a first-class state with a request-access next action rather than revealing hidden fields. Exact-value alternatives preserve authorized values; later connected work must enforce purpose-specific field selection at the API/export boundary.
