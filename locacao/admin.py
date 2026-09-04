from django.contrib import admin

from .models import (
    Dentista,
    Despesa,
    Disponibilidade,
    DividaAvulsa,
    PagamentoPar,
    Sala,
)


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome', 'descricao')


@admin.register(Disponibilidade)
class DisponibilidadeAdmin(admin.ModelAdmin):
    list_display = ('sala', 'data', 'hora_inicio', 'hora_fim', 'status')
    list_filter = ('status', 'data', 'sala')
    date_hierarchy = 'data'


@admin.register(Dentista)
class DentistaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'sala', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome_completo',)
    autocomplete_fields = ('sala',)
    readonly_fields = ('cadastrado_em',)


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = (
        'descricao',
        'valor',
        'valor_cota',
        'competencia',
        'tipo',
        'pago_por',
    )
    list_filter = ('tipo', 'competencia', 'pago_por')
    search_fields = ('descricao',)
    autocomplete_fields = ('pago_por',)
    readonly_fields = ('cadastrado_em', 'valor_cota')
    date_hierarchy = 'competencia'


@admin.register(DividaAvulsa)
class DividaAvulsaAdmin(admin.ModelAdmin):
    list_display = (
        'descricao',
        'valor',
        'competencia',
        'de_dentista',
        'para_dentista',
    )
    list_filter = ('competencia',)
    search_fields = ('descricao',)
    autocomplete_fields = ('de_dentista', 'para_dentista')
    readonly_fields = ('cadastrado_em',)
    date_hierarchy = 'competencia'


@admin.register(PagamentoPar)
class PagamentoParAdmin(admin.ModelAdmin):
    list_display = ('de_dentista', 'para_dentista', 'competencia', 'pago')
    list_filter = ('pago', 'competencia')
    search_fields = (
        'de_dentista__nome_completo',
        'para_dentista__nome_completo',
    )
    autocomplete_fields = ('de_dentista', 'para_dentista')
    readonly_fields = ('cadastrado_em',)
    date_hierarchy = 'competencia'
