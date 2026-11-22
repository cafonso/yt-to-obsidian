from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.m4a")

print("Idioma detetado:", info.language)
for segment in segments:
    print(f"[{segment.start:.1f}s] {segment.text}")