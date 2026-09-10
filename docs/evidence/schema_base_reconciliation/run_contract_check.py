"""Execute two workflow contracts from the merged test AST on a selected source tree.

This isolates static workflow tests in an environment without a full GRC checkout.
It does not import the GRC runtime, install the lockfile or emulate hosted CI.
"""
from pathlib import Path
import ast
import sys

workspace_root = Path(__file__).resolve().parent
selected_root = workspace_root / sys.argv[1]
merged_file = workspace_root / 'source_merged/tests/test_integrity_contracts.py'
source_tree = ast.parse(merged_file.read_text(), feature_version=(3, 12))
selected_names = (
    'test_product_workflow_rejects_any_dirty_tree',
    'test_product_workflow_only_cancels_superseded_pull_request_heads',
)
selected_nodes = [node for node in source_tree.body if isinstance(node, ast.FunctionDef) and node.name in selected_names]
assert len(selected_nodes) == 2
scope_values = {'REPOSITORY_ROOT': selected_root}
exec(compile(ast.Module(body=selected_nodes, type_ignores=[]), str(merged_file), 'exec'), scope_values)
for function_name in selected_names:
    scope_values[function_name]()
    print('PASS', function_name, flush=True)
