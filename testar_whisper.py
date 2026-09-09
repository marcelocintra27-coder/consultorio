import time
from faster_whisper import WhisperModel

ARQUIVO = "teste2.wav"

print("Carregando modelo...")
modelo = WhisperModel("small", device="cpu", compute_type="int8")

print("Transcrevendo...")
inicio = time.time()
segmentos, info = modelo.transcribe(ARQUIVO, language="pt")

texto = ""
for s in segmentos:
    print(f"[{s.start:.1f}s -> {s.end:.1f}s] {s.text}")
    texto += s.text

print("=" * 40)
print("TEXTO COMPLETO:")
print(texto.strip())
print("=" * 40)
print(f"Tempo: {round(time.time() - inicio, 1)}s")
