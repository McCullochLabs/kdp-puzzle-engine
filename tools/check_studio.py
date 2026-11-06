"""Run on the HP: python tools/check_studio.py [--model NAME --smoke-local-ai]."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from publishing.studio_health import collect_readiness, readiness_text
from publishing.studio_assistant import LocalAssistant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model')
    parser.add_argument('--smoke-local-ai', action='store_true', help='Classify one harmless request using an installed model; never generate files.')
    args = parser.parse_args()
    result = collect_readiness(ROOT)
    print(readiness_text(result))
    if args.smoke_local_ai:
        if not args.model:
            parser.error('--model is required for the explicit inference smoke check')
        try:
            intent = LocalAssistant().interpret('Make a space activity pack', args.model)
            if intent.action != 'create_pack' or not intent.topic:
                print('Local AI needs refinement: the sample request was not understood.')
                return 1
            print(f'Local AI smoke passed: {intent.action}, topic={intent.topic}. No files were generated.')
        except Exception as exc:
            print(f'Local AI smoke failed: {exc}')
            return 1
    return 0 if result['ready'] else 1


if __name__ == '__main__': raise SystemExit(main())
