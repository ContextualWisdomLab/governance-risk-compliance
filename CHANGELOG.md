# CHANGELOG.md

## Unreleased

### Added

- First buyer slice: official CSAP / SOC 2 / ISMS-P / ISO/IEC 27001:2022 / NIST SP 800-53 Rev. 5 / COSO 2013 / COSO 2017 control seeds.
- Evidence create and control–evidence binding under purpose-limited authorization.
- Uncovered-control query and officer home that states the next action.
- `/healthz` probe, standalone `python -m cwl_grc` entry, and `create_app()` module factory.
- Product CI for lint, docstring coverage, and 100% test coverage.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query as the first GRC product surface.
