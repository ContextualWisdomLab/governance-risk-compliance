# Control catalog and evidence binding implementation plan

> Historical first-slice plan. The internal-control implementation plan and
> acceptance contract are in `docs/product/internal-control-model.md` and ADR
> 0011.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A compliance officer can author a versioned policy, see explicit control statuses, and establish a reviewed control test using purpose-approved evidence.

**Architecture:** Installable `cwl_grc` FastAPI kernel with 3NF SQLite-ready tables, Fernet evidence encryption, and `/healthz`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, pytest, ruff, interrogate.

## Global Constraints

- Real catalog identifiers only.
- Two-or-more-word snake_case database objects, 3NF.
- PII stays usable.
- Product CI only; no org Security/OpenCode/Noema lanes.
- Draft PR against `develop`.
