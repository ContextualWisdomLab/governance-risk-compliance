"""Provider-neutral semantic-model client port for GRC Analytics.

This application boundary lets GRC consume a governed semantic release without
importing ConceptWeave implementation classes, provider payloads, prompts, or
foreign persistence.  The concrete adapter is intentionally deferred until
ConceptWeave publishes its versioned client contract; this module only defines
what GRC requires from that contract.
"""

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol, runtime_checkable

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


class SemanticReleaseState(StrEnum):
    """Publication states that matter at the GRC consumer boundary."""

    PROPOSED = "proposed"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class SemanticReleaseRef:
    """Immutable coordinates for one ConceptWeave-compatible semantic release.

    The reference intentionally carries no endpoint, provider credential, raw
    source material, or generator-private state.  GRC may use an authoritative
    semantic model only after the caller-supplied release has passed the
    consumer-side publication and digest checks below and, later, the concrete
    ConceptWeave client adapter's schema/provenance validation.
    """

    release_id: str
    schema_version: str
    content_digest_sha256: str
    publication_state: SemanticReleaseState


class SemanticReleaseValidationError(ValueError):
    """Reject a semantic release that is unsafe for authoritative GRC analysis."""


@runtime_checkable
class SemanticModelClientPort(Protocol):
    """Application port that isolates GRC from semantic-model provider details."""

    def validate_release(self, release: SemanticReleaseRef) -> SemanticReleaseRef:
        """Validate and return a release that this client can safely consume."""

    def resolve_term(self, *, release: SemanticReleaseRef, term: str) -> str | None:
        """Resolve one GRC term to a stable semantic concept identifier, if known."""


def require_published_release(release: SemanticReleaseRef) -> SemanticReleaseRef:
    """Fail closed unless a semantic release has complete immutable coordinates.

    This is deliberately narrower than a future concrete ConceptWeave adapter.
    It prevents proposed or superseded semantic artifacts from being treated as
    authoritative in GRC and rejects incomplete release identity, schema, or
    digest coordinates.  Schema compatibility, signature/provenance policy,
    tenant and purpose authorization remain separate consumer/application
    responsibilities.
    """

    if release.publication_state is not SemanticReleaseState.PUBLISHED:
        raise SemanticReleaseValidationError(
            "authoritative GRC analysis requires a published semantic release"
        )
    release_id = release.release_id
    if type(release_id) is not str or not release_id.strip():
        raise SemanticReleaseValidationError(
            "semantic release identifier must be a non-empty string"
        )
    schema_version = release.schema_version
    if type(schema_version) is not str or not schema_version.strip():
        raise SemanticReleaseValidationError(
            "semantic release schema version must be a non-empty string"
        )
    digest = release.content_digest_sha256
    if type(digest) is not str or len(digest) != 64 or _SHA256_HEX.fullmatch(digest) is None:
        raise SemanticReleaseValidationError(
            "semantic release content digest must be lowercase SHA-256 hexadecimal"
        )
    return release
