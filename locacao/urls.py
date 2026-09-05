from django.urls import path

from .views import (
    acerto_mensal,
    cadastrar_despesa,
    cadastrar_dentista,
    editar_despesa,
    editar_dentista,
    listar_despesas,
    listar_dentistas,
    marcar_pagamento,
)

app_name = 'locacao'

urlpatterns = [
    path('dentistas/', listar_dentistas, name='listar_dentistas'),
    path('dentistas/cadastrar/', cadastrar_dentista, name='cadastrar_dentista'),
    path('dentistas/<int:pk>/editar/', editar_dentista, name='editar_dentista'),
    path('despesas/', listar_despesas, name='listar_despesas'),
    path('despesas/cadastrar/', cadastrar_despesa, name='cadastrar_despesa'),
    path('despesas/<int:pk>/editar/', editar_despesa, name='editar_despesa'),
    path('acerto/', acerto_mensal, name='acerto_mensal'),
    path('acerto/marcar-pagamento/', marcar_pagamento, name='marcar_pagamento'),
]
