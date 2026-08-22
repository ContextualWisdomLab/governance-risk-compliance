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
    for action in (
        "Request missing evidence",
        "View exact values",
        "Open evidence room",
        "Request access",
    ):
        assert action in html
    assert 'aria-labelledby="workspace-title"' in html
    assert '<html lang="en">' in html
    assert '<table' in html
    assert '<caption' in html
    assert 'data-i18n="table.deficienciesValue"' in html
    assert 'data-i18n="action.requestAccess"' in html
    assert 'id="action-feedback"' in html
    assert 'href="#exact-title"' in html


def test_workspace_preserves_keyboard_motion_touch_print_and_responsive_contracts() -> None:
    """Require the CSS-level WCAG and report fallbacks owned by this fixture."""

    css = read("apps/grc-workspace/styles.css")
    for contract in (
        ":focus-visible",
        "@media (prefers-reduced-motion: reduce)",
        "@media print",
        "@media (max-width: 720px)",
        "min-height: 44px",
        "clip-path: inset(50%)",
        "[hidden] { display: none !important; }",
    ):
        assert contract in css


def test_storybook_inventory_covers_reusable_states_with_a11y_enabled() -> None:
    """Keep Storybook and Figma as paired design authority for the bounded slice."""

    main = read(".storybook/main.mjs")
    stories = read("apps/grc-workspace/workspace.stories.mjs")
    package = read("package.json")
    assert "@storybook/web-components-vite" in main
    assert "@storybook/addon-a11y" in main
    assert "docs: { autodocs: true }" not in main
    assert "tags: ['!autodocs']" in stories
    assert "./index.html?raw" in stories
    assert "accessDenied = true" in stories
    assert "stale = true" in stories
    assert "renderFixture({ accessDenied: true, stale: false })" in stories
    assert "renderFixture({ accessDenied: false, stale: true })" in stories
    assert "globals: { viewport: { value: 'mobile1', isRotated: false } }" in stories
    assert "parameters: { viewport: { defaultViewport: 'mobile1' } }" not in stories
    for story in (
        "ComplianceOfficerDesktop",
        "ComplianceOfficerMobile",
        "AccessDenied",
        "StaleEvidence",
        "KoreanLocale",
    ):
        assert story in stories
    assert '"storybook": "10.5.10"' in package
    assert '"@storybook/web-components-vite": "10.5.10"' in package
    assert '"@storybook/addon-a11y": "10.5.10"' in package


def test_frontend_toolchain_and_browser_gate_are_pinned() -> None:
    """Keep CI reproducible and exercise the real static page in a browser."""

    package = read("package.json")
    lock = read("package-lock.json")
    mise = read("mise.toml")
    workflow = read(".github/workflows/buyer-workspace.yml")
    assert '"@playwright/test": "1.62.1"' in package
    assert '"test:buyer-workspace": "playwright test tests/buyer-workspace.spec.mjs"' in package
    assert '"name": "cwl-grc-design-authority"' in lock
    assert 'node = "24.18.0"' in mise
    assert "corepack npm ci" in workflow
    assert "node-version: '24.18.0'" in workflow
    assert "playwright install --with-deps chromium" in workflow
    assert "test:buyer-workspace" in workflow


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


def test_i18n_contract_keeps_english_and_korean_semantics_aligned() -> None:
    """Require one locale controller for the real page and Storybook fixture."""

    html = read("apps/grc-workspace/index.html")
    i18n = read("apps/grc-workspace/i18n.mjs")
    controller = read("apps/grc-workspace/locale-controller.mjs")
    bootstrap = read("apps/grc-workspace/i18n-bootstrap.mjs")
    stories = read("apps/grc-workspace/workspace.stories.mjs")
    assert 'lang="en"' in html
    assert 'id="locale-select"' in html
    assert 'src="./i18n-bootstrap.mjs"' in html
    assert "export const LOCALES" in i18n
    assert "'ko'" in i18n
    for key in (
        "header.title",
        "metric.applicable",
        "status.unknown3",
        "action.requestAccess",
        "feedback.limitation",
    ):
        assert f"'{key}'" in i18n
    assert "local developer preview" in i18n
    assert "로컬 개발자 미리보기" in i18n
    assert "export function initializeLocale" in controller
    assert "applyLocale(root, requestedLocale)" in controller
    assert "select.addEventListener('change'" in controller
    assert "initializeLocale(document, document.documentElement.lang)" in bootstrap
    assert "initializeLocale(host, locale)" in stories
    assert "KoreanLocale" in stories
