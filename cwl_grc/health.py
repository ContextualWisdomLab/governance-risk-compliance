"""Truthful liveness, startup, readiness, and drain contracts for GRC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from cwl_grc.authorization import PurposeCode
from cwl_grc.encryption import EvidenceCipher, make_evidence_context
from cwl_grc.migrations import (
    EVIDENCE_ENCRYPTION_MIGRATION,
    EVIDENCE_RETENTION_MIGRATION,
    POLICY_INTEGRITY_MIGRATION,
    TENANT_ISOLATION_MIGRATION,
)
from cwl_grc.models import Base


SERVICE_NAME = "cwl-grc"
LOCAL_PREVIEW_ENVIRONMENT = "local_preview"
PRODUCTION_ENVIRONMENT = "production"
REQUIRED_MIGRATIONS = frozenset(
    {
        POLICY_INTEGRITY_MIGRATION,
        TENANT_ISOLATION_MIGRATION,
        EVIDENCE_ENCRYPTION_MIGRATION,
        EVIDENCE_RETENTION_MIGRATION,
    }
)
REQUIRED_TABLES = frozenset(Base.metadata.tables) | {"schema_migration"}
SQLITE_GUARDS = frozenset(
    {
        "audit_event_block_update",
        "audit_event_block_delete",
        "policy_version_require_tenant_document",
        "policy_version_require_open_insert",
        "policy_version_block_delete",
        "policy_version_finalize_only",
        "policy_control_mapping_block_update",
        "policy_control_mapping_block_delete",
        "policy_control_mapping_require_open_version",
        "control_binding_require_tenant_evidence_insert",
        "control_binding_require_tenant_evidence_update",
    }
)
POSTGRESQL_GUARDS = frozenset(
    {
        "audit_event_immutable",
        "policy_version_immutable",
        "policy_control_mapping_immutable",
        "control_binding_tenant_parent",
    }
)


@dataclass
class LifecycleState:
    """Track whether this process accepts traffic or is draining."""

    state: str = "starting"

    @property
    def is_draining(self) -> bool:
        """Return whether new mutating work must be rejected."""
        return self.state == "draining"

    def mark_ready(self) -> None:
        """Advertise readiness after all startup checks have passed."""
        if not self.is_draining:
            self.state = "ready"

    def begin_drain(self) -> None:
        """Stop advertising readiness before graceful process shutdown."""
        self.state = "draining"


def health_payload() -> dict[str, Any]:
    """Return the dependency-free /healthz body used by orchestrators."""
    return {"status": "ok", "service": SERVICE_NAME}


def readiness_payload(
    factory: sessionmaker[Session],
    cipher: EvidenceCipher,
    environment: str,
    access_token_verifier: object | None,
    lifecycle: LifecycleState | None = None,
) -> dict[str, Any]:
    """Check bounded local dependencies without returning secrets or database details."""
    checks = _database_checks(factory)
    checks["evidence_key"] = _evidence_key_check(cipher)
    checks["identity_configuration"] = _identity_check(
        environment,
        access_token_verifier,
    )
    if lifecycle is not None:
        checks["lifecycle"] = _lifecycle_check(lifecycle)
    ready = all(check["status"] == "ok" for check in checks.values())
    return {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE_NAME,
        "environment": environment,
        "checks": checks,
    }


def ensure_startup_ready(
    factory: sessionmaker[Session],
    cipher: EvidenceCipher,
    environment: str,
    access_token_verifier: object | None,
) -> dict[str, Any]:
    """Fail closed before traffic is admitted when startup contracts are not true."""
    report = readiness_payload(
        factory,
        cipher,
        environment,
        access_token_verifier,
    )
    if report["status"] != "ready":
        reasons = [
            check["reason_code"]
            for check in report["checks"].values()
            if check["status"] != "ok"
        ]
        raise RuntimeError(f"GRC startup checks failed: {','.join(reasons)}")
    return report


def _database_checks(factory: sessionmaker[Session]) -> dict[str, dict[str, str]]:
    """Check connectivity, schema receipts, seed rows, and database guards."""
    try:
        with factory() as session:
            session.execute(text("SELECT 1"))
            inspector = inspect(session.bind)
            missing_tables = REQUIRED_TABLES - set(inspector.get_table_names())
            if missing_tables:
                return {
                    "database": _fail("schema_unavailable"),
                    "schema": _fail("schema_incompatible"),
                    "seed_state": _fail("schema_incompatible"),
                    "integrity_guards": _fail("schema_incompatible"),
                }
            receipts = set(
                session.execute(text("SELECT migration_key FROM schema_migration")).scalars()
            )
            if not REQUIRED_MIGRATIONS <= receipts:
                return {
                    "database": _ok("database_reachable"),
                    "schema": _fail("schema_migration_incomplete"),
                    "seed_state": _fail("schema_migration_incomplete"),
                    "integrity_guards": _fail("schema_migration_incomplete"),
                }
            control_count = session.execute(text("SELECT COUNT(*) FROM control_item")).scalar_one()
            purpose_count = session.execute(
                text("SELECT COUNT(*) FROM authorization_purpose")
            ).scalar_one()
            if control_count < 1 or purpose_count < len(PurposeCode):
                return {
                    "database": _ok("database_reachable"),
                    "schema": _ok("schema_compatible"),
                    "seed_state": _fail("seed_state_incomplete"),
                    "integrity_guards": _fail("seed_state_incomplete"),
                }
            guard_names = _guard_names(session)
            required_guards = (
                SQLITE_GUARDS
                if session.bind.dialect.name == "sqlite"
                else POSTGRESQL_GUARDS
            )
            if not required_guards <= guard_names:
                return {
                    "database": _ok("database_reachable"),
                    "schema": _ok("schema_compatible"),
                    "seed_state": _ok("seed_state_ready"),
                    "integrity_guards": _fail("integrity_guards_incomplete"),
                }
    except Exception:
        return {
            "database": _fail("database_unreachable"),
            "schema": _fail("database_unreachable"),
            "seed_state": _fail("database_unreachable"),
            "integrity_guards": _fail("database_unreachable"),
        }
    return {
        "database": _ok("database_reachable"),
        "schema": _ok("schema_compatible"),
        "seed_state": _ok("seed_state_ready"),
        "integrity_guards": _ok("integrity_guards_ready"),
    }


def _guard_names(session: Session) -> set[str]:
    """Return non-internal database trigger names for the active dialect."""
    if session.bind.dialect.name == "sqlite":
        return set(
            session.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            ).scalars()
        )
    return set(
        session.execute(
            text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
        ).scalars()
    )


def _evidence_key_check(cipher: EvidenceCipher) -> dict[str, str]:
    """Prove the configured evidence key can perform a private round trip."""
    try:
        context = make_evidence_context("readiness_probe", "readiness_probe")
        encrypted = cipher.encrypt_record("readiness-probe", context=context)
        if cipher.decrypt_record(encrypted, context=context) != "readiness-probe":
            return _fail("evidence_key_round_trip_failed")
    except Exception:
        return _fail("evidence_key_unavailable")
    return _ok("evidence_key_ready")


def _identity_check(
    environment: str,
    access_token_verifier: object | None,
) -> dict[str, str]:
    """Distinguish safe local preview from a forbidden unverified production mode."""
    if environment == LOCAL_PREVIEW_ENVIRONMENT and access_token_verifier is None:
        return _ok("local_preview_identity_disabled")
    if environment == LOCAL_PREVIEW_ENVIRONMENT:
        return _ok("keyverse_configuration_ready")
    if environment == PRODUCTION_ENVIRONMENT and access_token_verifier is None:
        return _fail("keyverse_configuration_required")
    if environment == PRODUCTION_ENVIRONMENT:
        return _fail("remote_access_boundary_disabled")
    return _fail("unsupported_environment")


def _lifecycle_check(lifecycle: LifecycleState) -> dict[str, str]:
    """Return the current drain/readiness state using stable reason codes."""
    if lifecycle.is_draining:
        return _fail("draining")
    if lifecycle.state != "ready":
        return _fail("startup_incomplete")
    return _ok("lifecycle_ready")


def _ok(reason_code: str) -> dict[str, str]:
    """Build a successful probe check."""
    return {"status": "ok", "reason_code": reason_code}


def _fail(reason_code: str) -> dict[str, str]:
    """Build a failed probe check without exposing exception details."""
    return {"status": "fail", "reason_code": reason_code}
