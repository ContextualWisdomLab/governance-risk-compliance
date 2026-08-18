"""Buyer-facing officer home: policies, coverage gaps, and the next evidence action."""

from __future__ import annotations

from html import escape

from cwl_grc.catalog import FrameworkCode, framework_label
from cwl_grc.models import ControlItem
from cwl_grc.policy import PolicyGap

_BUYER_FRAMEWORKS = (
    FrameworkCode.CSAP_2026,
    FrameworkCode.SOC2_TSC_2017,
    FrameworkCode.ISMS_P_2023,
)

_POLICY_FRAMEWORKS = (
    FrameworkCode.CSAP_2026,
    FrameworkCode.SOC2_TSC_2017,
    FrameworkCode.ISMS_P_2023,
    FrameworkCode.ISO27001_2022,
)


def render_officer_home(
    uncovered: list[ControlItem],
    policy_gaps: list[PolicyGap] | None = None,
    catalog_items: list[ControlItem] | None = None,
) -> str:
    """Render the officer home with policy authoring and the next evidence action."""
    gaps = policy_gaps or []
    catalog = catalog_items or []
    sections: list[str] = []
    for code in _BUYER_FRAMEWORKS:
        rows = [item for item in uncovered if item.framework_key == code.value]
        items = "".join(_row(item) for item in rows) or (
            "<li>Every seeded control in this catalog has evidence. Review the bindings or attach another artifact.</li>"
        )
        sections.append(
            f"<section><h2>{escape(framework_label(code))}</h2><ul>{items}</ul></section>"
        )
    gap_items = "".join(_policy_gap_row(gap) for gap in gaps) or (
        "<li>No uncovered policy requirements. Author the next policy or attach another artifact.</li>"
    )
    evidence_options = "".join(
        f'<option value="{escape(item.framework_key)}|{escape(item.catalog_identifier)}">'
        f"{escape(item.framework_key)} {escape(item.catalog_identifier)} — {escape(item.control_title)}"
        "</option>"
        for item in uncovered
        if item.framework_key in {code.value for code in _BUYER_FRAMEWORKS}
    )
    mapping_source = catalog or uncovered
    policy_options = "".join(
        f'<option value="{escape(item.framework_key)}|{escape(item.catalog_identifier)}">'
        f"{escape(item.framework_key)} {escape(item.catalog_identifier)} — {escape(item.control_title)}"
        "</option>"
        for item in mapping_source
        if item.framework_key in {code.value for code in _POLICY_FRAMEWORKS}
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CWL GRC — Policies and control coverage</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; max-width: 52rem; }}
    label, input, select, textarea, button {{ display: block; width: 100%; margin: 0.4rem 0; }}
    textarea {{ min-height: 6rem; }}
    select[multiple] {{ min-height: 10rem; }}
  </style>
</head>
<body>
  <h1>Author the next policy, then attach evidence on uncovered controls</h1>
  <p>Map each policy to official CSAP / SOC 2 / ISMS-P / ISO 27001 identifiers. Officer contact details stay usable; they are not masked.</p>
  <h2>Author the next policy</h2>
  <form method="post" action="/officer/policy">
    <label>Policy title
      <input name="policy_title" required placeholder="Logical Access Policy">
    </label>
    <label>Policy body
      <textarea name="policy_body" required></textarea>
    </label>
    <label>Officer identifier
      <input name="actor_identifier" required placeholder="officer-ahn">
    </label>
    <label>Official controls this policy maps
      <select name="control_refs" multiple>{policy_options}</select>
    </label>
    <button type="submit">Author the next policy</button>
  </form>
  <h2>Policy requirements that still lack evidence</h2>
  <ul>{gap_items}</ul>
  {''.join(sections)}
  <h2>Attach the next evidence</h2>
  <form method="post" action="/officer/evidence">
    <label>Uncovered control
      <select name="control_ref" required>{evidence_options}</select>
    </label>
    <label>Officer identifier
      <input name="actor_identifier" required placeholder="officer-ahn">
    </label>
    <label>Evidence title
      <input name="evidence_title" required placeholder="CSAP 10.2.1 access-grant register">
    </label>
    <label>Evidence text, including usable PII
      <textarea name="payload_text" required></textarea>
    </label>
    <button type="submit">Attach the next evidence</button>
  </form>
</body>
</html>
"""


def _row(item: ControlItem) -> str:
    """Render one uncovered control with the next action."""
    return (
        f"<li><strong>{escape(item.catalog_identifier)}</strong> "
        f"{escape(item.control_title)} — Attach the next evidence for {escape(item.catalog_identifier)}.</li>"
    )


def _policy_gap_row(gap: PolicyGap) -> str:
    """Render one uncovered policy mapping with the next action."""
    return (
        f"<li><strong>{escape(gap.policy_title)}</strong> maps "
        f"{escape(gap.catalog_identifier)} {escape(gap.control_title)} — "
        "Attach the next evidence on this uncovered policy control.</li>"
    )


def parse_control_ref(control_ref: str) -> tuple[str, str]:
    """Split a console control reference into framework key and catalog identifier."""
    framework_key, separator, catalog_identifier = control_ref.partition("|")
    if not separator or not framework_key or not catalog_identifier:
        raise ValueError("control_ref")
    return framework_key, catalog_identifier
