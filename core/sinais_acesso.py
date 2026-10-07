"""Registra entrada, saída e senha incorreta. Nunca grava senha nem IP."""
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .alerta_horario import entrada_de_funcionaria_fora_do_horario
from .models import RegistroAcesso


@receiver(user_logged_in)
def registrar_entrada(sender, request, user, **kwargs):
    if user is None or not getattr(user, 'pk', None):
        return
    RegistroAcesso.objects.create(
        usuario=user,
        tipo=RegistroAcesso.Tipo.ENTROU,
        fora_do_horario=entrada_de_funcionaria_fora_do_horario(user),
    )


@receiver(user_logged_out)
def registrar_saida(sender, request, user, **kwargs):
    if user is None or not getattr(user, 'pk', None):
        return
    RegistroAcesso.objects.create(
        usuario=user,
        tipo=RegistroAcesso.Tipo.SAIU,
    )


@receiver(user_login_failed)
def registrar_tentativa_falhou(sender, credentials, request, **kwargs):
    digitado = ''
    if credentials:
        digitado = credentials.get('username') or ''
    RegistroAcesso.objects.create(
        usuario=None,
        usuario_digitado=str(digitado)[:150],
        tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU,
    )
