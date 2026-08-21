"""Verify the GRC hourly review-repair caller contract."""

from pathlib import Path


WORKFLOW = (
    Path(__file__).parents[1] / ".github" / "workflows" / "hourly-review-repair.yml"
)


def test_hourly_review_repair_caller_is_central_and_read_only() -> None:
    """Keep the leaf caller bound to the central scheduler and safe permissions."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "53 * * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert (
        "ContextualWisdomLab/.github/.github/workflows/"
        "pr-review-fix-scheduler.yml@55a8b576725451dfe0a21a57d36a2f1a41619b24"
        in workflow
    )
    assert "target_repository: ContextualWisdomLab/governance-risk-compliance" in workflow
    assert "base_branch: develop" in workflow
    assert 'max_dispatches: "1"' in workflow
    assert 'retry_hours: "2"' in workflow
    assert "contents: read" in workflow
    assert "id-token: write" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "COPILOT_GITHUB_TOKEN" not in workflow
