# GRC buyer workspace — bounded PRD

## Authority

- Product issue: #30
- Figma: `ta1jjWSjmADz2BFxka9UPs`
- Design decision: ADR 0012

## Buyer outcome

A compliance officer can distinguish proven posture from incomplete posture, trace a claim through requirement → control → test → evidence, and identify the next safe action without treating a dashboard projection as authoritative truth.

## First-slice stories

1. As a compliance officer, I can see `unknown`, `not assessed`, `stale`, `blocked`, and `access denied` as distinct states so that missing evidence never appears as a healthy zero.
2. As a compliance officer, I can request missing evidence from the same trace that exposed the gap.
3. As an internal or external reviewer, I can reveal an exact-value table for every projected summary so that a badge or percentage is independently understandable.
4. As a keyboard or touch user, I can reach every action without hover, dragging, or pointer-only state.
5. As an operator preparing a report, I can print the exact-value table with period, source version, limitation, and next action intact.

## Acceptance evidence

The Figma desktop frame `1:72`, mobile frame `1:150`, reusable component section `1:2`, and interaction-state section `1:227` use the same semantic vocabulary as Storybook and `apps/grc-workspace/styles.css`. Storybook must expose desktop, mobile, stale-evidence, and access-denied stories with the a11y addon enabled.

Repository tests must fail if the explicit buyer states, next-action labels, exact-value table, focus-visible rule, reduced-motion rule, print rule, responsive rule, Storybook inventory, or Figma traceability are removed.

## Non-goals

This slice does not authenticate a tenant, authorize a purpose, fetch protected GRC records, create an evidence request, issue an export, grant a data-room package, certify WCAG conformance, or certify compliance. Those capabilities remain dependent on the domain and security issues linked from #30.
