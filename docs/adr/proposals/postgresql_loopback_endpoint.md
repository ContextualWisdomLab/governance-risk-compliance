# Bind the plaintext PostgreSQL test exception to the actual loopback address

Status: **Proposed**. Owner: GRC schema lifecycle, PR 18; privacy program 69.
Source parent: `56f2399ea2fa97f78afcf4da73aaa67f196a58a9`.
Original database blob: `9ec92990ee67ee028ffccd7b32dbe798868a42fe`.
No numeric ADR is reserved across the unmerged owner stacks.

## Problem and operational scenario

The existing default requires `sslmode=verify-full`. A separately enabled test
exception permits `sslmode=disable` only when the URL authority is loopback.
That check inspected `url.host`, not the endpoint ultimately passed to psycopg.

For example, an isolated test configuration can retain `127.0.0.1` in its URL
while a query `host` selects another address. The actual SQLAlchemy psycopg
dialect replaces the first host with the query host, including multi-host
forms. libpq also distinguishes a host name from `hostaddr`, the numeric network
address, and can fill unset parameters from environment/service defaults.
A loopback name check therefore does not establish a loopback destination.

The reproduced defect is in configuration validation, not an unauthenticated
HTTP route and not an established customer incident. No remote database,
credentials or customer data were used. Reserved documentation addresses and
synthetic unit values suffice to demonstrate the final argument substitution.

## Decision and invariant

Keep the verified-TLS production profile and the explicit opt-in requirement.
Within the plaintext test exception only:

- Reject query `host`, `hostaddr`, `port` and `service` before calling the engine
  builder, even if the second selector happens to name another loopback value.
  A second selector must not silently replace the reviewed URL authority.
- Pass the already validated host explicitly in `connect_args` and also pass
  its numeric loopback address as `hostaddr`. These explicit fields do not rely
  on environment defaults or host-name resolution to choose the network address.
- Interpret `localhost`, case-insensitively, as IPv4 `127.0.0.1` for this exception.
  IPv6 tests use the explicit `[::1]` URL authority. IP-literal loopback inputs
  retain their address; a nondefault authority port remains unchanged.

The boundary is implemented in the existing `_build_postgresql_engine`, not a
second database service. Its error message does not echo the rejected URL.
Existing TLS mismatch/ambiguity checks, pooling, wait limits, transaction
isolation, migration ownership, schema compatibility and stored values remain.
No production environment variable is read, deleted or rewritten by the repair.

This is an address-scope invariant, not an authentication system or a port
allowlist. When the URL omits a port, existing libpq port-default behavior is
unchanged. Configuration/plugins, the operating system, local forwarders and
services already controlling loopback are outside this narrow trust boundary.

## Alternatives and tradeoffs

Checking only `url.host` is rejected because the observed driver arguments can
select a different host. Checking only query `host` is insufficient because
`hostaddr` can choose the network address independently. Clearing PG environment
variables globally is rejected because an imported library must not mutate
other consumers' process configuration. Resolving localhost on every request
is unnecessary and does not bind the final native connection address.

Deleting the opt-in test profile would disrupt the existing isolated real
PostgreSQL acceptance service; it is not necessary to correct this defect.
Allowing alternate selectors and silently overriding them would conceal a
configuration mistake. The selected fail-closed behavior instead asks the test
operator to use one literal URL authority and its optional port.

A global ban on production multi-host/service options is rejected: this repair
is not an approved production topology redesign. Those options retain their
existing verified-TLS contract and require their separate configuration review.

The localhost IPv4 choice is deliberate compatibility tightening. An IPv6-only
local test database must use `[::1]`; the repair does not fall back silently to
a different address family. See the operator notes below and the unit cases.

## Verification and remaining gates

`tests/test_postgresql_endpoint_policy.py` contains 27 no-network unit cases.
It executes actual GRC engine-policy functions and the real SQLAlchemy psycopg
dialect conversion. Only engine creation is captured, so no DBAPI, pool or
socket is created. The local harness extracts the unchanged definitions from
the full hash-verified source to avoid importing an incomplete source checkout;
normal Product execution imports the real GRC package directly.

The same tests on the original source produce **17 failed / 10 passed**. On the
repaired source, **27 pass**. They cover query/multi-host/encoded-key selectors,
loopback IPv4/IPv6/localhost, nondefault URL port, explicit opt-in, nonlocal or
missing authority, contradictory TLS options, retained production options and
explicit host arguments with PG environment defaults present. Those last cases
inspect supplied arguments; they do not simulate native libpq service loading.

Actual execution instants, environment, commands, exit codes, source/test Git
OIDs and SHA-256 and raw outputs are retained in
`docs/evidence/postgresql_endpoint_policy/verification_receipt.json`.
Local Python 3.13.5 / SQLAlchemy 2.0.50 / pytest 9.0.2 are not the locked Product
environment; psycopg is not installed there. Compilation and Python 3.12 grammar
acceptance do not claim a Python 3.12 runtime run or whole-product coverage.

Before protected merge: full locked Product and 100% production coverage,
actual PostgreSQL acceptance using the existing owner lane, security, current
independent review and all live branch requirements. Before adoption: immutable
release and deployed control verification. Source publication is not release,
deployment or legal compliance. Program 69 remains open.

## Existing runtime and ownership

This is a causal repair to an existing Python database adapter, not approval of
a new Python security core. A future Rust-owned adapter must preserve this
contract and normal schema/connection behavior, pass actual database and
rollback acceptance, and be released before the legacy implementation is removed.
No cross-service source/SQL access or copy of Keyverse, EgressWeave or central CI
is introduced. The earlier blocked database diagnostic/logging candidate remains
excluded; this change neither applies it nor claims to protect diagnostic output.

## Operator notes

Use a single literal loopback authority with the explicit test settings. Keep
an explicit URL port for isolated services. Remove conflicting query selectors
from the test configuration rather than weakening the check. Use `[::1]` for
IPv6-only services; `localhost` in this exception is now explicitly IPv4. Do not
apply the plaintext profile to production, a remote service or a local tunnel
that forwards to a remote database. Normal production retains verify-full.

## Primary implementation references (APA 7)

SQLAlchemy. (n.d.). *PostgreSQL: Unix domain connections; specifying multiple
fallback hosts*. SQLAlchemy 2.0 documentation. Retrieved September 10, 2026, from
https://docs.sqlalchemy.org/en/20/dialects/postgresql.html

SQLAlchemy. (n.d.). *Engine configuration*. SQLAlchemy 2.0 documentation.
Retrieved September 10, 2026, from
https://docs.sqlalchemy.org/en/20/core/engines.html

PostgreSQL Global Development Group. (n.d.). *32.1. Database connection control
functions*. PostgreSQL 18 documentation. Retrieved September 10, 2026, from
https://www.postgresql.org/docs/18/libpq-connect.html

These primary references explain URL conversion, explicit driver arguments,
`hostaddr` and unset-parameter defaults. The SQLAlchemy examples include psycopg2;
the local regression independently executes the actual psycopg dialect used by
GRC rather than assuming equivalence. Full HTTP response archives were not
retained here. These references are not legal-source applicability evidence,
a native network test or certification of a deployed configuration.
