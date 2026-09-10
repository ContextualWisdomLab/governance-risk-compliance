"""Execute the real engine-policy definitions in an isolated, no-network unit harness."""
from pathlib import Path
import ast
import sys
import types
import pytest

workspace_root = Path(__file__).resolve().parent
source_path = workspace_root / sys.argv[1]
source_tree = ast.parse(source_path.read_text(), feature_version=(3, 12))
selected_names = {'PostgresEngineSettings', 'build_engine', '_build_postgresql_engine', '_host_is_loopback'}
selected_nodes = []
for source_node in source_tree.body:
    if isinstance(source_node, ast.ImportFrom) and not (source_node.module or '').startswith('cwl_grc'):
        selected_nodes.append(source_node)
    elif isinstance(source_node, (ast.ClassDef, ast.FunctionDef)) and source_node.name in selected_names:
        selected_nodes.append(source_node)
    elif isinstance(source_node, ast.Assign) and any(isinstance(target_node, ast.Name) and target_node.id == 'POSTGRESQL_DRIVER' for target_node in source_node.targets):
        selected_nodes.append(source_node)
package_module = types.ModuleType('cwl_grc')
package_module.__path__ = []
database_module = types.ModuleType('cwl_grc.database')
database_module.__file__ = str(source_path)
sys.modules['cwl_grc'] = package_module
sys.modules['cwl_grc.database'] = database_module
package_module.database = database_module
exec(compile(ast.Module(body=selected_nodes, type_ignores=[]), str(source_path), 'exec'), database_module.__dict__)
raise SystemExit(pytest.main([str(workspace_root/'tests/test_postgresql_endpoint_policy.py'), '-q', '--tb=short']))
