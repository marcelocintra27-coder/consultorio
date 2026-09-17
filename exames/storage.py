import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from django.core.exceptions import ValidationError
from .config import raiz, limite


def pasta_privada(nome):
    pasta = raiz() / nome
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    if pasta.is_symlink() or pasta.resolve().parent != raiz():
        raise ValidationError('Armazenamento privado inválido.')
    return pasta


def caminho(chave):
    import uuid
    return pasta_privada('originais') / (str(uuid.UUID(str(chave))) + '.bin')


def conferir_espaco(tamanho):
    livre = shutil.disk_usage(pasta_privada('originais')).free
    if livre < tamanho + limite('EXAMES_RESERVA_BYTES', 100 * 1024 * 1024):
        raise ValidationError('Espaço insuficiente para receber o arquivo com segurança.')


def validar_arquivo(upload):
    extensao = Path(upload.name).suffix.lower()
    if extensao not in ('.jpg', '.jpeg', '.png', '.pdf') or not 0 < upload.size <= limite('EXAMES_MAX_BYTES', 20 * 1024 * 1024):
        raise ValidationError('Envie JPEG, PNG ou PDF, não vazio, com até 20 MiB.')
    try:
        resultado = subprocess.run(
            [sys.executable, '-B', str(Path(__file__).with_name('worker.py')), upload.file.name, extensao,
             str(limite('EXAMES_MAX_PIXELS', 40000000)), str(limite('EXAMES_MAX_PAGES', 100))],
            capture_output=True, timeout=limite('EXAMES_VALIDATION_TIMEOUT', 15),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        dados = json.loads(resultado.stdout)
        if resultado.returncode or dados.get('tipo') not in ('image/png', 'image/jpeg', 'application/pdf'):
            raise ValueError
        return dados['tipo']
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ValidationError('Arquivo inválido, conteúdo não permitido ou limite de processamento excedido.')


def gravar(upload, chave):
    conferir_espaco(upload.size)
    destino = caminho(chave)
    resumo = hashlib.sha256()
    criado = False
    try:
        with destino.open('xb') as saida:
            criado = True
            os.chmod(destino, 0o600)
            upload.seek(0)
            total = 0
            for bloco in upload.chunks():
                total += len(bloco)
                if total > limite('EXAMES_MAX_BYTES', 20 * 1024 * 1024):
                    raise ValidationError('Arquivo excede o limite.')
                resumo.update(bloco)
                saida.write(bloco)
            if total != upload.size:
                raise ValidationError('Recebimento incompleto.')
            saida.flush()
            os.fsync(saida.fileno())
        return resumo.hexdigest()
    except Exception:
        if criado:
            destino.unlink(missing_ok=True)
        raise


def abrir_verificado(exame):
    alvo = caminho(exame.chave)
    if alvo.is_symlink():
        raise ValidationError('Integridade indisponível.')
    try:
        arquivo = alvo.open('rb')
    except OSError:
        raise ValidationError('Arquivo ausente ou indisponível.')
    try:
        resumo = hashlib.sha256()
        total = 0
        while bloco := arquivo.read(65536):
            total += len(bloco)
            if total > exame.tamanho:
                raise ValidationError('Integridade comprometida.')
            resumo.update(bloco)
        if total != exame.tamanho or resumo.hexdigest() != exame.sha256:
            raise ValidationError('Integridade comprometida.')
        arquivo.seek(0)
        return arquivo
    except Exception:
        arquivo.close()
        raise
