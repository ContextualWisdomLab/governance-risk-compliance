# ADR 0001: Product and authority boundary

- Status: Draft
- Date: 2026-08-18

## Context

ContextualWisdomLab already has specialist homes. Folding governance, risk, and
compliance into a composition hub would move GRC truth away from the service
that must answer for policy, control, risk, evidence, and compliance-audit
records. Requiring sibling checkouts would also make this leaf unable to run
alone.

The customer README already states that other CWL services consume
control/evidence contracts and do not take GRC truth with them.

## Decision

This repository is the GRC leaf. It owns policy, control, risk, evidence, and
compliance-audit truth.

Sibling homes keep their own truth:

| Home | Owns |
| --- | --- |
| [Orgmetra](https://github.com/ContextualWisdomLab/Orgmetra) | Employment truth |
| [Keyverse](https://github.com/ContextualWisdomLab/keyverse) | Identity truth |
| [Accounting Information Platform](https://github.com/ContextualWisdomLab/accounting-information-platform) (AIS) | Books |
| [Metering Billing Platform](https://github.com/ContextualWisdomLab/metering-billing-platform) | Commercial billing |

[naruon](https://github.com/ContextualWisdomLab/naruon) and
[gyeot](https://github.com/ContextualWisdomLab/gyeot) remain allowed composition
hubs. They may call this leaf. They do not absorb it. GRC is not folded into a
hub.

The leaf follows 따로 또 같이: it runs independently and it is callable. A
deployment or documentation path must not require a sibling checkout. Hub
repository links stay as call relationships, not as clone requirements.

Other CWL services may consume control and evidence contracts. They do not own
those records.

## Consequences

- Officers look here for GRC truth, not in naruon, gyeot, Orgmetra, Keyverse,
  AIS, or Billing.
- Hub composition stays valid as long as the hub calls this leaf.
- Later implementation slices must expose a contract this leaf can serve
  without reading another product's application tables.
- This draft does not create that contract, runtime, or package.

## References

ContextualWisdomLab. (2026). *Governance, Risk & Compliance* [Customer
README]. https://github.com/ContextualWisdomLab/governance-risk-compliance

ContextualWisdomLab. (2026). *Orgmetra* [Product README: employment truth].
https://github.com/ContextualWisdomLab/Orgmetra

ContextualWisdomLab. (2026). *cwl-idp — ecosystem central IdP* [Product README:
identity provider]. https://github.com/ContextualWisdomLab/keyverse
