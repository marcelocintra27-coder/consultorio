"""Pendências e alertas da ficha do paciente.

Cada item só aparece para quem pode agir sobre ele: o clínico vê o que é do
prontuário, o administrador vê valores, e quem edita o cadastro vê o que falta
no cadastro.
"""
from django.urls import reverse
from django.utils import timezone

from .models import Consulta, FichaCadastroAnamnese


def alerta_alergia(paciente):
    """Texto da alergia informada na anamnese assinada mais recente, se houver."""
    ficha = (
        FichaCadastroAnamnese.objects.filter(paciente=paciente)
        .exclude(status=FichaCadastroAnamnese.Status.RASCUNHO)
        .order_by('-criado_em', '-pk')
        .first()
    )
    if ficha and ficha.alergia == FichaCadastroAnamnese.SimNao.SIM:
        return (ficha.alergia_qual or 'sim (sem detalhe)').strip()
    return ''


def pendencias_paciente(paciente, *, pode_clinico, pode_financeiro, pode_editar):
    itens = []
    if pode_clinico:
        abertas = FichaCadastroAnamnese.objects.filter(
            paciente=paciente,
            status__in=[
                FichaCadastroAnamnese.Status.RASCUNHO,
                FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA,
            ],
        ).order_by('tipo')
        for ficha in abertas:
            nome = 'Anamnese HOF' if ficha.tipo == 'hof' else 'Anamnese odontológica'
            if ficha.status == FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA:
                itens.append({
                    'texto': f'{nome}: falta a assinatura do dentista.',
                    'acao': 'Ver e concluir',
                    'link': reverse('core:ver_ficha_anamnese', args=[paciente.pk, ficha.pk]),
                })
            else:
                itens.append({
                    'texto': f'{nome}: em preenchimento, ainda sem assinatura do paciente.',
                    'acao': 'Abrir anamnese',
                    'link': reverse('core:listar_fichas_anamnese', args=[paciente.pk]),
                })
    if pode_financeiro:
        hoje = timezone.localdate()
        consultas = (
            Consulta.objects.filter(paciente=paciente, data__lte=hoje, pago=False)
            .exclude(status__in=[Consulta.Status.CANCELADA, Consulta.Status.FALTOU])
            .order_by('-data', '-hora_inicio')[:20]
        )
        for consulta in consultas:
            valor = consulta.valor_a_cobrar
            if valor > 0:
                texto_valor = f'{valor:.2f}'.replace('.', ',')
                itens.append({
                    'texto': (
                        f'R$ {texto_valor} em aberto da consulta de '
                        f'{consulta.data:%d/%m/%Y}.'
                    ),
                    'acao': 'Ver na agenda',
                    'link': (
                        reverse('core:listar_consultas')
                        + f'?data={consulta.data.isoformat()}'
                    ),
                })
    if pode_editar:
        editar = reverse('core:editar_paciente', args=[paciente.pk])
        if not (paciente.cpf or '').strip():
            itens.append({
                'texto': 'Cadastro sem CPF: ele é pedido para assinar plano e autorização.',
                'acao': 'Completar cadastro',
                'link': editar,
            })
        if not (paciente.whatsapp or '').strip():
            itens.append({
                'texto': 'Sem WhatsApp no cadastro: o paciente não recebe lembrete de consulta.',
                'acao': 'Completar cadastro',
                'link': editar,
            })
    return itens
