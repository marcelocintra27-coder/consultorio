import json
from decimal import Decimal

TIPOS_QUE_EXIGEM_DESCRICAO = frozenset({'outros_exames', 'outros'})

TEXTO_DECLARACAO_AUTORIZACAO = (
    'Declaro que fui informado(a) sobre os itens abaixo, inclusive quando '
    'houver cobrança, e autorizo a realização e o lançamento desses itens '
    'no meu atendimento.'
)


def _data_iso(valor):
    if valor is None:
        return ''
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()
    return str(valor)


def _valor_texto(valor):
    if valor is None:
        return ''
    return str(Decimal(valor).quantize(Decimal('0.01')))


def texto_para_hash_autorizacao(ficha):
    itens = []
    for item in ficha.itens.all().order_by('ordem', 'pk'):
        itens.append(
            {
                'descricao': item.descricao,
                'id': item.pk,
                'quantidade': item.quantidade,
                'tipo': item.tipo,
                'valor': _valor_texto(item.valor),
            }
        )
    payload = {
        'aceitou_declaracao': bool(ficha.aceitou_declaracao),
        'consulta_id': ficha.consulta_id,
        'cpf': ficha.cpf,
        'data_nascimento': _data_iso(ficha.data_nascimento),
        'declaracao': TEXTO_DECLARACAO_AUTORIZACAO,
        'itens': itens,
        'nome_completo': ficha.nome_completo,
        'nome_responsavel': ficha.nome_responsavel,
        'paciente_id': ficha.paciente_id,
        'solicitado_por_id': ficha.solicitado_por_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
