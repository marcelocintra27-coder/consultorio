"""Quem aluga de quem: a relação entre titulares (donas de sala) e locatárias.

Uma consulta só ao banco para a tela inteira, em vez de uma por dentista.
"""
from .models import Dentista, TurnoLocacao


def relacoes_de_locacao():
    """Devolve (alugueis_por_titular, donas_por_locataria).

    alugueis_por_titular: {pk da titular: [{'locataria', 'texto'}]}
    donas_por_locataria: {pk da locatária: [titulares, sem repetir]}
    """
    titular_da_sala = {
        dentista.sala_id: dentista
        for dentista in Dentista.objects.filter(
            ativo=True, tipo=Dentista.Tipo.TITULAR, sala__isnull=False,
        )
    }
    turnos = (
        TurnoLocacao.objects.filter(ativo=True, dentista__ativo=True)
        .select_related('dentista', 'sala')
        .order_by('dentista__nome_completo', 'dia_semana', 'hora_inicio')
    )
    por_titular = {}
    donas = {}
    for turno in turnos:
        titular = titular_da_sala.get(turno.sala_id)
        if titular is None:
            continue
        grupos = por_titular.setdefault(titular.pk, {})
        grupo = grupos.setdefault(turno.dentista_id, {'locataria': turno.dentista, 'partes': []})
        grupo['partes'].append(turno.rotulo_curto())
        lista = donas.setdefault(turno.dentista_id, [])
        if titular not in lista:
            lista.append(titular)
    alugueis = {
        pk: [
            {'locataria': grupo['locataria'], 'texto': '; '.join(grupo['partes'])}
            for grupo in grupos.values()
        ]
        for pk, grupos in por_titular.items()
    }
    return alugueis, donas


def rotulo_sala(sala, titular_da_sala):
    """'Sala Dra. Adriana — da Dra. Adriana', para escolher a sala do turno."""
    titular = titular_da_sala.get(sala.pk)
    if titular is None:
        return f'{sala} — sem titular'
    return f'{sala} — da {titular.nome_completo}'
