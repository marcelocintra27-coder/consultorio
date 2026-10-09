import json
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

TEXTO_DECLARACAO_ANAMNESE = (
    'Declaro que as informações acima são verdadeiras e completas conforme '
    'meu conhecimento. Comprometo-me a informar ao cirurgião-dentista qualquer '
    'alteração relevante no meu estado de saúde, uso de medicamentos ou alergias.'
)

PRAZO_LINK_DIAS = 14

UFS = [
    ('AC', 'AC'),
    ('AL', 'AL'),
    ('AP', 'AP'),
    ('AM', 'AM'),
    ('BA', 'BA'),
    ('CE', 'CE'),
    ('DF', 'DF'),
    ('ES', 'ES'),
    ('GO', 'GO'),
    ('MA', 'MA'),
    ('MT', 'MT'),
    ('MS', 'MS'),
    ('MG', 'MG'),
    ('PA', 'PA'),
    ('PB', 'PB'),
    ('PR', 'PR'),
    ('PE', 'PE'),
    ('PI', 'PI'),
    ('RJ', 'RJ'),
    ('RN', 'RN'),
    ('RS', 'RS'),
    ('RO', 'RO'),
    ('RR', 'RR'),
    ('SC', 'SC'),
    ('SP', 'SP'),
    ('SE', 'SE'),
    ('TO', 'TO'),
]

SAUDE_CONDICOES = [
    ('pressao_alta', 'pressão alta'),
    ('diabetes', 'diabetes'),
    ('problemas_cardiacos', 'problemas cardíacos'),
    ('respiratorios', 'problemas respiratórios'),
    ('renais_hepaticos', 'problemas renais ou hepáticos'),
    ('coagulacao', 'problemas de coagulação'),
    ('osteoporose', 'osteoporose'),
    ('convulsoes', 'convulsões / epilepsia'),
    ('autoimune', 'doença autoimune'),
    ('cancer', 'câncer'),
    ('outra', 'outra'),
    ('nenhuma', 'nenhuma'),
]

SAUDE_BUCAL = [
    ('dor', 'dor'),
    ('sensibilidade', 'sensibilidade'),
    ('sangramento_gengiva', 'sangramento na gengiva'),
    ('mau_halito', 'mau hálito'),
    ('dor_mastigar', 'dor ao mastigar'),
    ('dente_quebrado', 'dente quebrado'),
    ('dente_solto', 'dente solto'),
    ('ferida_boca', 'ferida na boca'),
    ('bruxismo', 'bruxismo / apertamento'),
    ('estalos_mandibula', 'estalos / travamento da mandíbula'),
    ('dor_cabeca_face', 'dor de cabeça / face'),
    ('nenhuma', 'nenhuma'),
]


# Anamnese de harmonização orofacial (HOF). As chaves ficam gravadas na ficha;
# mudar uma chave depois quebra a leitura das fichas antigas.
SAUDE_CONDICOES_HOF = [
    ('hipertensao', 'hipertensão'),
    ('diabetes', 'diabetes'),
    ('doenca_cardiaca', 'doença cardíaca'),
    ('autoimune', 'doença autoimune'),
    ('coagulacao', 'distúrbio de coagulação'),
    ('neuromuscular', 'doença neuromuscular'),
    ('hepatica_renal', 'doença hepática / renal'),
    ('cancer', 'histórico de câncer'),
    ('herpes', 'herpes recorrente'),
    ('infeccao_ativa', 'infecção ativa'),
    ('cicatrizacao', 'cicatrização alterada / queloide'),
    ('nenhuma', 'nenhuma das anteriores'),
]

SITUACOES_HOF = [
    ('gestante_lactante', 'gestante / lactante'),
    ('infeccao_facial', 'infecção odontológica / facial'),
    ('bruxismo', 'bruxismo / apertamento'),
    ('paralisia_facial', 'paralisia facial prévia'),
    ('reacao_injetaveis', 'reação a injetáveis / desmaios'),
    ('vacina_infeccao_recente', 'vacinação ou infecção recente'),
    ('nenhuma', 'nenhuma'),
]

