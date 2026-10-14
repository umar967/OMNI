import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


def evaluate_ux(persona, task, screenshot_path):

    prompt = f"""
You are OMNI's AI Persona UX Evaluation Agent.

USER PERSONA:
{json.dumps(persona, indent=2)}

USER TASK:
{task}

Evaluate the provided screenshot from this persona's
perspective.

Focus on the evaluation criteria defined in the persona.

RULES:
1. Identify only issues supported by visible evidence.
2. Do not invent user interactions or hidden functionality.
3. Explain why each issue may affect this persona.
4. Give a practical recommendation for each issue.
5. If no issues are visible, return an empty findings list.
6. Return valid JSON only.

SEVERITY:
Low: Minor inconvenience.
Medium: Causes noticeable confusion or friction.
High: May prevent task completion.

JSON OUTPUT:
{{
  "persona": "Persona name",
  "task": "User task",
  "findings": [
    {{
      "issue": "Issue title",
      "category": "UX category",
      "severity": "Low, Medium or High",
      "explanation": "Why this is a problem",
      "evidence": "What is visible in the screenshot",
      "recommendation": "Suggested improvement"
    }}
  ]
}}
"""

    image_bytes = Path(screenshot_path).read_bytes()

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png"
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )

    return json.loads(response.text)
