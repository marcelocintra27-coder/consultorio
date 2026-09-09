import json

TEXTO_AVISO_MULTIPLOS_PROFISSIONAIS = (
    'O atendimento neste consultório pode ser realizado por mais de um '
    'cirurgião-dentista, conforme a especialidade e a etapa do tratamento. '
    'Os profissionais responsáveis por cada procedimento estão indicados '
    'neste documento.'
)

TEXTO_DECLARACAO_PLANO = (
    'Declaro que as informações acima me foram prestadas, que tive '
    'oportunidade de esclarecer dúvidas e que compreendi o tratamento '
    'proposto, as alternativas, os riscos, as limitações e as orientações '
    'de cuidados, manutenção e custos. Dou meu consentimento de forma '
    'livre e esclarecida.'
)

CIENCIA_ITENS = [
    ('diagnostico', 'diagnóstico e situação atual'),
    (
        'tratamento',
        'tratamento proposto, objetivos, etapas e duração',
    ),
    (
        'alternativas',
        'alternativas de tratamento, incluindo não realizar o tratamento',
    ),
    ('beneficios', 'benefícios e limitações'),
    (
        'riscos',
        'possíveis riscos, complicações e efeitos adversos',
    ),
    (
        'cuidados',
        'necessidade de cuidados, manutenção e acompanhamento',
    ),
    (
        'custos',
        'custos, forma de pagamento e política de cancelamento',
    ),
]

COMPLEXIDADE_ITENS = [
    ('cirurgias', 'cirurgias'),
    ('sedacao', 'sedação'),
    ('especiais', 'outros procedimentos especiais'),
    ('endodontia', 'tratamento endodôntico'),
    ('ortodontia', 'ortodontia'),
    ('implantes', 'implantes e cirurgias de implantodontia'),
    ('lentes', 'lentes de contato / facetas'),
]


def _data_iso(valor):
    if valor is None:
        return ''
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()
    return str(valor)


def texto_para_hash_plano(ficha):
    itens = []
    for item in ficha.itens.all().order_by('ordem', 'pk'):
        itens.append(
            {
                'cro': item.cro,
                'dentistas': sorted(item.dentistas.values_list('pk', flat=True)),
                'descricao': item.descricao,
                'id': item.pk,
                'procedimento': item.procedimento,
            }
        )
    profissionais = []
    for item in ficha.profissionais.all().order_by('ordem', 'pk'):
        profissionais.append(
            {
                'cro': item.cro,
                'id': item.pk,
                'nome': item.nome,
            }
        )
    payload = {
        'aceitou_declaracao': bool(ficha.aceitou_declaracao),
        'aviso': TEXTO_AVISO_MULTIPLOS_PROFISSIONAIS,
        'ciencia_itens': sorted(ficha.ciencia_itens or []),
        'cidade': ficha.cidade,
        'complexidade_itens': sorted(ficha.complexidade_itens or []),
        'cpf': ficha.cpf,
        'data_consentimento': _data_iso(ficha.data_consentimento),
        'data_nascimento': _data_iso(ficha.data_nascimento),
        'declaracao': TEXTO_DECLARACAO_PLANO,
        'email': ficha.email,
        'endereco': ficha.endereco,
        'itens': itens,
        'local_assinatura': ficha.local_assinatura,
        'nome_completo': ficha.nome_completo,
        'nome_responsavel': ficha.nome_responsavel,
        'paciente_id': ficha.paciente_id,
        'plano_tratamento': ficha.plano_tratamento,
        'profissionais': profissionais,
        'profissao': ficha.profissao,
        'telefone': ficha.telefone,
        'uf': ficha.uf,
        'whatsapp': ficha.whatsapp,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
