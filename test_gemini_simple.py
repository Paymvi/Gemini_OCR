import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ---------------------------------------
# Load API key
# ---------------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

print("1. API key found:", bool(api_key), flush=True)

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY was not found in your .env file."
    )


# ---------------------------------------
# Create Gemini client
# ---------------------------------------

client = genai.Client(
    api_key=api_key,

    http_options=types.HttpOptions(
        timeout=120000
    ),
)


# ---------------------------------------
# Test a fast Gemini model
# ---------------------------------------

print("2. Calling Gemini 3.5 Flash-Lite...", flush=True)

try:

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",

        input="Reply with exactly: API WORKS",
    )

    print("3. Gemini responded!", flush=True)

    print()
    print(interaction.output_text)


except Exception as error:

    print()
    print("REQUEST FAILED:")
    print(type(error).__name__)
    print(error)