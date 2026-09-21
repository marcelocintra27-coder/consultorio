import base64
import json
import logging
import mimetypes
import os
import re

from anthropic import Anthropic

logger = logging.getLogger(__name__)

MODELO_VISAO = 'claude-sonnet-4-6'
TIPOS_IMAGEM = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
}

PROMPT_EXTRACAO = (
    'Você está lendo a foto de uma ficha odontológica em papel (português do Brasil). '
    'Extraia somente o que estiver visível na imagem. Responda APENAS com um JSON '
    'válido, sem markdown e sem texto fora do JSON, neste formato:\n'
    '{\n'
    '  "nome_paciente": {"valor": "", "incerto": false},\n'
    '  "data_nascimento": {"valor": "", "incerto": false},\n'
    '  "telefone": {"valor": "", "incerto": false},\n'
    '  "queixa_principal": {"valor": "", "incerto": false},\n'
    '  "medicamentos_em_uso": {"valor": "", "incerto": false},\n'
    '  "alergias": {"valor": "", "incerto": false},\n'
    '  "evolucoes": [\n'
    '    {"data": "", "descricao": "", "incerto": false}\n'
    '  ]\n'
    '}\n'
    'Regras:\n'
    '- Se um campo não aparecer ou você não tiver confiança na leitura, '
    'preencha "valor" com string vazia (ou omita a evolução) e marque '
    '"incerto": true.\n'
    '- "evolucoes" é uma lista de entradas de evolução clínica, cada uma com '
    'data e descrição.\n'
    '- Não invente dados. Não inclua comentários fora do JSON.'
)


def processar_digitalizacao_com_ia(digitalizacao):
    """Lê a imagem da digitalização com Claude e grava o JSON em texto_bruto_ia.

    Em caso de falha, registra o erro em log e em texto_bruto_ia, sem
    propagar a exceção. Retorna True se a extração foi salva; False se não.
    """
    try:
        chave = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        if not chave:
            raise RuntimeError('ANTHROPIC_API_KEY não está configurada.')

        if not digitalizacao.imagem:
            raise RuntimeError('A digitalização não tem imagem anexada.')

        from .digitalizacao_uploads import validar_imagem
        with digitalizacao.imagem.open('rb') as arquivo:
            bytes_imagem, media_type = validar_imagem(arquivo, digitalizacao.imagem.name)

        cliente = Anthropic(api_key=chave)
        resposta = cliente.messages.create(
            model=MODELO_VISAO,
            max_tokens=4096,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': media_type,
                                'data': base64.standard_b64encode(
                                    bytes_imagem
                                ).decode('ascii'),
                            },
                        },
                        {'type': 'text', 'text': PROMPT_EXTRACAO},
                    ],
                }
            ],
        )
        texto = _texto_da_resposta(resposta)
        dados = _json_da_resposta(texto)
        digitalizacao.texto_bruto_ia = dados
        digitalizacao.save(update_fields=['texto_bruto_ia'])
        return True
    except Exception:
        logger.exception(
            'Falha ao processar digitalização %s com IA.',
            getattr(digitalizacao, 'pk', None),
        )
        try:
            digitalizacao.texto_bruto_ia = {
                'erro': True,
                'mensagem': 'Não foi possível ler a ficha com a IA. '
                'Tente novamente ou revise o arquivo enviado.',
            }
            digitalizacao.save(update_fields=['texto_bruto_ia'])
        except Exception:
            logger.exception(
                'Também falhou gravar o erro na digitalização %s.',
                getattr(digitalizacao, 'pk', None),
            )
        return False


def _tipo_midia(digitalizacao):
    nome = getattr(digitalizacao.imagem, 'name', '') or ''
    content_type = getattr(digitalizacao.imagem, 'content_type', None)
    if content_type in TIPOS_IMAGEM:
        return content_type
    guess, _ = mimetypes.guess_type(nome)
    if guess in TIPOS_IMAGEM:
        return guess
    return guess or 'application/octet-stream'


def _texto_da_resposta(resposta):
    partes = []
    for bloco in getattr(resposta, 'content', []) or []:
        if getattr(bloco, 'type', None) == 'text':
            partes.append(bloco.text or '')
    return '\n'.join(partes).strip()


def _json_da_resposta(texto):
    if not texto:
        raise ValueError('A API não devolveu texto.')
    candidato = texto.strip()
    cerca = re.search(r'```(?:json)?\s*(\{.*\})\s*```', candidato, re.DOTALL)
    if cerca:
        candidato = cerca.group(1)
    else:
        inicio = candidato.find('{')
        fim = candidato.rfind('}')
        if inicio != -1 and fim != -1 and fim > inicio:
            candidato = candidato[inicio : fim + 1]
    return json.loads(candidato)
