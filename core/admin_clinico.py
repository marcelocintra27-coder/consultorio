from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.html import format_html_join

from .integridade_documentos import documento_bloqueado, verificar_integridade, tipo_documento
from .permissoes import usuario_pode_acessar_prontuario, usuario_e_administrador, dentista_do_usuario


class AdminClinicoProtegido:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if usuario_e_administrador(request.user):
            return qs
        dentista = dentista_do_usuario(request.user)
        if not dentista:
            return qs.none()
        if self.model._meta.model_name == 'retificacaodocumento':
            filtro = Q()
            for campo in ('evolucao', 'anamnese', 'plano', 'autorizacao', 'prescricao'):
                filtro |= Q(**{campo + '__paciente__consultas__dentista': dentista})
            return qs.filter(filtro).distinct()
        return qs.filter(paciente__consultas__dentista=dentista).distinct()

    def _autorizado(self, request, obj):
        if obj is None:
            return usuario_e_administrador(request.user) or dentista_do_usuario(request.user) is not None
        if obj.paciente_id:
            return usuario_pode_acessar_prontuario(request.user, obj.paciente)
        return usuario_e_administrador(request.user)

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._autorizado(request, obj)

    def has_add_permission(self, request):
        if self.model._meta.model_name in ('evolucao', 'assinaturaeletronica', 'retificacaodocumento'):
            return False
        return super().has_add_permission(request) and self._autorizado(request, None)

    def has_change_permission(self, request, obj=None):
        return (super().has_change_permission(request, obj) and self._autorizado(request, obj)
                and (obj is None or not documento_bloqueado(obj)))

    def has_delete_permission(self, request, obj=None):
        return (super().has_delete_permission(request, obj) and self._autorizado(request, obj)
                and (obj is None or not documento_bloqueado(obj)))

    def save_model(self, request, obj, form, change):
        if not self._autorizado(request, obj) or (change and documento_bloqueado(obj)):
            raise PermissionDenied
        super().save_model(request, obj, form, change)

    def delete_queryset(self, request, queryset):
        if any(not self.has_delete_permission(request, obj) for obj in queryset):
            raise PermissionDenied
        super().delete_queryset(request, queryset)

    def get_readonly_fields(self, request, obj=None):
        campos = tuple(super().get_readonly_fields(request, obj))
        if obj and (tipo_documento(obj) or obj._meta.model_name == 'assinaturaeletronica'):
            campos += ('integridade_documental',)
        return campos

    def integridade_documental(self, obj):
        if obj._meta.model_name == 'assinaturaeletronica':
            from .integridade_documentos import documento_da_assinatura
            obj = documento_da_assinatura(obj)
            if obj is None:
                return 'Não foi possível conferir a integridade de um documento clínico associado.'
        if getattr(obj, 'status', None) == 'rascunho' and not documento_bloqueado(obj):
            return 'Rascunho não assinado. A verificação será feita após a assinatura.'
        resultado = verificar_integridade(obj)
        textos = resultado.ocorrencias or ('Integridade conferida com os hashes registrados.',)
        return format_html_join('', '<p>{}</p>', ((texto,) for texto in textos))


class InlineClinicoProtegido:
    def has_add_permission(self, request, obj=None):
        return (obj is None or not documento_bloqueado(obj)) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return (obj is None or not documento_bloqueado(obj)) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return (obj is None or not documento_bloqueado(obj)) and super().has_delete_permission(request, obj)
