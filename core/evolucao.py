import json


def texto_para_hash_evolucao(registro):
    payload = {
        'cro': registro.cro,
        'data': registro.data.isoformat() if registro.data else '',
        'descricao_clinica': registro.descricao_clinica,
        'nome_profissional': registro.nome_profissional,
        'orientacoes': registro.orientacoes,
        'paciente_id': registro.paciente_id,
        'procedimento_etapa': registro.procedimento_etapa,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
