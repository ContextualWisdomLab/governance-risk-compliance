"""Buyer-facing officer home: coverage gaps and the next evidence action."""

from __future__ import annotations

from html import escape

from cwl_grc.catalog import FrameworkCode, framework_label
from cwl_grc.models import ControlItem

_BUYER_FRAMEWORKS = (
    FrameworkCode.CSAP_2026,
    FrameworkCode.SOC2_TSC_2017,
    FrameworkCode.ISMS_P_2023,
)


def render_officer_home(uncovered: list[ControlItem]) -> str:
    """Render the officer home with the next action on every uncovered control."""
    sections: list[str] = []
    for code in _BUYER_FRAMEWORKS:
        rows = [item for item in uncovered if item.framework_key == code.value]
        items = "".join(_row(item) for item in rows) or (
            "<li>Every seeded control in this catalog has evidence. Review the bindings or attach another artifact.</li>"
        )
        sections.append(
            f"<section><h2>{escape(framework_label(code))}</h2><ul>{items}</ul></section>"
        )
    options = "".join(
        f'<option value="{escape(item.framework_key)}|{escape(item.catalog_identifier)}">'
        f"{escape(item.framework_key)} {escape(item.catalog_identifier)} — {escape(item.control_title)}"
        "</option>"
        for item in uncovered
        if item.framework_key in {code.value for code in _BUYER_FRAMEWORKS}
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CWL GRC — Control coverage</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; max-width: 52rem; }}
    label, input, select, textarea, button {{ display: block; width: 100%; margin: 0.4rem 0; }}
    textarea {{ min-height: 6rem; }}
  </style>
</head>
<body>
  <h1>See which CSAP / SOC 2 / ISMS-P controls still need evidence</h1>
  <p>Attach the next evidence on an uncovered control. Officer contact details stay usable; they are not masked.</p>
  {''.join(sections)}
  <h2>Attach the next evidence</h2>
  <form method="post" action="/officer/evidence">
    <label>Uncovered control
      <select name="control_ref" required>{options}</select>
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


def parse_control_ref(control_ref: str) -> tuple[str, str]:
    """Split a console control reference into framework key and catalog identifier."""
    framework_key, separator, catalog_identifier = control_ref.partition("|")
    if not separator or not framework_key or not catalog_identifier:
        raise ValueError("control_ref")
    return framework_key, catalog_identifier
