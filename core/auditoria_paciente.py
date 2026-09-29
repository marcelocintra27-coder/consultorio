"""Registro imutável de quem criou ou alterou um paciente."""
from datetime import date, datetime

from django.db import models

from .models import AuditoriaPaciente

CAMPOS_AUDITADOS = (
    'nome_completo',
    'cpf',
    'data_nascimento',
    'telefone',
    'whatsapp',
    'email',
    'endereco',
    'convenio',
    'carteirinha',
    'observacoes',
    'instagram',
    'facebook',
    'outra_rede_social',
    'ativo',
)


def valor_auditavel(paciente, nome):
    campo = paciente._meta.get_field(nome)
    if isinstance(campo, models.ForeignKey):
        return getattr(paciente, campo.attname)
    valor = getattr(paciente, nome)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def snapshot(paciente):
    return {nome: valor_auditavel(paciente, nome) for nome in CAMPOS_AUDITADOS}


def diferencas(anteriores, paciente):
    mudancas = {}
    for nome in CAMPOS_AUDITADOS:
        depois = valor_auditavel(paciente, nome)
        antes = anteriores[nome]
        if antes != depois:
            mudancas[nome] = {'antes': antes, 'depois': depois}
    return mudancas


def valores_iniciais(paciente):
    return {
        nome: {'antes': None, 'depois': valor_auditavel(paciente, nome)}
        for nome in CAMPOS_AUDITADOS
    }


def acao_da_mudanca(alteracoes):
    ativo = alteracoes.get('ativo')
    if ativo and ativo['antes'] is True and ativo['depois'] is False:
        return AuditoriaPaciente.Acao.DESATIVADO
    if ativo and ativo['antes'] is False and ativo['depois'] is True:
        return AuditoriaPaciente.Acao.REATIVADO
    return AuditoriaPaciente.Acao.ALTERADO


def registrar_auditoria_paciente(*, paciente, usuario, acao, origem, alteracoes):
    return AuditoriaPaciente.objects.create(
        paciente=paciente,
        usuario=usuario,
        acao=acao,
        origem=origem,
        alteracoes=alteracoes,
    )
