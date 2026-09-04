from django.contrib import admin

from .models import Convenio, Paciente, Evolucao, Consulta


@admin.register(Convenio)
class ConvenioAdmin(admin.ModelAdmin):
    list_display = (
        'nome',
        'valor_hora',
        'percentual_desconto',
        'percentual_imposto',
        'ativo',
    )
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = (
        'nome_completo',
        'cpf',
        'convenio',
        'telefone',
        'ativo',
        'cadastrado_em',
    )
    list_filter = ('ativo', 'convenio')
    search_fields = (
        'nome_completo',
        'cpf',
        'telefone',
        'whatsapp',
        'email',
        'carteirinha',
    )
    autocomplete_fields = ('convenio',)
    readonly_fields = ('cadastrado_em',)
    list_per_page = 25


@admin.register(Evolucao)
class EvolucaoAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'data', 'descricao')


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = (
        'paciente',
        'data',
        'hora_inicio',
        'hora_fim',
        'status',
        'pago',
        'valor_a_cobrar',
    )
    list_filter = ('status', 'pago', 'data')
    search_fields = ('paciente__nome_completo',)
    autocomplete_fields = ('paciente',)
    readonly_fields = ('cadastrado_em', 'valor_a_cobrar')
    list_per_page = 25
