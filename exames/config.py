import os
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def limite(nome, padrao):
    valor = int(getattr(settings, nome, os.environ.get(nome, padrao)))
    if valor <= 0:
        raise ImproperlyConfigured(f'{nome} deve ser positivo.')
    return valor


def raiz():
    configurada = getattr(settings, 'EXAMES_ROOT', os.environ.get('EXAMES_ROOT'))
    if getattr(settings, 'EM_PRODUCAO', False) and not configurada:
        raise ImproperlyConfigured('Armazenamento privado de exames não configurado.')
    pasta = Path(configurada or settings.BASE_DIR / 'private_exames').resolve()
    for publico in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
        publico = Path(publico).resolve()
        if pasta == publico or publico in pasta.parents or pasta in publico.parents:
            raise ImproperlyConfigured('Exames exigem diretório privado separado da mídia pública.')
    return pasta
