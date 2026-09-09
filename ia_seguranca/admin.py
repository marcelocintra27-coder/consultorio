from django.contrib import admin

from .models import ConsentimentoIA, RegistroAuditoriaIA


@admin.register(ConsentimentoIA)
class ConsentimentoIAAdmin(admin.ModelAdmin):
    list_display = ("paciente", "finalidade", "concedido", "concedido_em", "revogado_em")
    list_filter = ("finalidade", "concedido")
    search_fields = ("paciente__nome_completo",)


@admin.register(RegistroAuditoriaIA)
class RegistroAuditoriaIAAdmin(admin.ModelAdmin):
    list_display = ("data_hora", "recurso", "paciente", "usuario", "decisao")
    list_filter = ("recurso", "decisao")
    search_fields = ("paciente__nome_completo", "entrada_resumo", "saida_sugerida")