PROCEDIMENTOS_HOF = [
    ('toxina', 'toxina botulínica'),
    ('acido_hialuronico', 'ácido hialurônico'),
    ('bioestimulador', 'bioestimulador'),
    ('fios', 'fios de sustentação'),
    ('laser_peeling', 'laser / peeling'),
    ('pmma', 'preenchimento permanente / PMMA'),
    ('cirurgia_facial', 'cirurgia facial'),
    ('nenhuma', 'nenhum procedimento'),
]


# Mesma condição de saúde com chave diferente em cada tipo de ficha.
_SAUDE_ODONTO_PARA_HOF = {
    'pressao_alta': 'hipertensao',
    'diabetes': 'diabetes',
    'problemas_cardiacos': 'doenca_cardiaca',
    'autoimune': 'autoimune',
    'coagulacao': 'coagulacao',
    'renais_hepaticos': 'hepatica_renal',
    'cancer': 'cancer',
}
_SAUDE_HOF_PARA_ODONTO = {hof: odonto for odonto, hof in _SAUDE_ODONTO_PARA_HOF.items()}

CAMPOS_COMUNS_ANAMNESE = (
    'cidade', 'uf', 'profissao', 'nome_responsavel',
    'alergia', 'alergia_qual', 'usa_medicamento', 'medicamento_nome', 'fuma',
)


def _ficha_base(paciente, excluir_pk=None):
    """Ficha de onde copiar respostas: a última assinada; se não houver,
    a última em preenchimento que já tenha alguma resposta."""
    from .models import FichaCadastroAnamnese

    fichas = FichaCadastroAnamnese.objects.filter(paciente=paciente)
    if excluir_pk:
        fichas = fichas.exclude(pk=excluir_pk)
    rascunho = FichaCadastroAnamnese.Status.RASCUNHO
    assinada = fichas.exclude(status=rascunho).order_by('-criado_em', '-pk').first()
    if assinada:
        return assinada
    for ficha in fichas.filter(status=rascunho).order_by('-atualizado_em', '-pk'):
        if ficha.saude_condicoes or any(
            getattr(ficha, campo) for campo in CAMPOS_COMUNS_ANAMNESE
        ):
            return ficha
    return None


def dados_da_ficha_anterior(paciente, tipo, excluir_pk=None):
    """Respostas de outra ficha do paciente, para não perguntar tudo de novo.

    Vale entre os dois tipos (odontológica e HOF). O paciente revisa e assina;
    nada da ficha de origem é alterado.
    """
    anterior = _ficha_base(paciente, excluir_pk)
    if anterior is None:
        return {}
    dados = {campo: getattr(anterior, campo) for campo in CAMPOS_COMUNS_ANAMNESE}
    condicoes = list(anterior.saude_condicoes or [])
    if anterior.tipo == tipo:
        dados['saude_condicoes'] = condicoes
    else:
        mapa = _SAUDE_ODONTO_PARA_HOF if tipo == 'hof' else _SAUDE_HOF_PARA_ODONTO
        dados['saude_condicoes'] = [mapa[c] for c in condicoes if c in mapa]

    # Bruxismo e gravidez ficam em perguntas diferentes em cada ficha.
    if anterior.tipo == 'hof':
        situacoes = set(anterior.hof_situacoes or [])
        bruxismo = 'bruxismo' in situacoes
        gestante = 'gestante_lactante' in situacoes
    else:
        bruxismo = (
            anterior.range_dentes == 'sim'
            or 'bruxismo' in (anterior.saude_bucal or [])
        )
        gestante = anterior.gravidez == 'sim'
    if tipo == 'hof':
        dados['hof_situacoes'] = [
            chave for chave, marcado in (
                ('gestante_lactante', gestante), ('bruxismo', bruxismo),
            ) if marcado
        ]
    elif bruxismo:
        # "Gestante / lactante" da HOF não vira gravidez na odontológica:
        # lactante não é gestante, então a paciente responde de novo.
        dados['range_dentes'] = 'sim'
    return dados


def completar_rascunho(ficha):
    """Preenche, só na tela, os campos vazios de um rascunho com as respostas
    de outra ficha. Não grava nada: vale quando a equipe ou o paciente salvar."""
    if ficha.status != ficha.Status.RASCUNHO:
        return ficha
    dados = dados_da_ficha_anterior(ficha.paciente, ficha.tipo, excluir_pk=ficha.pk)
    for campo, valor in dados.items():
        if not getattr(ficha, campo) and valor:
            setattr(ficha, campo, valor)
    return ficha


