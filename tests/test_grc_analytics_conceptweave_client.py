"""ConceptWeave semantic-release boundary tests for GRC Analytics."""

import pytest

from cwl_grc.analytics.application.semantic_model import (
    SemanticModelClientPort,
    SemanticReleaseRef,
    SemanticReleaseState,
    SemanticReleaseValidationError,
    require_published_release,
)


def _release(*, state: SemanticReleaseState = SemanticReleaseState.PUBLISHED) -> SemanticReleaseRef:
    return SemanticReleaseRef(
        release_id="conceptweave-grc-2026-09-01",
        schema_version="cwl.conceptweave.semantic-release.v1",
        content_digest_sha256="a" * 64,
        publication_state=state,
    )


def test_published_release_is_accepted_for_authoritative_grc_analysis() -> None:
    release = _release()

    assert require_published_release(release) is release


def test_proposed_release_is_rejected_for_authoritative_grc_analysis() -> None:
    with pytest.raises(SemanticReleaseValidationError, match="published"):
        require_published_release(_release(state=SemanticReleaseState.PROPOSED))


def test_release_digest_must_be_lowercase_sha256_hex() -> None:
    release = SemanticReleaseRef(
        release_id="conceptweave-grc-2026-09-01",
        schema_version="cwl.conceptweave.semantic-release.v1",
        content_digest_sha256="NOT-A-SHA256",
        publication_state=SemanticReleaseState.PUBLISHED,
    )

    with pytest.raises(SemanticReleaseValidationError, match="SHA-256"):
        require_published_release(release)


def test_malformed_release_digest_fails_with_typed_validation_error() -> None:
    release = SemanticReleaseRef(
        release_id="conceptweave-grc-2026-09-01",
        schema_version="cwl.conceptweave.semantic-release.v1",
        content_digest_sha256=None,
        publication_state=SemanticReleaseState.PUBLISHED,
    )

    with pytest.raises(SemanticReleaseValidationError, match="SHA-256"):
        require_published_release(release)


def test_semantic_model_client_port_is_structural_and_provider_neutral() -> None:
    class FakeClient:
        def validate_release(self, release: SemanticReleaseRef) -> SemanticReleaseRef:
            return require_published_release(release)

        def resolve_term(self, *, release: SemanticReleaseRef, term: str) -> str | None:
            require_published_release(release)
            return "cwl:internal_control" if term == "internal control" else None

    assert isinstance(FakeClient(), SemanticModelClientPort)
