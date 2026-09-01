"""Architectural fitness tests for the GRC Analytics bounded context."""

import ast
from pathlib import Path
import sys

ANALYTICS_ROOT = Path(__file__).parents[1] / "cwl_grc" / "analytics"
GENERIC_DOMAIN_BUCKETS = {"common.py", "helpers.py", "misc.py", "services.py", "utils.py"}


def _absolute_imports(path: Path) -> set[str]:
    """Return absolute module imports so dependency-boundary assertions cannot be bypassed."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported_modules.add(node.module)
    return imported_modules


def _domain_imports_respect_boundary(path: Path) -> bool:
    """Allow domain modules to use stdlib or their own domain package, never the facade."""

    for module in _absolute_imports(path):
        if module.split(".", 1)[0] != "cwl_grc":
            continue
        if module == "cwl_grc.analytics.domain":
            continue
        if module.startswith("cwl_grc.analytics.domain."):
            continue
        return False
    return True


def test_analytics_is_a_named_bounded_context_with_explicit_layers():
    assert (ANALYTICS_ROOT / "domain" / "query_contract.py").is_file()
    assert (ANALYTICS_ROOT / "application" / "planning.py").is_file()
    python_paths = (path.name for path in ANALYTICS_ROOT.rglob("*.py"))
    assert not GENERIC_DOMAIN_BUCKETS.intersection(python_paths)


def test_analytics_domain_and_application_only_depend_on_stdlib_or_their_own_context():
    """Reject undisclosed provider/database SDKs and flat-kernel imports in either syntax."""

    for path in ANALYTICS_ROOT.rglob("*.py"):
        for module in _absolute_imports(path):
            root = module.split(".", 1)[0]
            if root == "cwl_grc":
                assert module.startswith("cwl_grc.analytics"), (path, module)
            else:
                assert root in sys.stdlib_module_names, (path, module)


def test_domain_has_no_dependency_on_application_layer():
    domain_root = ANALYTICS_ROOT / "domain"
    for path in domain_root.rglob("*.py"):
        assert _domain_imports_respect_boundary(path), path


def test_domain_import_policy_rejects_package_facade(tmp_path):
    """The package facade exports application symbols and must not enter the domain layer."""

    probe = tmp_path / "facade_bypass.py"
    probe.write_text(
        "from cwl_grc.analytics import build_query_plan\n",
        encoding="utf-8",
    )

    assert not _domain_imports_respect_boundary(probe)
