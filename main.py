import json
from pathlib import Path
from agents.persona_agent import evaluate_ux

persona_path = "personas/older_user.json"
screenshot_path = "screenshots/signup.png"

with open(persona_path, encoding="utf-8") as file:
    persona = json.load(file)

print("OMNI Persona UX Evaluation")
print("--------------------------")
print("Persona:", persona["name"])
print("Task: Create an account")
print("Analyzing screenshot...")

result = evaluate_ux(
    persona=persona,
    task="Create an account",
    screenshot_path=screenshot_path
)

Path("results").mkdir(exist_ok=True)

with open(
    "results/older_user_report.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(result, file, indent=4)

print("\nAnalysis Complete!")
print(json.dumps(result, indent=4))
