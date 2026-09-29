"""Marca até que horas cada usuária usou o sistema, no dia de São Paulo."""
from datetime import datetime, timedelta

from django.db import IntegrityError
from django.utils import timezone

from .models import AtividadeDiaria

INTERVALO = timedelta(minutes=5)
SESSAO = 'atividade_diaria_em'


class AtividadeDiariaMiddleware:
    """Grava no máximo uma vez a cada 5 minutos por usuária."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.registrar(request)
        return self.get_response(request)

    def registrar(self, request):
        usuario = getattr(request, 'user', None)
        if usuario is None or not usuario.is_authenticated:
            return
        agora = timezone.now()
        if self._dentro_do_intervalo(request, agora):
            return
        dia = timezone.localdate(agora)
        limite = agora - INTERVALO
        atualizados = AtividadeDiaria.objects.filter(
            usuario=usuario,
            data=dia,
            ultima_atividade__lte=limite,
        ).update(ultima_atividade=agora)
        if atualizados:
            self._marcar(request, agora)
            return
        if AtividadeDiaria.objects.filter(usuario=usuario, data=dia).exists():
            return
        try:
            AtividadeDiaria.objects.create(
                usuario=usuario,
                data=dia,
                primeira_atividade=agora,
                ultima_atividade=agora,
            )
        except IntegrityError:
            return
        self._marcar(request, agora)

    def _dentro_do_intervalo(self, request, agora):
        sessao = getattr(request, 'session', None)
        if sessao is None:
            return False
        marcado = sessao.get(SESSAO)
        if not marcado:
            return False
        try:
            ultimo = datetime.fromisoformat(marcado)
        except (TypeError, ValueError):
            return False
        if timezone.is_naive(ultimo):
            return False
        return agora - ultimo < INTERVALO

    def _marcar(self, request, agora):
        sessao = getattr(request, 'session', None)
        if sessao is not None:
            sessao[SESSAO] = agora.isoformat()
