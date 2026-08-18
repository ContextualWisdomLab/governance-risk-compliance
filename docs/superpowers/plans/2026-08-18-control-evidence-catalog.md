# Control catalog and evidence binding implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A compliance officer can list official controls, see coverage gaps, and bind evidence.

**Architecture:** Installable `cwl_grc` FastAPI kernel with 3NF SQLite-ready tables, Fernet evidence encryption, and `/healthz`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, pytest, ruff, interrogate.

## Global Constraints

- Real catalog identifiers only.
- Two-or-more-word snake_case database objects, 3NF.
- PII stays usable.
- Product CI only; no org Security/OpenCode/Noema lanes.
- Draft PR against `develop`.
