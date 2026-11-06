"""Read-only local readiness evidence, with no automatic repairs or downloads."""
import json
from pathlib import Path
import platform

from background_generation.index import approval_state, retired_from_new_production
from tools.check_runtime import runtime_errors
from .studio_assistant import LocalAssistant


def collect_readiness(root, check_ai=True):
    root = Path(root)
    result = {'platform': platform.system(), 'python': platform.python_version(), 'blockers': runtime_errors(), 'notes': [], 'models': []}
    for name in ('word_search_creator.py', 'wordsearch.py', 'sudoku.py', 'cover.py', 'wrap_cover.py'):
        if not (root/name).is_file(): result['blockers'].append(f'Required application file missing: {name}')
    registry = root/'cover_assets'/'generated_background_index.json'
    try:
        data = json.loads(registry.read_text(encoding='utf-8-sig'))
        rows = data.get('assets', [])
        if not isinstance(rows, list): raise ValueError('Invalid artwork registry.')
        approved = [row for row in rows if isinstance(row, dict) and approval_state(row) == 'approved' and not retired_from_new_production(row)]
        missing = [str(row.get('path') or '') for row in approved if not row.get('path') or not (root/str(row['path'])).is_file()]
        available = len(approved)-len(missing)
        result['notes'].append(f'{available} approved, active artwork files are available. Topic matching and final proof checks still apply.')
        if missing:
            result['blockers'].append(f'{len(missing)} approved artwork files are missing. Restore the originals from the HP or recover the correct assets; do not bypass approval.')
            result['missing_artwork'] = missing
        if not approved: result['blockers'].append('No approved, active cover artwork is recorded. Use the existing cover review workflow.')
    except (OSError, ValueError, AttributeError) as exc:
        result['blockers'].append(f'Cover registry could not be read: {exc}')
    if check_ai:
        try:
            result['models'] = LocalAssistant().models()
            result['notes'].append(f"Ollama: {len(result['models'])} installed local model(s). No download or inference was performed.")
        except Exception:
            result['notes'].append('Ollama is not reachable on this computer. Guide mode remains available.')
    result['notes'].append('Windows fonts/scaling, a physical print sample, and uncoached family testing still need verification on the HP.')
    result['ready'] = not result['blockers']
    return result


def readiness_text(result):
    lines = [f"Computer: {result['platform']} | Python {result['python']}", '', 'Ready for local testing' if result['ready'] else 'Items need attention before complete book production']
    lines += ['- '+item for item in result['blockers']]
    lines += ['', *result['notes']]
    if result.get('models'): lines += ['', 'Installed local models:', *result['models']]
    return '\n'.join(lines)
