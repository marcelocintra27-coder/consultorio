from django.contrib import admin
from .models import Exame, EventoExame


class SomenteAuditoria(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if self.has_module_permission(request) else qs.none()


@admin.register(Exame)
class ExameAdmin(SomenteAuditoria):
    list_display = ['id', 'categoria', 'criado_em', 'estado']
    exclude = ['chave']

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if self.has_view_permission(request):
            obj = self.get_object(request, object_id)
            if obj:
                from .services import evento
                evento(request.user, 'consulta_admin', exame=obj)
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        if self.has_view_permission(request):
            from .services import evento
            evento(request.user, 'listagem_admin')
        return super().changelist_view(request, extra_context)


@admin.register(EventoExame)
class EventoAdmin(SomenteAuditoria):
    list_display = ['id', 'criado_em', 'acao', 'resultado', 'usuario']
