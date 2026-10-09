"""Cópia dos arquivos guardados no disco (fotos, assinaturas, exames).

O export do banco não leva os arquivos. Esta tela entrega ao administrador
um .zip com tudo o que está no disco, para guardar fora do servidor junto
com o export semanal do banco.

O .zip é montado aos poucos e enviado enquanto é montado: nada é gravado
no disco do servidor (ele é pequeno) e a memória usada fica baixa.
"""
import logging
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .permissoes import exige_financeiro

logger = logging.getLogger(__name__)

TAMANHO_BLOCO = 1024 * 1024


def _pasta_exames():
    """Só os originais dos exames; a pasta de temporários fica de fora."""
    configurada = getattr(settings, 'EXAMES_ROOT', None)
    if not configurada:
        return None
    return Path(configurada) / 'originais'


def pastas_do_backup():
    """Pares (nome dentro do .zip, pasta no disco) que entram na cópia."""
    pastas = [('arquivos', Path(settings.MEDIA_ROOT))]
    exames = _pasta_exames()
    if exames is not None:
        pastas.append(('exames/originais', exames))
    return pastas


def listar_arquivos():
    """Lista (nome no .zip, caminho) de arquivos comuns, sem seguir atalhos."""
    itens = []
    for prefixo, pasta in pastas_do_backup():
        if not pasta.is_dir() or pasta.is_symlink():
            continue
        raiz = pasta.resolve()
        for caminho in sorted(pasta.rglob('*')):
            if caminho.is_symlink() or not caminho.is_file():
                continue
            if raiz not in caminho.resolve().parents:
                continue
            relativo = caminho.relative_to(pasta).as_posix()
            itens.append((f'{prefixo}/{relativo}', caminho))
    return itens


def resumo_arquivos():
    itens = listar_arquivos()
    total = 0
    for _, caminho in itens:
        try:
            total += caminho.stat().st_size
        except OSError:
            continue
    return len(itens), total


class _Saida:
    """Destino do zipfile que só acumula bytes para serem enviados."""

    def __init__(self):
        self._partes = []
        self._posicao = 0

    def write(self, dados):
        self._partes.append(bytes(dados))
        self._posicao += len(dados)
        return len(dados)

    def tell(self):
        return self._posicao

    def flush(self):
        pass

    def retirar(self):
        dados = b''.join(self._partes)
        self._partes = []
        return dados


def gerar_zip(itens):
    """Gera o .zip em pedaços. Fotos e PDFs já são comprimidos: só armazena."""
    saida = _Saida()
    with zipfile.ZipFile(saida, mode='w', compression=zipfile.ZIP_STORED) as arquivo_zip:
        for nome, caminho in itens:
            try:
                origem = caminho.open('rb')
            except OSError:
                logger.warning('Cópia dos arquivos: não foi possível ler %s', nome)
                continue
            with origem, arquivo_zip.open(nome, mode='w', force_zip64=True) as destino:
                while True:
                    bloco = origem.read(TAMANHO_BLOCO)
                    if not bloco:
                        break
                    destino.write(bloco)
                    pedaco = saida.retirar()
                    if pedaco:
                        yield pedaco
            pedaco = saida.retirar()
            if pedaco:
                yield pedaco
    pedaco = saida.retirar()
    if pedaco:
        yield pedaco


def _tamanho_legivel(total):
    if total < 1024 * 1024:
        return f'{max(total, 0) / 1024:.0f} KB'.replace('.', ',')
    if total < 1024 * 1024 * 1024:
        return f'{total / (1024 * 1024):.1f} MB'.replace('.', ',')
    return f'{total / (1024 * 1024 * 1024):.2f} GB'.replace('.', ',')


@never_cache
@require_http_methods(['GET', 'POST'])
@exige_financeiro
def backup_arquivos(request):
    if request.method == 'POST':
        itens = listar_arquivos()
        agora = timezone.localtime()
        nome = f'arquivos-consultorio-{agora:%Y-%m-%d}.zip'
        logger.info(
            'Cópia dos arquivos baixada por %s (%s arquivos).',
            request.user.get_username(), len(itens),
        )
        resposta = StreamingHttpResponse(gerar_zip(itens), content_type='application/zip')
        resposta['Content-Disposition'] = f'attachment; filename="{nome}"'
        resposta['X-Content-Type-Options'] = 'nosniff'
        return resposta

    quantidade, total = resumo_arquivos()
    return render(request, 'core/backup_arquivos.html', {
        'quantidade': quantidade,
        'tamanho': _tamanho_legivel(total),
    })
