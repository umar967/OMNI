"""Retry only the report review for a saved exploration run."""

import argparse
import json
import os
from pathlib import Path

from Backend.agents.exploration_agent import apply_review, clean_review, review_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path,
                        help='Path to an exploration_* results folder')
    parser.add_argument('--provider', choices=['gemini', 'ollama'], default='ollama')
    parser.add_argument('--model', help='Model name (default qwen3:4b for Ollama)')
    args = parser.parse_args()
    if not args.run.is_dir():
        parser.error('Run folder does not exist')
    os.environ['OMNI_MODEL_PROVIDER'] = args.provider
    if args.model:
        os.environ['OLLAMA_MODEL' if args.provider == 'ollama' else 'GEMINI_MODEL'] = args.model
    persona = json.loads((args.run / 'persona.json').read_text(encoding='utf-8'))
    history = json.loads((args.run / 'history.json').read_text(encoding='utf-8'))
    if not history:
        parser.error('Saved run contains no actions to review')
    report_path = args.run / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['actions_recorded'] = len(history)
    print(f"Reviewing {len(history)} saved actions with {args.provider}...", flush=True)
    try:
        review = clean_review(review_run(persona, history), history)
    except Exception as exc:
        report['review_status'] = 'not_completed'
        report['review_error'] = str(exc)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        raise SystemExit(f'Review did not finish: {exc}')
    apply_review(report, review)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Persona experience review saved: {report_path} "
          f"({len(report['findings'])} candidate issues)")


if __name__ == '__main__':
    main()
