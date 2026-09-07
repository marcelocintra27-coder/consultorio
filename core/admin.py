from django.contrib import admin

from .models import (
    Convenio,
    Paciente,
    Evolucao,
    Consulta,
    MaterialUsado,
    Procedimento,
    PrecoProcedimento,
    LancamentoAtendimento,
    AuditoriaConsulta,
    ProcedimentoUniodonto,
)


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
        'dentista',
        'data',
        'hora_inicio',
        'hora_fim',
        'status',
        'eh_legado',
        'pago',
        'forma_pagamento',
        'valor_a_cobrar',
    )
    list_filter = ('status', 'pago', 'eh_legado', 'forma_pagamento', 'data')
    search_fields = ('paciente__nome_completo',)
    autocomplete_fields = ('paciente', 'dentista')
    readonly_fields = (
        'cadastrado_em',
        'valor_a_cobrar',
        'valor_historico',
        'dentista_complementado_em',
        'dentista_complementado_por',
    )
    list_per_page = 25


@admin.register(MaterialUsado)
class MaterialUsadoAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'valor', 'consulta', 'cadastrado_em')
    search_fields = ('descricao', 'consulta__paciente__nome_completo')
    autocomplete_fields = ('consulta',)
    readonly_fields = ('cadastrado_em',)
    list_per_page = 25


@admin.register(Procedimento)
class ProcedimentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'dentista', 'duracao_estimada_minutos', 'ativo')
    list_filter = ('ativo', 'dentista')
    search_fields = ('nome',)
    autocomplete_fields = ('dentista',)


@admin.register(PrecoProcedimento)
class PrecoProcedimentoAdmin(admin.ModelAdmin):
    list_display = ('procedimento', 'convenio', 'valor')
    list_filter = ('convenio',)
    autocomplete_fields = ('procedimento', 'convenio')


@admin.register(LancamentoAtendimento)
class LancamentoAtendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'nome_procedimento',
        'consulta',
        'valor_final',
        'tipo',
        'cadastrado_em',
    )
    list_filter = ('tipo', 'particular')
    search_fields = ('nome_procedimento',)
    autocomplete_fields = ('consulta', 'procedimento', 'dentista', 'convenio')
    readonly_fields = (
        'nome_procedimento',
        'valor_tabela',
        'percentual_desconto',
        'valor_final',
        'cadastrado_em',
        'cadastrado_por',
    )


@admin.register(AuditoriaConsulta)
class AuditoriaConsultaAdmin(admin.ModelAdmin):
    list_display = ('consulta', 'usuario', 'descricao', 'cadastrado_em')
    readonly_fields = ('consulta', 'usuario', 'descricao', 'cadastrado_em')


@admin.register(ProcedimentoUniodonto)
class ProcedimentoUniodontoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo',
        'nome',
        'categoria',
        'valor_us',
        'valor_reais',
        'fator_us',
        'ativo',
    )
    list_filter = ('categoria', 'ativo')
    search_fields = ('codigo', 'nome')
    readonly_fields = ('codigo', 'nome', 'categoria', 'valor_us', 'valor_reais', 'fator_us')

