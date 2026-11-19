import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


def main() -> None:
    raiz_projeto = Path(__file__).resolve().parent.parent
    load_dotenv(raiz_projeto / ".env")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não definida no ambiente nem no .env da raiz.")

    client = genai.Client(api_key=api_key)

    for m in client.models.list():
        if "flash" in m.name.lower() or "lite" in m.name.lower():
            print(m.name)


if __name__ == "__main__":
    main()