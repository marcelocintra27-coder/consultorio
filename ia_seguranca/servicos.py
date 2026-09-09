import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

MODELO_WHISPER = getattr(settings, "IA_WHISPER_MODELO", "small")

_modelo = None


def _get_modelo():
    """Carrega o modelo uma vez so e reaproveita."""
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel

        _modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    return _modelo


def converter_para_wav(caminho_entrada):
    """Converte qualquer audio para WAV 16kHz mono (formato que o Whisper espera).

    Retorna o caminho do arquivo temporario gerado.
    """
    entrada = Path(caminho_entrada)
    if not entrada.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {entrada}")

    destino = Path(tempfile.gettempdir()) / f"{entrada.stem}_16k.wav"

    comando = [
        "ffmpeg", "-y",
        "-i", str(entrada),
        "-ar", "16000",
        "-ac", "1",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)

    if resultado.returncode != 0 or not destino.exists():
        raise RuntimeError(f"Falha ao converter o audio: {resultado.stderr[-500:]}")

    return destino


def transcrever_audio(caminho_audio, idioma="pt"):
    """Transcreve um arquivo de audio e devolve (texto, duracao_segundos)."""
    wav = converter_para_wav(caminho_audio)
    modelo = _get_modelo()

    segmentos, info = modelo.transcribe(str(wav), language=idioma)
    texto = "".join(s.text for s in segmentos).strip()

    try:
        wav.unlink()
    except OSError:
        pass

    return texto, info.duration


def transcrever_e_registrar(caminho_audio, usuario=None, paciente=None, idioma="pt"):
    """Transcreve o audio e grava um RegistroAuditoriaIA com a sugestao gerada.

    A decisao fica como 'pendente' ate alguem revisar e aprovar o texto.
    """
    from .models import RegistroAuditoriaIA

    texto, _duracao = transcrever_audio(caminho_audio, idioma=idioma)

    registro = RegistroAuditoriaIA.objects.create(
        usuario=usuario,
        paciente=paciente,
        recurso="transcricao_voz",
        modelo_utilizado=f"faster-whisper:{MODELO_WHISPER}",
        entrada_resumo=f"Audio: {caminho_audio}",
        saida_sugerida=texto,
        decisao="pendente",
    )

    return registro
