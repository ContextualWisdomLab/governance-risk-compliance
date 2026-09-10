"""Retain actual source-bound subprocess results for the no-network endpoint repair."""
from datetime import datetime, timezone
from pathlib import Path
import ast
import difflib
import hashlib
import importlib.metadata
import json
import subprocess
import sys

workspace_root = Path(__file__).resolve().parent
output_root = workspace_root / 'evidence'
output_root.mkdir(exist_ok=True)

def file_identity(file_path):
    file_bytes = file_path.read_bytes()
    git_header = f'blob {len(file_bytes)}\0'.encode()
    return {'git_blob_oid': hashlib.sha1(git_header + file_bytes).hexdigest(),
            'sha256': hashlib.sha256(file_bytes).hexdigest(), 'size_bytes': len(file_bytes)}

assert file_identity(workspace_root / 'database_before.py')['git_blob_oid'] == '9ec92990ee67ee028ffccd7b32dbe798868a42fe'
source_before = (workspace_root / 'database_before.py').read_text()
source_after = (workspace_root / 'database_after.py').read_text()
before_tree = ast.parse(source_before, feature_version=(3, 12))
after_tree = ast.parse(source_after, feature_version=(3, 12))
assert len(before_tree.body) == len(after_tree.body)
changed_symbols = []
for before_node, after_node in zip(before_tree.body, after_tree.body, strict=True):
    if ast.dump(before_node) != ast.dump(after_node):
        changed_symbols.append(getattr(before_node, 'name', type(before_node).__name__))
assert changed_symbols == ['_build_postgresql_engine']
assert all(ast.get_docstring(node) for node in after_tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)))
source_delta = ''.join(difflib.unified_diff(source_before.splitlines(True), source_after.splitlines(True), fromfile='parent/cwl_grc/database.py', tofile='candidate/cwl_grc/database.py'))
(output_root / 'source_delta.patch').write_text(source_delta)
commands = []
for output_name, command_argv, expected_exit in [
    ('negative_control.log', [sys.executable, 'run_endpoint_tests.py', 'database_before.py'], 1),
    ('endpoint_contracts.log', [sys.executable, 'run_endpoint_tests.py', 'database_after.py'], 0),
    ('compile_check.log', [sys.executable, '-m', 'compileall', '-q', 'database_after.py', 'tests/test_postgresql_endpoint_policy.py'], 0),
]:
    started_at = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command_argv, cwd=workspace_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=35)
    finished_at = datetime.now(timezone.utc).isoformat()
    (output_root / output_name).write_bytes(result.stdout)
    commands.append({'argv': command_argv, 'working_directory': str(workspace_root),
        'started_at': started_at, 'finished_at': finished_at, 'exit_code': result.returncode,
        'expected_exit_code': expected_exit, 'raw_output': output_name,
        'raw_output_sha256': hashlib.sha256(result.stdout).hexdigest()})
    print(output_name, result.returncode, result.stdout.decode(errors='replace').splitlines()[-1:] or ['no output'])
    assert result.returncode == expected_exit
receipt = {
    'schema_version': '1.0',
    'repository': 'ContextualWisdomLab/governance-risk-compliance',
    'source_parent': '56f2399ea2fa97f78afcf4da73aaa67f196a58a9',
    'source_path': 'cwl_grc/database.py',
    'test_path': 'tests/test_postgresql_endpoint_policy.py',
    'scope': '27 no-network unit cases execute the actual GRC engine-policy definitions and the real SQLAlchemy psycopg dialect URL conversion. The engine builder alone is captured; no libpq, socket, locked Product or PostgreSQL integration result is asserted.',
    'environment': {'python_version': sys.version, 'sqlalchemy': importlib.metadata.version('sqlalchemy'), 'pytest': importlib.metadata.version('pytest'), 'psycopg_installed': False},
    'commands': commands,
    'source_preservation': {'changed_top_level_symbols': changed_symbols, 'python_3_12_grammar_accepted': True, 'all_top_level_production_symbols_documented': True},
    'files': {name: file_identity(workspace_root / name) for name in ['database_before.py', 'database_after.py', 'tests/test_postgresql_endpoint_policy.py', 'run_endpoint_tests.py', 'capture_endpoint_verification.py']},
    'patch': {'path': 'source_delta.patch', **file_identity(output_root / 'source_delta.patch')},
}
(output_root / 'verification_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('receipt', file_identity(output_root / 'verification_receipt.json'))
print('candidate', file_identity(workspace_root / 'database_after.py'))
print('test', file_identity(workspace_root / 'tests/test_postgresql_endpoint_policy.py'))
