"""ConceptWeave semantic-release boundary tests for GRC Analytics."""

from dataclasses import replace

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


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("release_id", "", "release identifier"),
        ("release_id", "   ", "release identifier"),
        ("release_id", None, "release identifier"),
        ("schema_version", "", "schema version"),
        ("schema_version", "   ", "schema version"),
        ("schema_version", None, "schema version"),
    ],
)
def test_malformed_release_identity_and_schema_fail_with_typed_error(
    field_name: str,
    invalid_value: object,
    message: str,
) -> None:
    """Reject incomplete release coordinates before a supplier adapter is invoked."""

    malformed = replace(_release(), **{field_name: invalid_value})

    with pytest.raises(SemanticReleaseValidationError, match=message):
        require_published_release(malformed)


@pytest.mark.parametrize("field_name", ["release_id", "schema_version"])
def test_release_coordinates_are_bounded_before_string_processing(field_name: str) -> None:
    """Reject oversized coordinates before supplier-controlled strings are normalized."""

    oversized = replace(_release(), **{field_name: "x" * 1025})

    with pytest.raises(SemanticReleaseValidationError, match="1024"):
        require_published_release(oversized)


def test_semantic_model_client_port_is_structural_and_provider_neutral() -> None:
    class FakeClient:
        def validate_release(self, release: SemanticReleaseRef) -> SemanticReleaseRef:
            return require_published_release(release)

        def resolve_term(self, *, release: SemanticReleaseRef, term: str) -> str | None:
            require_published_release(release)
            return "cwl:internal_control" if term == "internal control" else None

    assert isinstance(FakeClient(), SemanticModelClientPort)
