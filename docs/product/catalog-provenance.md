# Catalog provenance first slice

Issue #29 starts with provenance because catalog truth must be reproducible before it is imported into the official control catalog.

## Implemented

The loopback-only API accepts `X-Purpose: catalog_governance` and records:

- an exact HTTPS source pointer against a reviewed server-owned host allowlist and source-license policy; request fields cannot expand the allowlist;
- an edition, publication/effective/withdrawal dates, lowercase SHA-256 digest, media type, and bounded byte length;
- an idempotent parser run and deterministic receipt digest with requirement/change/warning counts;
- a release only when a successful import receipt exists.

Historical provenance rows are append-only through database triggers. The service does not retain raw source bytes, follow remote redirects, or treat actor/purpose headers as authentication.

## Deliberate boundary

This is not yet a catalog importer. It does not fetch a NIST/KISA source, parse OSCAL or OLIR, copy source text, create `control_item` rows, map requirements, publish a `control_framework`, or calculate release impact. The next slice needs reviewable byte-level acquisition, parser fixtures, official identifier validation, mapping evidence, and independent approval before framework publication.

The official model and mapping references are recorded in `docs/doctoring/REFERENCES.md`.
