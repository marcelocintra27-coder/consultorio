from django.urls import path
from .views import (
    inicio,
    listar_pacientes,
    cadastrar_paciente,
    editar_paciente,
    listar_consultas,
)

app_name = 'core'

urlpatterns = [
    path('', inicio, name='inicio'),
    path('pacientes/', listar_pacientes, name='listar_pacientes'),
    path('pacientes/cadastrar/', cadastrar_paciente, name='cadastrar_paciente'),
    path('pacientes/<int:pk>/editar/', editar_paciente, name='editar_paciente'),
    path('consultas/', listar_consultas, name='listar_consultas'),
]
