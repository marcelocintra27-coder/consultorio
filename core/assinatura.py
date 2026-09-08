import base64
import hashlib
import re
from uuid import uuid4

from django.core.files.base import ContentFile

from .models import AssinaturaEletronica

_DATA_URL = re.compile(
    r'^data:image/png;base64,([A-Za-z0-9+/=\s]+)$',
    re.IGNORECASE,
)


def hash_sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def png_de_data_url(data_url: str) -> bytes:
    bruto = (data_url or '').strip()
    match = _DATA_URL.match(bruto)
    if not match:
        raise ValueError('Assinatura inválida. Desenhe no quadro e tente de novo.')
    try:
        png = base64.b64decode(match.group(1))
    except (ValueError, TypeError) as exc:
        raise ValueError('Não foi possível ler a imagem da assinatura.') from exc
    if len(png) < 32 or len(png) > 800_000:
        raise ValueError('A assinatura está vazia ou grande demais.')
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('A imagem da assinatura precisa ser PNG.')
    return png


def gravar_assinatura_manuscrita(
    *,
    tipo_documento,
    documento_id,
    papel,
    nome_assinante,
    imagem_data_url,
    conteudo_para_hash,
    paciente=None,
    cpf_assinante='',
    usuario=None,
    ip=None,
    user_agent='',
):
    png = png_de_data_url(imagem_data_url)
    assinatura = AssinaturaEletronica(
        tipo_documento=tipo_documento,
        documento_id=documento_id or 0,
        paciente=paciente,
        papel=papel,
        tipo_assinatura=AssinaturaEletronica.TipoAssinatura.MANUSCRITA,
        nome_assinante=nome_assinante,
        cpf_assinante=cpf_assinante or '',
        usuario=usuario,
        ip=ip,
        user_agent=(user_agent or '')[:400],
        hash_conteudo=hash_sha256(conteudo_para_hash.encode('utf-8')),
        hash_imagem=hash_sha256(png),
        status_verificacao=AssinaturaEletronica.StatusVerificacao.NAO_APLICAVEL,
    )
    nome_arquivo = f'{uuid4().hex}.png'
    assinatura.imagem.save(nome_arquivo, ContentFile(png), save=True)
    return assinatura
