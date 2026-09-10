# Retire completed source-subset execution helpers without rewriting evidence

Status: **Proposed**. GRC PR 18, program issue 69.
Parent: `8deede6988480a357532c28b13381705e107993a`.
Preservation/retirement decision recorded before publication in comment 5611262898.

## Problem, evidence and scope

Three checked-in Python helpers existed to run selected source definitions in
an incomplete local checkout. Two execute a selected AST with `exec`; the
capture helper assumes a particular local directory and hardcodes the observed
absence of psycopg. These were historical observation tools, not production
APIs or the repository's Product/PostgreSQL test entrypoints.

Scanner review 5161669059 identified the dynamic execution and SHA-1 call.
CodeRabbit review 5161670162 additionally identified the capture tool's fixed
environment field and nested output directory. A future user running the tool
as a generic verifier could record incorrect environment metadata or replace a
historical receipt. Those are maintainability and evidence-integrity problems,
not evidence that the application executed an attacker-controlled request.

The SHA-1 call calculated a Git blob identifier; the receipt separately stores
SHA-256. It was not a digital signature. Replacing that field with SHA-256 while
still labeling it a Git object ID would falsify its meaning.

The original purpose is now complete: on this exact parent, Product run
34423287766/job102703117356 performed the full locked checkout and tests;
PostgreSQL run34423287712/job102703117533 actually ran all three native suites.
The inspected raw Product summary is130passed/23skipped/1warning, production
983statements/244branches100%. The separate PostgreSQL lane executed23passing
cases on its pinned18.4 service. These are parent results, not a later commit's
checks. They establish the normal test path exists; they are not approvals or
proof of complete privacy compliance.

## Decision

Remove the three completed executables from the current tree, without replacing
their dynamic evaluation through another API, renaming files, changing scanner
scope or adding a suppression. Normal verification uses the real GRC package,
the checked-in tests and the existing locked Product/PostgreSQL lanes.

Keep all historical receipts, raw logs and endpoint source delta byte-for-byte.
Their `files` fields describe the original observation workspace, not files to
execute from the newest checkout. Resolve removed tool references through the
immutable parent below. New observations require a new output location and
receipt; never rerun a capture tool over a historical canonical receipt.

| Historical path under `docs/evidence/` | Git blob in immutable parent |
| --- | --- |
| `postgresql_endpoint_policy/capture_endpoint_verification.py` | `dfc5524712780c6434a5fe099e45876bbbf98f28` |
| `postgresql_endpoint_policy/run_endpoint_tests.py` | `2f1b4f85ef4f2ce23e58f7c5186cc779dc456fe7` |
| `schema_base_reconciliation/run_contract_check.py` | `af1b9b96a2e32d983b6d75dfc75f427ba76e0bef` |

The first two identities are also recorded in the original endpoint receipt.
The third is the blob returned for that exact historical path and parent.
For forensic source inspection use `git show 8deede6988480a357532c28b13381705e107993a:<path>`
in an authorized clone. Historical availability is not an instruction to execute
arbitrary source. The [endpoint reproduction notes](../../evidence/postgresql_endpoint_policy/reproduction_notes.md)
now describe normal full-checkout reproduction rather than an active AST runner.

## Alternatives rejected

Keeping and generalizing all three local helpers adds an unnecessary second
execution path when the actual package and native database already run in CI.
Changing only the capture output to overwrite the current directory, as
suggested by the review, risks replacing immutable observation evidence.
Changing its fixed environment flag would make the tool more reusable, but
would not remove the redundant execution surface or its lifecycle ambiguity.

Rule suppressions and hidden dynamic evaluation are rejected. Deleting the
receipt/logs to make the review disappear is also rejected: only the purpose-
complete executables leave the current tree; their exact source and original
claims remain independently inspectable at the parent revision.

## Verification and unfinished work

Before publication, verify the retired paths and their old identities, all
retained artifact identities, the normal workflow commands and the effective
diff. Full exact-head SAST, CodeQL, Product, PostgreSQL and independent review
remain required; removing the flagged source does not manufacture a passed scan.

The accompanying CLI repair preserves argparse's zero help exit. It changes one
return expression and adds17parser-only cases. The original source produces
11failures/6passes; the repaired source produces17passes. The local evidence
receipt explicitly labels selected definitions and does not claim a complete
package import or deployed execution.

The separate major review findings concerning schema-ahead recovery guidance
and implicit operational SQLite/development defaults remain open. Removing
observation tools does not fix them. The previously blocked database diagnostic
candidate remains excluded. No runtime logging, database data, key policy,
remote access, branch protection or legal applicability changes here.
