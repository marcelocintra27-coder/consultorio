from django.contrib import admin

from .models import Disponibilidade, Sala


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
