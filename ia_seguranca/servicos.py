import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

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

    destino = Path(tempfile.gettempdir()) / f"{uuid4().hex}_16k.wav"

    comando = [
        "ffmpeg", "-y",
        "-i", str(entrada),
        "-ar", "16000",
        "-ac", "1",
        str(destino),
    ]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=settings.IA_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('A conversão do áudio excedeu o tempo permitido.') from exc

    if resultado.returncode != 0 or not destino.exists():
        raise RuntimeError(f"Falha ao converter o audio: {resultado.stderr[-500:]}")

    return destino


def validar_duracao_audio(caminho_audio):
    """Rejeita áudio inválido ou longo antes de carregar o modelo Whisper."""
    comando = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(caminho_audio),
    ]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=settings.IA_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('A validação do áudio excedeu o tempo permitido.') from exc
    if resultado.returncode != 0:
        raise ValueError('Arquivo de áudio inválido.')
    try:
        duracao = float(resultado.stdout.strip())
    except ValueError as exc:
        raise ValueError('Não foi possível determinar a duração do áudio.') from exc
    if duracao <= 0 or duracao > settings.IA_AUDIO_MAX_DURATION_SECONDS:
        raise ValueError('A duração do áudio excede o limite permitido.')


def transcrever_audio(caminho_audio, idioma="pt"):
    """Transcreve um arquivo de audio e devolve (texto, duracao_segundos)."""
    wav = converter_para_wav(caminho_audio)
    try:
        modelo = _get_modelo()
        segmentos, info = modelo.transcribe(str(wav), language=idioma)
        texto = "".join(s.text for s in segmentos).strip()
    finally:
        try:
            wav.unlink()
        except OSError:
            pass

    return texto, info.duration


def transcrever_e_registrar(
    caminho_audio, usuario=None, paciente=None, consulta=None, idioma="pt"
):
    """Transcreve o audio e grava um RegistroAuditoriaIA com a sugestao gerada.

    A decisao fica como 'pendente' ate alguem revisar e aprovar o texto.
    """
    from .models import RegistroAuditoriaIA

    validar_duracao_audio(caminho_audio)
    texto, _duracao = transcrever_audio(caminho_audio, idioma=idioma)

    registro = RegistroAuditoriaIA.objects.create(
        usuario=usuario,
        paciente=paciente,
        consulta=consulta,
        recurso="transcricao_voz",
        modelo_utilizado=f"faster-whisper:{MODELO_WHISPER}",
        entrada_resumo=f"Audio: {caminho_audio}",
        saida_sugerida=texto,
        decisao="pendente",
    )

    return registro
