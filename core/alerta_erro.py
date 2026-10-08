"""Aviso por e-mail quando o sistema dá erro (página com erro 500).

O e-mail é curto de propósito: não leva dados de paciente, valores digitados,
parâmetros da URL nem o texto da exceção (que pode conter dados). Leva só o
endereço da página, o tipo do erro e o arquivo/linha onde aconteceu. Os
detalhes completos ficam nos logs do Render.

Para não lotar a caixa de entrada, o mesmo erro na mesma página só gera um
e-mail a cada ALERTA_ERRO_INTERVALO_MINUTOS.
"""
import hashlib
import logging
import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins
from django.utils import timezone

INTERVALO_PADRAO_MINUTOS = 15


def _origem(exc_info):
    """Último ponto do código do projeto onde o erro passou (arquivo:linha)."""
    if not exc_info or not exc_info[2]:
        return 'desconhecida'
    quadros = traceback.extract_tb(exc_info[2])
    base = str(settings.BASE_DIR)
    do_projeto = [
        q for q in quadros
        if q.filename.startswith(base) and '/site-packages/' not in q.filename
    ]
    quadro = (do_projeto or quadros)[-1]
    arquivo = quadro.filename
    if arquivo.startswith(base):
        arquivo = arquivo[len(base):].lstrip('/\\')
    return f'{arquivo}:{quadro.lineno} ({quadro.name})'


def montar_alerta(record):
    """Devolve (assunto, corpo) sem dados pessoais."""
    request = getattr(record, 'request', None)
    caminho = getattr(request, 'path', '') or '(sem página)'
    metodo = getattr(request, 'method', '') or ''
    tipo = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else 'Erro'
    status = getattr(record, 'status_code', None) or 500
    agora = timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')
    origem = _origem(record.exc_info)
    assunto = f'Erro {status} em {caminho}'
    corpo = (
        'O sistema do consultório teve um erro.\n\n'
        f'Quando: {agora}\n'
        f'Página: {metodo} {caminho}\n'
        f'Tipo do erro: {tipo}\n'
        f'Onde no código: {origem}\n\n'
        'Os detalhes completos estão nos Logs do serviço no Render '
        '(procure pelo horário acima).\n'
        'Este e-mail não contém dados de pacientes.\n'
    )
    return assunto, corpo


class AlertaErroEmailHandler(logging.Handler):
    """Manda um e-mail curto aos ADMINS quando acontece erro 500."""

    def emit(self, record):
        try:
            if not getattr(settings, 'ADMINS', None):
                return
            assunto, corpo = montar_alerta(record)
            chave = 'alerta_erro:' + hashlib.sha256(assunto.encode()).hexdigest()[:32]
            minutos = getattr(
                settings, 'ALERTA_ERRO_INTERVALO_MINUTOS', INTERVALO_PADRAO_MINUTOS
            )
            if not cache.add(chave, 1, timeout=minutos * 60):
                return
            mail_admins(assunto, corpo, fail_silently=True)
        except Exception:  # o aviso nunca pode derrubar o sistema
            pass
