import sys
from pathlib import Path
from faster_whisper import WhisperModel

if len(sys.argv) < 2:
    print("Uso: uv run python som-para-txt.py <ficheiro-de-audio>")
    sys.exit(1)

caminho = Path(sys.argv[1])
if not caminho.exists():
    print(f"Ficheiro não encontrado: {caminho}")
    sys.exit(1)

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe(str(caminho))

print("Idioma detetado:", info.language)
for segment in segments:
    print(f"[{segment.start:.1f}s] {segment.text}")