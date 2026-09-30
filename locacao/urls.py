from django.urls import path

from .views import (
    acerto_mensal,
    cadastrar_despesa,
    cadastrar_dentista,
    cadastrar_divida,
    cadastrar_turno,
    desativar_turno,
    editar_despesa,
    editar_dentista,
    editar_divida,
    editar_turno,
    listar_despesas,
    listar_dentistas,
    listar_dividas,
    marcar_pagamento,
)

app_name = 'locacao'

urlpatterns = [
    path('dentistas/', listar_dentistas, name='listar_dentistas'),
    path('dentistas/cadastrar/', cadastrar_dentista, name='cadastrar_dentista'),
    path('dentistas/<int:pk>/editar/', editar_dentista, name='editar_dentista'),
    path('dentistas/<int:pk>/turnos/cadastrar/', cadastrar_turno, name='cadastrar_turno'),
    path(
        'dentistas/<int:pk>/turnos/<int:turno_pk>/editar/',
        editar_turno,
        name='editar_turno',
    ),
    path(
        'dentistas/<int:pk>/turnos/<int:turno_pk>/desativar/',
        desativar_turno,
        name='desativar_turno',
    ),
    path('despesas/', listar_despesas, name='listar_despesas'),
    path('despesas/cadastrar/', cadastrar_despesa, name='cadastrar_despesa'),
    path('despesas/<int:pk>/editar/', editar_despesa, name='editar_despesa'),
    path('dividas/', listar_dividas, name='listar_dividas'),
    path('dividas/cadastrar/', cadastrar_divida, name='cadastrar_divida'),
    path('dividas/<int:pk>/editar/', editar_divida, name='editar_divida'),
    path('acerto/', acerto_mensal, name='acerto_mensal'),
    path('acerto/marcar-pagamento/', marcar_pagamento, name='marcar_pagamento'),
]
