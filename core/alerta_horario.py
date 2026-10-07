"""Alerta de entrada da funcionária fora do horário. O login não é bloqueado."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from locacao.models import PerfilUsuario

from .models import RegistroAcesso
from .permissoes import dentista_do_usuario, perfil_do_usuario, usuario_e_administrador

DIAS_AVISO = 7
DIAS_SEMANA = (
    'segunda-feira',
    'terça-feira',
    'quarta-feira',
    'quinta-feira',
    'sexta-feira',
    'sábado',
    'domingo',
)
_PAPEIS_FUNCIONARIA = {
    PerfilUsuario.Papel.AUXILIAR,
    PerfilUsuario.Papel.SECRETARIA,
}


def _momento_na_clinica(momento):
    if momento is None:
        momento = timezone.now()
    fuso = ZoneInfo(settings.FUSO_HORARIO_CLINICA)
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento, fuso)
    return momento.astimezone(fuso)


def fora_do_horario_da_clinica(momento=None):
    """Segunda a sexta, do minuto 07:30 ao minuto 18:00, no fuso da clínica."""
    local = _momento_na_clinica(momento)
    if local.weekday() not in settings.HORARIO_CLINICA_DIAS:
        return True
    hora = local.time().replace(second=0, microsecond=0)
    return not (
        settings.HORARIO_CLINICA_INICIO <= hora <= settings.HORARIO_CLINICA_FIM
    )


def usuario_e_funcionaria(user):
    """Auxiliar ou secretária. Dentista, admin e superusuário ficam de fora."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if usuario_e_administrador(user):
        return False
    perfil = perfil_do_usuario(user)
    return bool(perfil and perfil.papel in _PAPEIS_FUNCIONARIA)


def entrada_de_funcionaria_fora_do_horario(user, momento=None):
    if not usuario_e_funcionaria(user):
        return False
    return fora_do_horario_da_clinica(momento)


def usuario_pode_ver_entradas_fora_do_horario(user):
    if usuario_e_administrador(user):
        return True
    return dentista_do_usuario(user) is not None


def entradas_fora_do_horario_visiveis(user):
    consultas = RegistroAcesso.objects.filter(
        tipo=RegistroAcesso.Tipo.ENTROU,
        fora_do_horario=True,
        usuario__isnull=False,
    ).select_related('usuario', 'usuario__perfil')
    if usuario_e_administrador(user):
        return consultas
    dentista = dentista_do_usuario(user)
    if dentista is None:
        return consultas.none()
    return consultas.filter(usuario__perfil__dentista_id=dentista.pk)


def contagem_entradas_fora_do_horario(user):
    if not usuario_pode_ver_entradas_fora_do_horario(user):
        return 0
    limite = timezone.now() - timedelta(days=DIAS_AVISO)
    return entradas_fora_do_horario_visiveis(user).filter(criado_em__gte=limite).count()


def _nome(usuario):
    return usuario.get_full_name() or usuario.get_username()


def _linha(registro):
    local = _momento_na_clinica(registro.criado_em)
    return {
        'nome': _nome(registro.usuario),
        'dia_semana': DIAS_SEMANA[local.weekday()],
        'data': local.strftime('%d/%m/%Y'),
        'hora': local.strftime('%H:%M'),
    }


def listar_entradas_fora_do_horario(request):
    if not usuario_pode_ver_entradas_fora_do_horario(request.user):
        raise PermissionDenied
    registros = entradas_fora_do_horario_visiveis(request.user).order_by(
        '-criado_em', '-pk',
    )
    return render(request, 'core/entradas_fora_do_horario.html', {
        'entradas': [_linha(registro) for registro in registros],
    })