def idade_em_anos(data_nascimento, hoje=None):
    if data_nascimento is None:
        return None
    hoje = hoje or timezone.localdate()
    anos = hoje.year - data_nascimento.year
    if (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day):
        anos -= 1
    return anos


def eh_menor_de_idade(data_nascimento, hoje=None):
    anos = idade_em_anos(data_nascimento, hoje)
    return anos is not None and anos < 18


def renovar_token(ficha):
    ficha.token = uuid4()
    ficha.token_expira_em = timezone.now() + timedelta(days=PRAZO_LINK_DIAS)
    ficha.save(update_fields=['token', 'token_expira_em'])
    return ficha


def sincronizar_paciente(ficha):
    paciente = ficha.paciente
    paciente.nome_completo = ficha.nome_completo
    paciente.cpf = ficha.cpf
    paciente.data_nascimento = ficha.data_nascimento
    paciente.telefone = ficha.telefone
    paciente.whatsapp = ficha.whatsapp
    paciente.email = ficha.email
    paciente.endereco = ficha.endereco
    paciente.save(
        update_fields=[
            'nome_completo',
            'cpf',
            'data_nascimento',
            'telefone',
            'whatsapp',
            'email',
            'endereco',
        ]
    )


def _data_iso(valor):
    if valor is None:
        return ''
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()
    return str(valor)


def rotulos_checklist(valores, opcoes):
    mapa = dict(opcoes)
    return [mapa.get(item, item) for item in (valores or [])]


def texto_para_hash(ficha):
    payload = {
        'aceitou_declaracao': bool(ficha.aceitou_declaracao),
        'alergia': ficha.alergia,
        'alergia_qual': ficha.alergia_qual,
        'bebida_alcoolica': ficha.bebida_alcoolica,
        'cidade': ficha.cidade,
        'cirurgia_qual': ficha.cirurgia_qual,
        'cirurgia_recente': ficha.cirurgia_recente,
        'cpf': ficha.cpf,
        'data_nascimento': _data_iso(ficha.data_nascimento),
        'data_ultima_consulta': _data_iso(ficha.data_ultima_consulta),
        'declaracao': TEXTO_DECLARACAO_ANAMNESE,
        'email': ficha.email,
        'endereco': ficha.endereco,
        'experiencia_anterior': ficha.experiencia_anterior,
        'experiencia_relato': ficha.experiencia_relato,
        'fuma': ficha.fuma,
        'gravidez': ficha.gravidez,
        'medicamento_nome': ficha.medicamento_nome,
        'nome_completo': ficha.nome_completo,
        'nome_responsavel': ficha.nome_responsavel,
        'o_que_espera': ficha.o_que_espera,
        'o_que_incomoda': ficha.o_que_incomoda,
        'outra_info_relato': ficha.outra_info_relato,
        'outra_info_saude': ficha.outra_info_saude,
        'paciente_id': ficha.paciente_id,
        'profissao': ficha.profissao,
        'range_dentes': ficha.range_dentes,
        'saude_bucal': sorted(ficha.saude_bucal or []),
        'saude_condicoes': sorted(ficha.saude_condicoes or []),
        'saude_outra_texto': ficha.saude_outra_texto,
        'telefone': ficha.telefone,
        'uf': ficha.uf,
        'usa_medicamento': ficha.usa_medicamento,
        'whatsapp': ficha.whatsapp,
    }
    # A ficha odontológica mantém exatamente o conteúdo de antes, para as
    # assinaturas já gravadas continuarem conferindo. Só a HOF ganha campos.
    if ficha.tipo == 'hof':
        payload.update({
            'tipo': ficha.tipo,
            'hof_intercorrencias': ficha.hof_intercorrencias,
            'hof_procedimentos': sorted(ficha.hof_procedimentos or []),
            'hof_situacoes': sorted(ficha.hof_situacoes or []),
            'hof_situacoes_detalhes': ficha.hof_situacoes_detalhes,
            'hof_ultimo_procedimento': ficha.hof_ultimo_procedimento,
            'isotretinoina': ficha.isotretinoina,
            'isotretinoina_quando': ficha.isotretinoina_quando,
        })
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
