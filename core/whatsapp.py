"""Lembretes de consulta por WhatsApp.

Nesta etapa o envio é simulado: nada sai para a rede. O modo ``meta`` só
confere as variáveis e recusa o envio enquanto a Cloud API não estiver ligada.
"""
import hashlib
import hmac
import os
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AuditoriaConsulta, Consulta, MensagemWhatsApp


class ErroWhatsApp(Exception):
    """Configuração ou envio que não deve gravar mensagem como enviada."""


def modo_whatsapp():
    return (os.environ.get('WHATSAPP_MODO') or 'simulado').strip().lower() or 'simulado'


def normalizar_telefone(numero):
    digitos = re.sub(r'\D', '', numero or '')
    if digitos.startswith('55') and len(digitos) >= 12:
        return f'+{digitos}'
    if len(digitos) in (10, 11):
        return f'+55{digitos}'
    return ''


def texto_lembrete(consulta):
    """Só data, hora e nome da dentista. Sem procedimento, diagnóstico ou valor."""
    primeiro = consulta.paciente.nome_completo.strip().split()[0]
    if consulta.dentista_id:
        dentista = consulta.dentista.nome_completo
    else:
        dentista = 'não informada'
    if consulta.data == timezone.localdate() + timedelta(days=1):
        quando = f'amanhã, {consulta.data:%d/%m}'
    else:
        quando = f'no dia {consulta.data:%d/%m}'
    return (
        f'Olá, {primeiro}! Lembramos da sua consulta na Clínica Odontológica 90 {quando}, '
        f'às {consulta.hora_inicio:%H:%M}, com {dentista}. '
        'Responda 1 para CONFIRMAR ou 2 para DESMARCAR. Esta é uma mensagem automática.'
    )


class EnvioSimulado:
    def enviar(self, telefone, texto):
        return MensagemWhatsApp.Status.SIMULADA


class EnvioMeta:
    """Esqueleto da WhatsApp Cloud API. Não abre conexão nesta etapa."""

    def enviar(self, telefone, texto):
        token = (os.environ.get('WHATSAPP_TOKEN') or '').strip()
        phone_id = (os.environ.get('WHATSAPP_PHONE_NUMBER_ID') or '').strip()
        if not token or not phone_id:
            raise ErroWhatsApp(
                'WHATSAPP_MODO=meta exige WHATSAPP_TOKEN e WHATSAPP_PHONE_NUMBER_ID. '
                'Nenhuma mensagem foi enviada.'
            )
        raise ErroWhatsApp(
            'O envio pela API da Meta ainda não está habilitado. Nenhuma mensagem foi enviada.'
        )


def provedor_envio():
    modo = modo_whatsapp()
    if modo == 'simulado':
        return EnvioSimulado()
    if modo == 'meta':
        return EnvioMeta()
    raise ErroWhatsApp(
        f'WHATSAPP_MODO inválido: {modo}. Use simulado ou meta. Nenhuma mensagem foi enviada.'
    )


def consultas_elegiveis(data):
    return (
        Consulta.objects.filter(
            data=data,
            status__in=(Consulta.Status.AGENDADA, Consulta.Status.CONFIRMADA),
            paciente__aceita_lembretes_whatsapp=True,
        )
        .exclude(paciente__whatsapp='')
        .select_related('paciente', 'dentista')
        .order_by('hora_inicio', 'pk')
    )


def preparar_lembretes(data=None):
    """Grava um lembrete por consulta elegível. Não duplica e não acessa a rede."""
    if data is None:
        data = timezone.localdate() + timedelta(days=1)
    provedor = provedor_envio()
    criados = 0
    for consulta in consultas_elegiveis(data):
        if MensagemWhatsApp.objects.filter(
            consulta=consulta,
            direcao=MensagemWhatsApp.Direcao.ENVIADA,
        ).exists():
            continue
        telefone = normalizar_telefone(consulta.paciente.whatsapp)
        if not telefone:
            continue
        texto = texto_lembrete(consulta)
        status = provedor.enviar(telefone, texto)
        try:
            MensagemWhatsApp.objects.create(
                consulta=consulta,
                paciente=consulta.paciente,
                telefone=telefone,
                direcao=MensagemWhatsApp.Direcao.ENVIADA,
                texto=texto,
                status=status,
            )
        except IntegrityError:
            continue
        criados += 1
    return criados


