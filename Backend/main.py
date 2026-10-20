"""Optional CLI; the website uses app.server."""
import argparse
import json
from pathlib import Path
from agents.persona_agent import evaluate_ux

def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='Evaluate a screenshot with an OMNI persona.')
    parser.add_argument('--persona', type=Path, default=root/'personas/older_user.json')
    parser.add_argument('--screenshot', type=Path, default=root/'screenshots/signup.png')
    parser.add_argument('--task', default='Create an account')
    parser.add_argument('--output', type=Path, default=root/'results/cli_report.json')
    args = parser.parse_args()
    result = evaluate_ux(json.loads(args.persona.read_text(encoding='utf-8')),args.task,args.screenshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
