# Catalog provenance first slice

Issue #29 starts with provenance because catalog truth must be reproducible before it is imported into the official control catalog.

## Implemented

The loopback-only API accepts `X-Purpose: catalog_governance` and records:

- an exact HTTPS source pointer against a reviewed server-owned host allowlist and source-license policy; request fields cannot expand the allowlist;
- an explicit content classification mapped to its reviewed license policy, including identifier-only, lawful source text, licensed text, organization-authored summary, and translated summary;
- an edition, publication/effective/withdrawal dates, lowercase SHA-256 digest, media type, and bounded byte length;
- an idempotent parser run and deterministic receipt digest with requirement/change/warning counts;
- a release only when a successful import receipt exists, with the selected import-run identity stored on the release so later re-imports cannot rewrite its snapshot.
- a bounded governed release list and metadata-only comparison of two published releases, including changed and unchanged provenance/receipt fields and a clear requirement-diff limitation.

`GET /catalog/releases?limit=50&offset=0` returns deterministic pages with
`has_more` state and never returns more than 100 rows per request. A governed
`GET /catalog/releases/{id}` returns one metadata-only provenance snapshot.
The snapshot includes the registered content class and explicit source-text
storage/export and identifier-export policy flags, so an officer can confirm
the legal boundary before using or exporting a release.
Historical provenance rows are append-only through database triggers. The
release snapshot uses only its stored successful import identity and rejects
legacy releases without one. The
service does not retain raw source bytes, follow remote redirects, or treat
actor/purpose headers as authentication.

## Deliberate boundary

This is not yet a catalog importer. It does not fetch a NIST/KISA source, parse OSCAL or OLIR, copy source text, create `control_item` rows, map requirements, publish a `control_framework`, or calculate requirement-level release impact. The next slice needs reviewable byte-level acquisition, parser fixtures, official identifier validation, mapping evidence, and independent approval before framework publication.

The official model and mapping references are recorded in `docs/doctoring/REFERENCES.md`.
