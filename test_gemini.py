import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


print("1. Starting test...", flush=True)

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

print("2. Loaded .env", flush=True)
print(f"3. Gemini API key found: {bool(api_key)}", flush=True)

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY was not found. Check your .env file."
    )


print("4. Creating Gemini client...", flush=True)

client = genai.Client(
    api_key=api_key,

    # Give Gemini up to 2 minutes.
    http_options=types.HttpOptions(
        timeout=120000
    ),
)


print("5. Calling Gemini 3.5 Flash Lite...", flush=True)

try:

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",

        input="Reply with exactly: API WORKS",

        generation_config={
            "thinking_level": "low"
        },
    )

    print("6. Gemini responded!", flush=True)

    print()
    print(interaction.output_text)


except Exception as error:

    print()
    print("GEMINI REQUEST FAILED:")

    print(type(error).__name__)
    print(error)