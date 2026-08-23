"""Operator CLI: author policies, list gaps, and bind evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sqlalchemy.orm import Session

import uvicorn
from fastapi import HTTPException

from cwl_grc.app import create_app, parse_framework, serialize_control
from cwl_grc.keyverse_http import (
    EVIDENCE_WRITE_SCOPES,
    POLICY_READ_SCOPES,
    POLICY_WRITE_SCOPES,
    RequestPrincipal,
    authenticate_cli_principal,
    decision_for_request,
    process_access_token_verifier,
)
from cwl_grc.remote_access import (
    keyverse_start_is_required,
    loopback_server_bind,
    startup_next_action,
)
from cwl_grc.authorization import (
    AuthorizationDecision,
    PurposeCode,
    seed_authorization_purposes,
)
from cwl_grc.models import PolicyDocument
from cwl_grc.catalog import seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.policy import (
    PolicyGap,
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
    if not args or args == ["serve"]:
        return serve_http()
    parser = _parser()
    try:
        namespace = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code or 2)
    try:
        return _dispatch(namespace)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "next_action": startup_next_action(),
                }
            )
        )
        return 2
    except HTTPException as exc:
        print(
            json.dumps(
                {
                    "error": exc.detail,
                    "status_code": exc.status_code,
                    "next_action": _cli_http_next_action(exc),
                }
            )
        )
        return 1


def serve_http() -> int:
    """Serve the local preview on loopback, requiring TLS when Keyverse is required."""
    try:
        settings = loopback_server_bind()
        app = create_app(access_token_verifier=process_access_token_verifier())
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "next_action": startup_next_action(),
                }
            )
        )
        return 2
    uvicorn.run(app, **settings)
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the operator command parser."""
    parser = argparse.ArgumentParser(
        prog="cwl-grc",
        description="CWL GRC officer tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
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
    if command == "policy":
        return _policy_command(namespace)
    if command == "gaps":
        return _gaps_command(namespace.policy_id)
    if command == "bind":
        return _bind_command(namespace)
    return 2


def _cli_http_next_action(exc: HTTPException) -> str:
    """Return the officer next action for one CLI authorization or catalog error."""
    try:
        required = keyverse_start_is_required()
    except ValueError:
        required = True
    if exc.status_code in {401, 403} and required:
        return (
            "Set CWL_GRC_ACCESS_TOKEN to a Keyverse access token with the required "
            "scope, then author the next official-control policy (for example CSAP 10.2.1)."
        )
    return "Use an official catalog identifier, then attach the next evidence."


def _cli_decision(
    declared_actor: str | None,
    purpose: PurposeCode,
    required_scopes: tuple[str, ...],
) -> AuthorizationDecision:
    """Build a purpose decision from Keyverse when required, else from ``--actor``."""
    if not keyverse_start_is_required():
        if not declared_actor:
            raise HTTPException(
                status_code=401,
                detail="State the actor and purpose before touching evidence.",
            )
        return AuthorizationDecision(declared_actor, purpose)
    principal = authenticate_cli_principal(
        declared_actor=declared_actor,
        required_scopes=required_scopes,
    )
    return decision_for_request(principal, purpose.value, purpose)


def _cli_read_principal() -> RequestPrincipal | None:
    """Return the verified CLI principal for reads, or None in local preview."""
    if not keyverse_start_is_required():
        return None
    return authenticate_cli_principal(
        declared_actor=None,
        required_scopes=POLICY_READ_SCOPES,
    )


def _owned_policy_documents(
    session: Session,
    principal: RequestPrincipal | None,
) -> list[PolicyDocument]:
    """List policies, limited to the verified officer and tenant when Keyverse is required."""
    documents = list_policy_documents(session)
    if principal is None:
        return documents
    return [
        document
        for document in documents
        if document.created_by_actor == principal.actor_identifier
        and document.tenant_identifier == principal.tenant_identifier
    ]


def _owned_policy_gaps(
    session: Session,
    principal: RequestPrincipal | None,
    policy_document_id: str | None,
) -> list[PolicyGap]:
    """List uncovered mappings, limited to the verified tenant when Keyverse is required."""
    tenant = None if principal is None else principal.tenant_identifier
    gaps = list_policy_gaps(session, policy_document_id, tenant_identifier=tenant)
    if principal is None:
        return gaps
    owned = {
        document.policy_document_id
        for document in _owned_policy_documents(session, principal)
    }
    return [gap for gap in gaps if gap.policy_document_id in owned]


def _policy_command(namespace: argparse.Namespace) -> int:
    """Author, revise, or list policies."""
    action = namespace.policy_command
    session = _open_session()
    try:
        if action == "author":
            decision = _cli_decision(
                namespace.actor,
                PurposeCode.POLICY_AUTHORING,
                POLICY_WRITE_SCOPES,
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
            decision = _cli_decision(
                namespace.actor,
                PurposeCode.POLICY_AUTHORING,
                POLICY_WRITE_SCOPES,
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
                    for document in _owned_policy_documents(
                        session,
                        _cli_read_principal(),
                    )
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
        gaps = _owned_policy_gaps(session, _cli_read_principal(), policy_document_id)
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
        decision = _cli_decision(
            namespace.actor,
            PurposeCode.EVIDENCE_BINDING,
            EVIDENCE_WRITE_SCOPES,
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
    """Open a seeded product session for a one-shot CLI command."""
    url = os.environ.get(
        "CWL_GRC_DATABASE_URL",
        "sqlite:///grc_product.sqlite",
    )
    factory = create_session_factory(url)
    session = factory()
    seed_control_catalog(session)
    seed_authorization_purposes(session)
    session.commit()
    return session