def _lembrete_mais_recente(telefone):
    return (
        MensagemWhatsApp.objects.filter(
            telefone=telefone,
            direcao=MensagemWhatsApp.Direcao.ENVIADA,
        )
        .select_related('consulta', 'paciente')
        .order_by('-criado_em', '-pk')
        .first()
    )


def _queryset_lembrete_travado():
    """Trava só a mensagem.

    consulta e paciente são anuláveis. Juntá-los com select_related gera
    LEFT OUTER JOIN, e o PostgreSQL recusa FOR UPDATE nesse lado do join.
    A consulta, quando existe, é travada na própria tabela logo em seguida.
    """
    return MensagemWhatsApp.objects.select_for_update(of=('self',))


def _registrar_auditoria_resposta(consulta, status_anterior):
    AuditoriaConsulta.objects.create(
        consulta=consulta,
        usuario=None,
        descricao=(
            f'Status: {status_anterior} -> {consulta.status}; origem: resposta WhatsApp'
        ),
    )


def _resposta_pode_alterar_consulta(consulta):
    return (
        consulta.data >= timezone.localdate()
        and consulta.status in (Consulta.Status.AGENDADA, Consulta.Status.CONFIRMADA)
    )


def registrar_resposta(telefone, texto, id_externo=''):
    """Associa a resposta ao lembrete mais recente daquele telefone."""
    telefone = normalizar_telefone(telefone)
    if not telefone:
        raise ErroWhatsApp('Telefone da resposta não pôde ser normalizado.')
    if id_externo and MensagemWhatsApp.objects.filter(
        id_externo=id_externo,
        direcao=MensagemWhatsApp.Direcao.RECEBIDA,
    ).exists():
        return MensagemWhatsApp.objects.get(
            id_externo=id_externo,
            direcao=MensagemWhatsApp.Direcao.RECEBIDA,
        )
    resposta_texto = (texto or '').strip()
    with transaction.atomic():
        lembrete = _lembrete_mais_recente(telefone)
        if lembrete is not None:
            lembrete = _queryset_lembrete_travado().get(pk=lembrete.pk)
        acao = ''
        consulta = lembrete.consulta if lembrete is not None else None
        paciente = lembrete.paciente if lembrete is not None else None
        if consulta is not None:
            consulta = Consulta.objects.select_for_update().get(pk=consulta.pk)
            status_anterior = consulta.status
            if not _resposta_pode_alterar_consulta(consulta):
                acao = MensagemWhatsApp.Acao.PRECISA_ATENCAO
            elif resposta_texto == '1':
                acao = MensagemWhatsApp.Acao.CONFIRMOU
                consulta.status = Consulta.Status.CONFIRMADA
            elif resposta_texto == '2':
                acao = MensagemWhatsApp.Acao.DESMARCOU
                consulta.status = Consulta.Status.CANCELADA
            else:
                acao = MensagemWhatsApp.Acao.PRECISA_ATENCAO
            if consulta.status != status_anterior:
                consulta.save(update_fields=['status'])
                _registrar_auditoria_resposta(consulta, status_anterior)
        else:
            acao = MensagemWhatsApp.Acao.PRECISA_ATENCAO
        return MensagemWhatsApp.objects.create(
            consulta=consulta,
            paciente=paciente,
            lembrete=lembrete,
            telefone=telefone,
            direcao=MensagemWhatsApp.Direcao.RECEBIDA,
            texto=resposta_texto,
            status=MensagemWhatsApp.Status.RECEBIDA,
            id_externo=id_externo or '',
            acao=acao,
        )


def assinatura_webhook_valida(corpo, cabecalho):
    segredo = (os.environ.get('WHATSAPP_APP_SECRET') or '').strip()
    if not segredo or not cabecalho:
        return False
    digest = hmac.new(segredo.encode('utf-8'), corpo, hashlib.sha256).hexdigest()
    esperado = f'sha256={digest}'
    return hmac.compare_digest(esperado, cabecalho.strip())
