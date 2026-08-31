"""Officer home: policies, coverage gaps, and the next evidence action."""

from __future__ import annotations

from html import escape

from cwl_grc.catalog import FrameworkCode, framework_label
from cwl_grc.models import ControlItem
from cwl_grc.policy import PolicyGap

_OFFICER_FRAMEWORKS = (
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

_OFFICER_HOME_SCRIPT = """
(function () {
  var tokenKey = "cwlGrcKeyverseAccessToken";
  var tokenInput = document.getElementById("keyverse-access-token");
  var loadButton = document.getElementById("load-keyverse-policy-gaps");
  var gapList = document.getElementById("policy-gap-list");
  var evidenceSelect = document.getElementById("officer-evidence-control");
  var authState = document.getElementById("keyverse-auth-state");
  var actionState = document.getElementById("officer-action-status");
  var requiresKeyverse = document.body.dataset.keyverseRequired === "true";
  var stored = sessionStorage.getItem(tokenKey);

  if (stored && tokenInput) {
    tokenInput.value = stored;
  }

  function accessToken() {
    return tokenInput ? tokenInput.value.trim() : "";
  }

  function setState(target, message) {
    if (target) {
      target.textContent = message;
    }
  }

  function clearChildren(target) {
    if (!target) {
      return;
    }
    while (target.firstChild) {
      target.removeChild(target.firstChild);
    }
  }

  function renderPolicyGaps(gaps) {
    clearChildren(gapList);
    clearChildren(evidenceSelect);
    var seenControls = Object.create(null);

    if (!gaps.length) {
      if (gapList) {
        var emptyItem = document.createElement("li");
        emptyItem.textContent =
          "No uncovered policy requirements. Author the next policy or review existing evidence.";
        gapList.appendChild(emptyItem);
      }
      if (evidenceSelect) {
        var emptyOption = document.createElement("option");
        emptyOption.value = "";
        emptyOption.textContent = "No uncovered policy controls";
        evidenceSelect.appendChild(emptyOption);
        evidenceSelect.disabled = true;
      }
      return;
    }

    gaps.forEach(function (gap) {
      if (gapList) {
        var item = document.createElement("li");
        item.textContent =
          gap.policy_title + " maps " + gap.catalog_identifier + " " +
          gap.control_title + " — Attach the next evidence on this uncovered policy control.";
        gapList.appendChild(item);
      }
      if (evidenceSelect) {
        var controlRef = gap.framework + "|" + gap.catalog_identifier;
        if (!seenControls[controlRef]) {
          seenControls[controlRef] = true;
          var option = document.createElement("option");
          option.value = controlRef;
          option.textContent =
            gap.framework + " " + gap.catalog_identifier + " — " + gap.control_title;
          evidenceSelect.appendChild(option);
        }
      }
    });
    if (evidenceSelect) {
      evidenceSelect.disabled = false;
    }
  }

  function resetProtectedState() {
    sessionStorage.removeItem(tokenKey);
    if (tokenInput) {
      tokenInput.value = "";
    }
    clearChildren(gapList);
    if (gapList) {
      var hidden = document.createElement("li");
      hidden.textContent =
        "Policy gaps are hidden until Keyverse authorizes this token.";
      gapList.appendChild(hidden);
    }
    clearChildren(evidenceSelect);
    if (evidenceSelect) {
      var emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "Load your policy gaps first";
      evidenceSelect.appendChild(emptyOption);
      evidenceSelect.disabled = true;
    }
    setState(
      authState,
      "Policy gaps are hidden until Keyverse authorizes this token."
    );
  }

  function loadOfficerGaps() {
    if (!requiresKeyverse) {
      return;
    }
    var token = accessToken();
    if (!token) {
      setState(
        authState,
        "Enter a Keyverse access token, then load your policy gaps."
      );
      if (tokenInput) {
        tokenInput.focus();
      }
      return;
    }
    sessionStorage.setItem(tokenKey, token);
    setState(authState, "Loading policy gaps from your authorized organization…");
    fetch("/policy-gaps", {
      headers: { Authorization: "Bearer " + token }
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("keyverse-policy-gaps");
      }
      return response.json();
    }).then(function (payload) {
      renderPolicyGaps(payload.gaps || []);
      setState(
        authState,
        "Policy gaps loaded. Author a policy or attach evidence to an uncovered control."
      );
    }).catch(function () {
      resetProtectedState();
    });
  }

  if (loadButton) {
    loadButton.addEventListener("click", loadOfficerGaps);
  }

  function submitOfficerForm(form, purpose) {
    if (!form) {
      return;
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var token = accessToken();
      var actorField = form.querySelector('[name="actor_identifier"]');
      var actor = actorField ? actorField.value.trim() : "";
      if (token) {
        sessionStorage.setItem(tokenKey, token);
      } else if (!actor) {
        if (tokenInput) {
          tokenInput.setCustomValidity(
            "Present a Keyverse access token, or the officer identifier for local preview."
          );
          tokenInput.reportValidity();
          tokenInput.setCustomValidity("");
        }
        return;
      }
      var headers = { "X-Purpose": purpose };
      if (token) {
        headers.Authorization = "Bearer " + token;
      } else {
        headers["X-Actor-Id"] = actor;
      }
      setState(actionState, "Submitting the officer action…");
      fetch(form.action, {
        method: "POST",
        headers: headers,
        body: new FormData(form)
      }).then(function (response) {
        if (response.ok || response.redirected) {
          if (token) {
            sessionStorage.setItem(tokenKey, token);
          }
          if (requiresKeyverse) {
            setState(
              actionState,
              "Action recorded. Reloading your authorized policy gaps."
            );
            loadOfficerGaps();
            return;
          }
          window.location.assign("/");
          return;
        }
        setState(
          actionState,
          "The officer action could not be completed. Check the fields and authorization, then try again."
        );
      }).catch(function () {
        setState(
          actionState,
          "The officer action could not reach the local service. Check the service and try again."
        );
      });
    });
  }

  submitOfficerForm(
    document.getElementById("officer-policy-form"),
    "policy_authoring"
  );
  submitOfficerForm(
    document.getElementById("officer-evidence-form"),
    "evidence_binding"
  );

  if (requiresKeyverse && stored) {
    loadOfficerGaps();
  }
})();
""".strip()


def render_officer_home(
    uncovered: list[ControlItem],
    policy_gaps: list[PolicyGap] | None = None,
    catalog_items: list[ControlItem] | None = None,
    *,
    keyverse_required: bool = False,
) -> str:
    """Render the officer home with policy authoring and the next evidence action."""
    gaps = policy_gaps or []
    catalog = catalog_items or []
    sections: list[str] = []
    for code in _OFFICER_FRAMEWORKS:
        rows = [item for item in uncovered if item.framework_key == code.value]
        items = "".join(_row(item) for item in rows) or (
            "<li>Every seeded control in this catalog has evidence. Review the bindings or attach another artifact.</li>"
        )
        sections.append(
            f"<section><h2>{escape(framework_label(code))}</h2><ul>{items}</ul></section>"
        )
    if keyverse_required:
        gap_items = (
            '<li id="policy-gap-auth-required">'
            "Enter a Keyverse access token, then load your policy gaps."
            "</li>"
        )
        evidence_options = '<option value="">Load your policy gaps first</option>'
        coverage_sections = ""
        evidence_disabled = " disabled"
        keyverse_action = """
  <button type="button" id="load-keyverse-policy-gaps">Load my policy gaps</button>
  <p id="keyverse-auth-state" role="status" aria-live="polite">
    Enter a Keyverse access token, then load your policy gaps.
  </p>"""
    else:
        gap_items = "".join(_policy_gap_row(gap) for gap in gaps) or (
            "<li>No uncovered policy requirements. Author the next policy or attach another artifact.</li>"
        )
        evidence_options = "".join(
            f'<option value="{escape(item.framework_key)}|{escape(item.catalog_identifier)}">'
            f"{escape(item.framework_key)} {escape(item.catalog_identifier)} — {escape(item.control_title)}"
            "</option>"
            for item in uncovered
            if item.framework_key in {code.value for code in _OFFICER_FRAMEWORKS}
        )
        coverage_sections = "".join(sections)
        evidence_disabled = ""
        keyverse_action = ""
    mapping_source = catalog or uncovered
    policy_options = "".join(
        f'<option value="{escape(item.framework_key)}|{escape(item.catalog_identifier)}">'
        f"{escape(item.framework_key)} {escape(item.catalog_identifier)} — {escape(item.control_title)}"
        "</option>"
        for item in mapping_source
        if item.framework_key in {code.value for code in _POLICY_FRAMEWORKS}
    )
    keyverse_flag = "true" if keyverse_required else "false"
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
<body data-keyverse-required="{keyverse_flag}">
  <h1>Author the next policy, then attach evidence on uncovered controls</h1>
  <p>Map each policy to official CSAP / SOC 2 / ISMS-P / ISO 27001 identifiers. Officer contact details stay usable; they are not masked.</p>
  <label>Keyverse access token
    <input id="keyverse-access-token" type="password" autocomplete="off">
  </label>
  <p>Present a Keyverse access token when Keyverse is configured. Local preview uses the officer identifier instead.</p>
{keyverse_action}
  <p id="officer-action-status" role="status" aria-live="polite"></p>
  <h2>Author the next policy</h2>
  <form id="officer-policy-form" method="post" action="/officer/policy">
    <label>Policy title
      <input name="policy_title" required placeholder="Logical Access Policy">
    </label>
    <label>Policy body
      <textarea name="policy_body" required></textarea>
    </label>
    <label>Officer identifier
      <input name="actor_identifier" placeholder="officer-ahn">
    </label>
    <label>Official controls this policy maps
      <select name="control_refs" multiple>{policy_options}</select>
    </label>
    <button type="submit">Author the next policy</button>
  </form>
  <h2>Policy requirements that still lack evidence</h2>
  <ul id="policy-gap-list">{gap_items}</ul>
  {coverage_sections}
  <h2>Attach the next evidence</h2>
  <form id="officer-evidence-form" method="post" action="/officer/evidence">
    <label>Uncovered control
      <select id="officer-evidence-control" name="control_ref" required{evidence_disabled}>{evidence_options}</select>
    </label>
    <label>Officer identifier
      <input name="actor_identifier" placeholder="officer-ahn">
    </label>
    <label>Evidence title
      <input name="evidence_title" required placeholder="CSAP 10.2.1 access-grant register">
    </label>
    <label>Evidence text, including usable PII
      <textarea name="payload_text" required></textarea>
    </label>
    <button type="submit">Attach the next evidence</button>
  </form>
  <script>
{_OFFICER_HOME_SCRIPT}
  </script>
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
