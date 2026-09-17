"""Serializador exclusivo do novo documento; não altera hashes anteriores."""
import json


def texto_para_hash_prescricao(ficha):
    itens = list(ficha.itens.order_by('ordem', 'pk').values(
        'id', 'ordem', 'medicamento', 'concentracao_apresentacao',
        'quantidade', 'posologia', 'via', 'duracao', 'orientacoes',
    ))
    return json.dumps({
        'paciente_id': ficha.paciente_id,
        'nome_paciente': ficha.nome_paciente,
        'cpf_paciente': ficha.cpf_paciente,
        'data_nascimento_paciente': ficha.data_nascimento_paciente.isoformat() if ficha.data_nascimento_paciente else '',
        'dentista_id': ficha.dentista_id,
        'autor_id': ficha.criado_por_id,
        'nome_profissional': ficha.nome_profissional,
        'cro': ficha.cro,
        'emitida_em': ficha.emitida_em.isoformat() if ficha.emitida_em else '',
        'texto_livre': ficha.texto_livre,
        'orientacoes': ficha.orientacoes,
        'itens': itens,
    }, ensure_ascii=False, sort_keys=True)
