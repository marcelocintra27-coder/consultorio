"""Recebimento e validação restritos à digitalização de fichas."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload

from exames import antivirus

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
VALIDATION_TIMEOUT = 15
TIPOS = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
         '.gif': 'image/gif', '.webp': 'image/webp'}


class UploadDigitalizacao(FileUploadHandler):
    """Um arquivo limitado desde o recebimento, removido ao terminar a requisição."""
    def __init__(self, request):
        super().__init__(request)
        self.temporarios = []
        self.quantidade = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.quantidade += 1
        if self.quantidade != 1 or self.field_name != 'imagem':
            self.request.digitalizacao_upload_erro = True
            raise StopUpload(connection_reset=False)
        self.arquivo = tempfile.NamedTemporaryFile(
            mode='w+b', prefix='digitalizacao-', dir=settings.FILE_UPLOAD_TEMP_DIR,
            delete=False)
        self.temporarios.append(self.arquivo)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > MAX_BYTES:
            self.request.digitalizacao_upload_erro = True
            raise StopUpload(connection_reset=False)
        self.arquivo.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.arquivo.flush()
        self.arquivo.seek(0)
        return UploadedFile(self.arquivo, self.file_name, self.content_type, file_size)

    def fechar(self):
        for arquivo in self.temporarios:
            try:
                arquivo.close()
            finally:
                Path(arquivo.name).unlink(missing_ok=True)


def validar_imagem(arquivo, nome):
    """Valida uma cópia limitada e retorna exatamente os bytes inspecionados."""
    extensao = Path(nome).suffix.lower()
    if extensao not in TIPOS:
        raise ValidationError('Envie uma imagem JPEG, PNG, GIF ou WebP estática.')
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w+b', prefix='validacao-digitalizacao-',
                dir=settings.FILE_UPLOAD_TEMP_DIR, delete=False) as copia:
            temporario = Path(copia.name)
            arquivo.seek(0)
            total = 0
            while bloco := arquivo.read(65536):
                total += len(bloco)
                if total > MAX_BYTES:
                    raise ValidationError('A imagem deve ter até 20 MiB.')
                copia.write(bloco)
            if not total:
                raise ValidationError('A imagem está vazia.')
            copia.flush()
        resultado = subprocess.run(
            [sys.executable, '-B', str(Path(__file__).with_name('digitalizacao_worker.py')),
             str(temporario), extensao, str(MAX_PIXELS)],
            capture_output=True, timeout=VALIDATION_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        dados = json.loads(resultado.stdout)
        if resultado.returncode or dados.get('tipo') != TIPOS[extensao]:
            raise ValidationError('Imagem inválida, animada ou acima dos limites.')
        with temporario.open('rb') as copia:
            if antivirus.inspecionar(copia) != 'liberado':
                raise ValidationError('Imagem não liberada pela inspeção de segurança.')
            copia.seek(0)
            return copia.read(), dados['tipo']
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ValidationError('Não foi possível validar a imagem com segurança.') from exc
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
