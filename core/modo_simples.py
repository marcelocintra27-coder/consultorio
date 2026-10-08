from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .permissoes import perfil_do_usuario


@login_required
@require_POST
def alternar_modo_simples(request):
    perfil = perfil_do_usuario(request.user)
    if perfil is None:
        raise PermissionDenied
    perfil.modo_simples = not perfil.modo_simples
    perfil.save(update_fields=['modo_simples'])
    return redirect('core:inicio')
