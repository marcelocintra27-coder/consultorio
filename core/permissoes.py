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


def usuario_e_administrador(user):
    return bool(
        user is not None
        and user.is_authenticated
        and (user.is_staff or user.is_superuser)
    )


def usuario_pode_financeiro(user):
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    return perfil.papel == PerfilUsuario.Papel.DENTISTA


def exige_financeiro(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not usuario_pode_financeiro(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return inner


def dentista_do_usuario(user):
    perfil = perfil_do_usuario(user)
    if perfil is None or perfil.papel != PerfilUsuario.Papel.DENTISTA:
        return None
    return perfil.dentista


def usuario_pode_lancar(user, consulta):
    if not usuario_pode_financeiro(user):
        return False
    if usuario_e_administrador(user):
        return True
    if consulta.dentista_id is None:
        return False
    dentista = dentista_do_usuario(user)
    return dentista is not None and dentista.pk == consulta.dentista_id


def usuario_pode_complementar_dentista(user, consulta):
    if not consulta.eh_legado:
        return False
    return usuario_pode_financeiro(user)


def usuario_pode_editar_catalogo(user, dentista):
    if not usuario_pode_financeiro(user):
        return False
    if usuario_e_administrador(user):
        return True
    dentista_user = dentista_do_usuario(user)
    return dentista_user is not None and dentista_user.pk == dentista.pk
