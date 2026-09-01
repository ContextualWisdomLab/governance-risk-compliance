import ast
from pathlib import Path

ANALYTICS_ROOT = Path(__file__).parents[1] / "cwl_grc" / "analytics"
FORBIDDEN_EXTERNAL_IMPORTS = {"anthropic", "httpx", "openai", "requests", "sqlalchemy"}
GENERIC_DOMAIN_BUCKETS = {"common.py", "helpers.py", "misc.py", "services.py", "utils.py"}


def test_analytics_is_a_named_bounded_context_with_explicit_layers():
    assert (ANALYTICS_ROOT / "domain" / "query_contract.py").is_file()
    assert (ANALYTICS_ROOT / "application" / "planning.py").is_file()
    assert not GENERIC_DOMAIN_BUCKETS.intersection(path.name for path in ANALYTICS_ROOT.rglob("*.py"))


def test_analytics_domain_and_application_do_not_own_provider_or_database_adapters():
    for path in ANALYTICS_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                assert not roots.intersection(FORBIDDEN_EXTERNAL_IMPORTS), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                assert root not in FORBIDDEN_EXTERNAL_IMPORTS, path


def test_domain_has_no_dependency_on_application_or_existing_flat_kernel_modules():
    domain_root = ANALYTICS_ROOT / "domain"
    for path in domain_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any(module.startswith("cwl_grc.analytics.application") for module in imported_modules)
        assert not any(
            module.startswith(("cwl_grc.app", "cwl_grc.models", "cwl_grc.database"))
            for module in imported_modules
        )
