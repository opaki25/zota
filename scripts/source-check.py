"""Dependency-free source checks; not a replacement for runtime tests."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = list((root / 'apps/api').rglob('*.py'))
for file in files:
    ast.parse(file.read_text(encoding='utf-8'), filename=str(file))
for file in [root/'package.json', root/'apps/web/package.json', root/'apps/web/tsconfig.json']:
    json.loads(file.read_text(encoding='utf-8'))
assert (root/'apps/web/app/page.tsx').is_file()
assert (root/'apps/api/migrations/versions/0001_phase_one.py').is_file()
print(f'Parsed {len(files)} Python files and 3 JSON manifests. Source structure checks passed.')
