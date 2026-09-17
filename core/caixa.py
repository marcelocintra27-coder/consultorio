from django.utils import timezone

from .models import AuditoriaCaixa, CaixaDiario, MovimentoCaixa


def registrar_movimento_automatico(*, recebimento=None, baixa=None, usuario):
    """Registra uma única origem no caixa aberto da data da operação."""
    data = (recebimento.recebido_em if recebimento else baixa.baixado_em).date()
    try:
        caixa = CaixaDiario.objects.get(data=data, situacao=CaixaDiario.Situacao.ABERTO)
    except CaixaDiario.DoesNotExist:
        return None
    if recebimento:
        tipo = (
            MovimentoCaixa.Tipo.ENTRADA_AUTOMATICA
            if recebimento.tipo == recebimento.Tipo.RECEBIMENTO
            else MovimentoCaixa.Tipo.SAIDA_AUTOMATICA
        )
        movimento, criado = MovimentoCaixa.objects.get_or_create(
            recebido=recebimento,
            defaults={'caixa': caixa, 'tipo': tipo,
                      'valor': recebimento.valor, 'usuario': usuario},
        )
    else:
        movimento, criado = MovimentoCaixa.objects.get_or_create(
            baixa=baixa,
            defaults={'caixa': caixa, 'tipo': MovimentoCaixa.Tipo.SAIDA_AUTOMATICA,
                      'valor': baixa.valor, 'usuario': usuario},
        )
    if criado:
        AuditoriaCaixa.objects.create(caixa=caixa, movimento=movimento, usuario=usuario, descricao='Movimento automático registrado.')
    return movimento
