from collections import defaultdict
from decimal import Decimal

from .models import Despesa, Dentista, DividaAvulsa, PagamentoPar, arredondar_dinheiro, primeiro_dia_mes


def mes_anterior(mes):
    if mes.month == 1:
        return mes.replace(year=mes.year - 1, month=12)
    return mes.replace(month=mes.month - 1)


def mes_seguinte(mes):
    if mes.month == 12:
        return mes.replace(year=mes.year + 1, month=1)
    return mes.replace(month=mes.month + 1)


def calcular_acerto_mensal(mes):
    """Calcula o acerto financeiro entre dentistas para o mês (competência) informado.

    Débitos considerados: cota de despesas compartilhadas (rateada entre as
    dentistas ativas) e dívidas avulsas do mês. Despesas individuais entram
    só como informação, sem gerar débito entre dentistas.
    """
    mes = primeiro_dia_mes(mes)

    dentistas_ativas = list(Dentista.objects.filter(ativo=True).order_by('nome_completo'))
    dentistas_por_id = {d.id: d for d in dentistas_ativas}

    despesas_compartilhadas = list(
        Despesa.objects.filter(
            competencia=mes, tipo=Despesa.Tipo.COMPARTILHADA
        ).select_related('pago_por').order_by('descricao')
    )
    despesas_individuais = list(
        Despesa.objects.filter(
            competencia=mes, tipo=Despesa.Tipo.INDIVIDUAL
        ).select_related('pago_por').order_by('pago_por__nome_completo', 'descricao')
    )
    dividas = list(
        DividaAvulsa.objects.filter(competencia=mes)
        .select_related('de_dentista', 'para_dentista')
        .order_by('descricao')
    )

    for divida in dividas:
        dentistas_por_id.setdefault(divida.de_dentista_id, divida.de_dentista)
        dentistas_por_id.setdefault(divida.para_dentista_id, divida.para_dentista)

    # saldo[(id_menor, id_maior)] > 0: id_menor deve a id_maior; < 0: o inverso.
    saldo = defaultdict(Decimal)

    def registrar_debito(devedor_id, credor_id, valor):
        if devedor_id == credor_id or not valor:
            return
        menor, maior = sorted((devedor_id, credor_id))
        sinal = Decimal('1') if devedor_id == menor else Decimal('-1')
        saldo[(menor, maior)] += sinal * valor

    for despesa in despesas_compartilhadas:
        cota = despesa.valor_cota()
        for dentista in dentistas_ativas:
            registrar_debito(dentista.id, despesa.pago_por_id, cota)

    for divida in dividas:
        registrar_debito(divida.de_dentista_id, divida.para_dentista_id, divida.valor)

    pagamentos_existentes = {
        (p.de_dentista_id, p.para_dentista_id): p
        for p in PagamentoPar.objects.filter(competencia=mes)
    }

    pares = []
    for (menor_id, maior_id), valor in saldo.items():
        if valor == 0:
            continue
        if valor > 0:
            devedor_id, credor_id = menor_id, maior_id
        else:
            devedor_id, credor_id = maior_id, menor_id
        valor_calculado = arredondar_dinheiro(abs(valor))

        pagamento = pagamentos_existentes.get((devedor_id, credor_id))
        pago = bool(pagamento and pagamento.pago)
        valor_exibido = (
            pagamento.valor
            if pago and pagamento.valor is not None
            else valor_calculado
        )

        pares.append({
            'devedor': dentistas_por_id[devedor_id],
            'credor': dentistas_por_id[credor_id],
            'valor_calculado': valor_calculado,
            'valor': valor_exibido,
            'pago': pago,
            'pagamento': pagamento,
        })

    pares.sort(key=lambda p: (p['devedor'].nome_completo, p['credor'].nome_completo))

    despesas_individuais_por_dentista = defaultdict(Decimal)
    for despesa in despesas_individuais:
        despesas_individuais_por_dentista[despesa.pago_por_id] += despesa.valor

    resumo = []
    for dentista in dentistas_ativas:
        a_receber = sum(
            (p['valor'] for p in pares if p['credor'].id == dentista.id),
            Decimal('0.00'),
        )
        a_pagar = sum(
            (p['valor'] for p in pares if p['devedor'].id == dentista.id),
            Decimal('0.00'),
        )
        resumo.append({
            'dentista': dentista,
            'a_receber': a_receber,
            'a_pagar': a_pagar,
            'saldo': a_receber - a_pagar,
            'despesas_individuais': despesas_individuais_por_dentista.get(dentista.id, Decimal('0.00')),
        })

    return {
        'mes': mes,
        'pares': pares,
        'resumo': resumo,
        'despesas_compartilhadas': despesas_compartilhadas,
        'despesas_individuais': despesas_individuais,
        'dividas': dividas,
    }
