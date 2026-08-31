"""Operator CLI: schema ownership, policies, gaps, and evidence binding."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import uvicorn
from fastapi import HTTPException
from sqlalchemy.orm import Session

from cwl_grc.app import SCHEMA_MODES, create_app, parse_framework, serialize_control
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.database import (
    SchemaCompatibilityError,
    assert_schema_compatible,
    build_engine,
    create_session_factory,
    migrate_database,
)
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.policy import (
    author_policy,
    list_policy_documents,
    list_policy_gaps,
    parse_cli_control_map,
    revise_policy,
    serialize_gap,
    serialize_policy,
)


def main(argv: list[str] | None = None) -> int:
    """Dispatch ``cwl-grc`` tool commands; no arguments still serves HTTP."""
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        if not args or args == ["serve"]:
            return serve_http()
        parser = _parser()
        try:
            namespace = parser.parse_args(args)
        except SystemExit as exc:
            return int(exc.code or 2)
        return _dispatch(namespace)
    except HTTPException as exc:
        print(
            json.dumps(
                {
                    "error": exc.detail,
                    "status_code": exc.status_code,
                    "next_action": (
                        "Use an official catalog identifier, then attach the next evidence."
                    ),
                }
            )
        )
        return 1
    except SchemaCompatibilityError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "next_action": (
                        "Run the explicit database migration owner, then check compatibility."
                    ),
                }
            )
        )
        return 1
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "next_action": "Correct the command input or runtime configuration, then retry.",
                }
            )
        )
        return 1


def serve_http() -> int:
    """Serve the loopback-only preview using the configured schema profile."""
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the operator command parser."""
    parser = argparse.ArgumentParser(
        prog="cwl-grc",
        description="CWL GRC officer and schema-owner tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    database = sub.add_parser("database", help="Migrate or check the product schema")
    database_sub = database.add_subparsers(dest="database_command", required=True)
    migrate = database_sub.add_parser(
        "migrate",
        help="Apply the exact supported schema as the single migration owner",
    )
    database_url = os.environ.get("CWL_GRC_DATABASE_URL")
    migrate.add_argument(
        "--database-url",
        default=database_url,
        required=database_url is None,
    )
    check = database_sub.add_parser(
        "check",
        help="Verify schema compatibility without changing the database",
    )
    check.add_argument(
        "--database-url",
        default=database_url,
        required=database_url is None,
    )

    policy = sub.add_parser("policy", help="Author, revise, or list policies")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    author = policy_sub.add_parser(
        "author",
        help="Author a policy mapped to official controls",
    )
    author.add_argument("--title", required=True)
    author.add_argument("--body", required=True)
    author.add_argument("--map", action="append", default=[], dest="maps")
    author.add_argument("--actor", required=True)
    revise = policy_sub.add_parser("revise", help="Publish the next policy edition")
    revise.add_argument("--policy-id", required=True)
    revise.add_argument("--body", required=True)
    revise.add_argument("--map", action="append", default=[], dest="maps")
    revise.add_argument("--actor", required=True)
    policy_sub.add_parser("list", help="List authored policies")
    gaps = sub.add_parser("gaps", help="List uncovered policy/control gaps")
    gaps.add_argument("--policy-id")
    bind = sub.add_parser("bind", help="Store and bind the next evidence artifact")
    bind.add_argument("--framework", required=True)
    bind.add_argument("--identifier", required=True)
    bind.add_argument("--title", required=True)
    bind.add_argument("--payload", required=True)
    bind.add_argument("--actor", required=True)
    return parser


def _dispatch(namespace: argparse.Namespace) -> int:
    """Run one parsed operator command against the product store."""
    command = namespace.command
    if command == "database":
        return _database_command(namespace)
    if command == "policy":
        return _policy_command(namespace)
    if command == "gaps":
        return _gaps_command(namespace.policy_id)
    if command == "bind":
        return _bind_command(namespace)
    return 2


def _database_command(namespace: argparse.Namespace) -> int:
    """Migrate or verify one exact product schema without serving traffic."""
    database_url = namespace.database_url
    if namespace.database_command == "migrate":
        receipts = migrate_database(database_url)
        print(
            json.dumps(
                {
                    "status": "schema_ready",
                    "migration_keys": list(receipts),
                    "next_action": "Start the runtime in schema mode runtime.",
                }
            )
        )
        return 0
    if namespace.database_command == "check":
        engine = build_engine(database_url)
        try:
            receipts = assert_schema_compatible(engine)
        finally:
            engine.dispose()
        print(
            json.dumps(
                {
                    "status": "schema_compatible",
                    "migration_keys": list(receipts),
                    "next_action": "Start or continue the runtime without running DDL.",
                }
            )
        )
        return 0
    return 2


def _policy_command(namespace: argparse.Namespace) -> int:
    """Author, revise, or list policies."""
    action = namespace.policy_command
    session = _open_session()
    try:
        if action == "author":
            decision = AuthorizationDecision(
                namespace.actor,
                PurposeCode.POLICY_AUTHORING,
            )
            refs = [parse_cli_control_map(raw) for raw in namespace.maps]
            document = author_policy(
                session,
                decision,
                namespace.title,
                namespace.body,
                refs,
            )
            session.commit()
            print(json.dumps(serialize_policy(session, document)))
            return 0
        if action == "revise":
            decision = AuthorizationDecision(
                namespace.actor,
                PurposeCode.POLICY_AUTHORING,
            )
            refs = [parse_cli_control_map(raw) for raw in namespace.maps]
            document = revise_policy(
                session,
                decision,
                namespace.policy_id,
                namespace.body,
                refs,
            )
            session.commit()
            print(json.dumps(serialize_policy(session, document)))
            return 0
        if action == "list":
            payload: dict[str, Any] = {
                "policies": [
                    serialize_policy(session, document)
                    for document in list_policy_documents(session)
                ],
                "next_action": "Review policy gaps and attach the next evidence.",
            }
            print(json.dumps(payload))
            return 0
        return 2
    finally:
        session.close()


def _gaps_command(policy_document_id: str | None) -> int:
    """Print uncovered policy/control gaps as JSON."""
    session = _open_session()
    try:
        gaps = list_policy_gaps(session, policy_document_id)
        print(
            json.dumps(
                {
                    "next_action": (
                        "Attach the next evidence on an uncovered policy control."
                    ),
                    "gaps": [serialize_gap(gap) for gap in gaps],
                }
            )
        )
        return 0
    finally:
        session.close()


def _bind_command(namespace: argparse.Namespace) -> int:
    """Store one evidence artifact and bind it to an official control."""
    session = _open_session()
    cipher = EvidenceCipher(os.environ.get("CWL_GRC_EVIDENCE_KEY"))
    try:
        decision = AuthorizationDecision(
            namespace.actor,
            PurposeCode.EVIDENCE_BINDING,
        )
        framework = parse_framework(namespace.framework)
        if framework is None:
            raise HTTPException(
                status_code=400,
                detail="Name the official framework.",
            )
        record = create_evidence_record(
            session,
            cipher,
            decision,
            namespace.title,
            namespace.payload,
        )
        binding = bind_control_evidence(
            session,
            decision,
            framework,
            namespace.identifier,
            record.evidence_record_id,
        )
        session.commit()
        print(
            json.dumps(
                {
                    "binding_id": binding.binding_id,
                    "control_item_id": binding.control_item_id,
                    "evidence_record_id": record.evidence_record_id,
                    "payload_text": cipher.decrypt(record.ciphertext_payload),
                    "control": serialize_control(binding.control_item),
                    "next_action": (
                        "Review remaining uncovered policy controls and attach the next "
                        "evidence."
                    ),
                }
            )
        )
        return 0
    finally:
        session.close()


def _open_session() -> Session:
    """Open one officer session under the configured schema-ownership profile."""
    url = os.environ.get(
        "CWL_GRC_DATABASE_URL",
        "sqlite:///grc_product.sqlite",
    )
    mode = os.environ.get("CWL_GRC_SCHEMA_MODE", "development")
    if mode not in SCHEMA_MODES:
        allowed = ", ".join(sorted(SCHEMA_MODES))
        raise ValueError(f"CWL GRC schema mode must be one of: {allowed}.")
    factory = create_session_factory(
        url,
        manage_schema=mode == "development",
    )
    return factory()
