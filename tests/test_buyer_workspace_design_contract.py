"""Regression contract for the bounded GRC buyer-workspace design slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    """Return repository text used by the design-contract assertions."""

    return (ROOT / path).read_text(encoding="utf-8")


def test_workspace_exposes_truthful_buyer_states_and_next_actions() -> None:
    """Keep projection states explicit and every surface oriented to a next action."""

    html = read("apps/grc-workspace/index.html")
    for state in ("unknown", "not assessed", "stale", "blocked", "access denied"):
        assert state in html.lower()
    for action in ("Request missing evidence", "View exact values", "Open evidence room"):
        assert action in html
    assert 'aria-labelledby="workspace-title"' in html
    assert '<table' in html
    assert '<caption>' in html


def test_workspace_preserves_keyboard_motion_touch_print_and_responsive_contracts() -> None:
    """Require the CSS-level WCAG and report fallbacks owned by this fixture."""

    css = read("apps/grc-workspace/styles.css")
    for contract in (
        ":focus-visible",
        "@media (prefers-reduced-motion: reduce)",
        "@media print",
        "@media (max-width: 720px)",
        "min-height: 44px",
    ):
        assert contract in css


def test_storybook_inventory_covers_reusable_states_with_a11y_enabled() -> None:
    """Keep Storybook and Figma as paired design authority for the bounded slice."""

    main = read(".storybook/main.mjs")
    stories = read("apps/grc-workspace/workspace.stories.mjs")
    package = read("package.json")
    assert "@storybook/web-components-vite" in main
    assert "@storybook/addon-a11y" in main
    for story in ("ComplianceOfficerDesktop", "ComplianceOfficerMobile", "AccessDenied", "StaleEvidence"):
        assert story in stories
    assert '"storybook": "10.5.10"' in package
    assert '"@storybook/web-components-vite": "10.5.10"' in package
    assert '"@storybook/addon-a11y": "10.5.10"' in package


def test_design_authority_is_traceable_to_figma_and_decision_records() -> None:
    """Require a stable Figma source and explicit ownership/limitation records."""

    adr = read("docs/adr/0012-grc-buyer-workspace-design-authority.md")
    prd = read("docs/product/grc-buyer-workspace-prd.md")
    trd = read("docs/product/grc-buyer-workspace-trd.md")
    for document in (adr, prd, trd):
        assert "ta1jjWSjmADz2BFxka9UPs" in document
    assert "1:72" in adr
    assert "1:150" in adr
    assert "WCAG 2.2 AA" in adr
    assert "projection" in adr.lower()
    assert "not production evidence" in trd.lower()
