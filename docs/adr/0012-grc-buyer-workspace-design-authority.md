# ADR 0012: GRC buyer-workspace design authority

- Status: Proposed
- Date: 2026-08-21
- Issue: #30
- Figma file: `ta1jjWSjmADz2BFxka9UPs`
- Desktop frame: `1:72`
- Mobile frame: `1:150`
- Reusable-components section: `1:2`
- Interaction-state section: `1:227`

## Context

The protected product currently exposes a local officer preview but has no shared design authority for the enterprise buyer journey. Issue #30 requires Figma, design tokens, Storybook, WCAG 2.2 AA interaction evidence, responsive states, and exact-value alternatives before a reusable frontend system becomes product authority.

The first bounded slice is intentionally a design/runtime fixture. It must make uncertainty visible instead of presenting false zeroes, make every explanatory state lead to a next action, and preserve the GRC domain boundary: authoritative obligation, control, test, evidence, risk, audit, and authorization records remain in their owning APIs and database models. The workspace is a projection.

## Decision

Use the Figma design file `ta1jjWSjmADz2BFxka9UPs` and repository Storybook as paired design authority for this slice.

The shared semantic tokens are defined in `apps/grc-workspace/styles.css`. Repeated states use explicit text plus color: `effective`, `unknown`, `not assessed`, `stale`, `blocked`, and `access denied`. Repeated actions use persistent controls for requesting evidence, opening the evidence room, and revealing exact values. No buyer-critical action depends on hover, drag, animation, or a chart alone.

Storybook 10.5.10 uses the official Web Components + Vite framework and `@storybook/addon-a11y`. The checked-in npm lockfile and `mise.toml` pin the frontend toolchain; the exact-head workflow also runs a real Chromium interaction check. The initial inventory is:

- `ComplianceOfficerDesktop`
- `ComplianceOfficerMobile`
- `AccessDenied`
- `StaleEvidence`

The accessibility target is WCAG 2.2 AA for supported journeys. The fixture therefore requires keyboard operation, visible focus, text-equivalent status, a minimum 44 px action height, reduced-motion handling, forced-colors resilience, responsive stacking, print behavior, and an exact-value table for projected summary values. The 44 px target is an intentional product-system margin above WCAG 2.2 AA Success Criterion 2.5.8's 24 CSS pixel minimum.

On 2026-08-21, metadata and rendered screenshots of frames `1:72` and `1:150` found a collapsed desktop header/main-content layout and mobile overflow in the freshness alert and requirement trace. The existing Figma nodes were repaired in place: the desktop header and content now fill the intended frame width, desktop content keeps its 2:1 split, while mobile text wraps, trace rows stack, and actions remain inside the 358 px content column. This is design-authority evidence only; the repository Storybook and Chromium checks remain the executable implementation evidence.

The local preview now uses a dependency-free message-key catalog with English and Korean as the first verified locales, including a browser-tested locale selector and Storybook Korean story. Status identifiers remain stable machine values; localized labels must not change authorization, evidence, or export semantics. Connected work must carry the same key-based contract into authenticated APIs and exports.

## Ownership boundary

This repository owns GRC-specific view composition and GRC workflow presentation. It does not copy Keyverse identity/authorization, another product's system of record, or central privileged CI/review credentials. Dashboards and cards are projections and cannot become a second source of truth.

The Figma and Storybook artifacts in this ADR are design evidence, not authentication evidence, API-contract evidence, accessibility certification, or deployment evidence. A connected workspace remains dependent on #4, #9, #12, #27, #28, #13, and #14 as applicable.

## Consequences

A reviewer can compare the desktop/mobile Figma frames with executable Storybook states and the static fixture from one traceable token/state vocabulary. Buyer-facing gaps can be repaired without inventing product truth. The trade-off is an additional frontend dev dependency surface; the checked-in lockfile, exact-head Storybook build, and Chromium interaction check remain design evidence rather than release evidence.

## References

Storybook. (2026). *Storybook for Web components with Vite*. https://storybook.js.org/docs/get-started/frameworks/web-components-vite

Storybook. (2026). *Accessibility tests*. https://storybook.js.org/docs/writing-tests/accessibility-testing

World Wide Web Consortium. (2023). *Web Content Accessibility Guidelines (WCAG) 2.2*. https://www.w3.org/TR/WCAG22/
