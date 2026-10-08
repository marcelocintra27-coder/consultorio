"""Ao definir a senha de outra pessoa no Admin, a troca passa a ser obrigatória."""
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .troca_senha import marcar_troca_obrigatoria


class UsuarioAdmin(UserAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change or getattr(request.user, 'pk', None) == obj.pk:
            return
        if obj.has_usable_password():
            marcar_troca_obrigatoria(obj)

    def user_change_password(self, request, id, form_url=''):
        usuario = self.get_object(request, unquote(id))
        senha_antes = usuario.password if usuario is not None else None
        resposta = super().user_change_password(request, id, form_url)
        if (
            request.method == 'POST'
            and usuario is not None
            and senha_antes
            and getattr(request.user, 'pk', None) != usuario.pk
        ):
            usuario.refresh_from_db(fields=['password'])
            if usuario.password != senha_antes and usuario.has_usable_password():
                marcar_troca_obrigatoria(usuario)
        return resposta


admin.site.unregister(User)
admin.site.register(User, UsuarioAdmin)
