# ADR 0013: Catalog provenance and import receipts

## Status

Accepted for the Issue #29 first vertical slice.

## Context

Official control catalogs change by publisher, edition, and parser. A catalog row without a source pointer, exact digest, parser identity, or import outcome cannot support an audit explanation or a safe re-import. The repository also must not claim that a remote page was fetched or that requirements were imported when no byte-level acquisition and parser evidence exists.

OSCAL provides machine-readable control and mapping models, and NIST's OLIR program provides a structured way to relate informative references to authoritative sources. Those formats inform the later importer; they are not a reason to duplicate source text or invent control identifiers in this slice.

## Decision

Add a global, tenant-neutral provenance chain:

`source_license_policy` → `source_artifact` → `source_artifact_version` → `catalog_import_run` + `catalog_import_receipt` → `catalog_release`

- Register only explicit HTTPS pointers whose host is in the reviewed server-owned exact allowlist. The HTTP caller cannot expand that list; the service does not follow redirects or fetch bytes.
- Require an externally computed lowercase SHA-256 digest, edition metadata, inert JSON/XML/YAML/plain media type, and bounded byte length. Raw source bytes are not stored.
- Make source versions, parser runs/receipts, and releases append-only at the SQLite and PostgreSQL database boundary.
- Make import identity idempotent by source version plus parser version; release publication requires a successful receipt.
- Persist the selected successful import-run identity on each release. Release snapshots resolve only that immutable link; legacy releases without a valid link fail closed rather than switching to a later re-import.
- Upgrade existing stores with the versioned `0003_catalog_release_receipt_link` migration, backfilling the latest successful receipt when one exists.
- Require the declared `catalog_governance` purpose. It is an audit-purpose declaration in the local preview, not authentication.
- Expose a bounded published-release list, a metadata-only release detail endpoint, and a comparison endpoint so officers can review source/version/receipt and explicit license/export policy changes without implying a requirement-level diff.
- Keep provenance separate from `control_framework` and `control_item`. A later importer may create or update an official framework edition only after verified source bytes, parser output, official identifiers, mapping evidence, and independent review exist.

## Consequences

The current API can explain which source edition and parser receipt produced a candidate release, page through published identities, and compare metadata fields between two releases without overstating acquisition or catalog completeness. It cannot yet retrieve a catalog, parse OSCAL/OLIR, bind imported requirements to a framework, or answer requirement-level impact/diff questions. Those remain explicit follow-on work.

## References

See `docs/doctoring/REFERENCES.md` for the APA 7 references to NIST OSCAL and OLIR materials.
