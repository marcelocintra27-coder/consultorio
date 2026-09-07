from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from locacao.models import PerfilUsuario


def perfil_do_usuario(user):
    if user is None or not user.is_authenticated:
        return None
    try:
        return user.perfil
    except ObjectDoesNotExist:
        return None


def usuario_pode_financeiro(user):
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    return perfil.papel != PerfilUsuario.Papel.AUXILIAR


def exige_financeiro(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not usuario_pode_financeiro(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return inner
