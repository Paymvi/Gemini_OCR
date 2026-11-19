"""Manual check that the Gemini API key and model in .env work. Sends one short request.

Run it with `python check_gemini.py`. It exits with code 1 if the request fails.
"""
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

import pipeline

load_dotenv(pipeline.ENV_PATH)

api_key = pipeline.get_api_key()
if not api_key:
    sys.exit("GEMINI_API_KEY was not found. Check your .env file.")

model = pipeline.get_model()
print(f"Calling {model}...", flush=True)

client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120000))  # 2 minutes

try:
    interaction = client.interactions.create(
        model=model,
        input="Reply with exactly: API WORKS",
        generation_config={"thinking_level": pipeline.get_thinking_level()},
    )
except Exception as error:
    print("GEMINI REQUEST FAILED:")
    print(f"{type(error).__name__}: {error}")
    sys.exit(1)

print(interaction.output_text)
