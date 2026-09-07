from django.utils import timezone

from .permissoes import usuario_pode_financeiro


def admin_local_date(request):
    return {"admin_local_date": timezone.localdate().isoformat()}


def permissoes_usuario(request):
    return {'pode_financeiro': usuario_pode_financeiro(request.user)}
