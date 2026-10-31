import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
if not key or key == "paste_your_key_here":
    raise SystemExit("No API key found. Put it in the .env file first.")

client = genai.Client(api_key=key)

print("Models available to your key:")
for m in client.models.list():
    print(" -", m.name)

model = os.getenv("GEMINI_MODEL")
if model:
    reply = client.models.generate_content(
        model=model,
        contents="Reply with exactly: Dark Spot is alive.",
    )
    print("\nModel replied:", reply.text)
else:
    print("\nNow copy one model name (without the 'models/' part) into GEMINI_MODEL in .env and run again.")