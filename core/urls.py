from django.urls import path
from .views import (
    inicio,
    listar_pacientes,
    cadastrar_paciente,
    editar_paciente,
    listar_convenios,
    cadastrar_convenio,
    editar_convenio,
    listar_consultas,
)

app_name = 'core'

urlpatterns = [
    path('', inicio, name='inicio'),
    path('pacientes/', listar_pacientes, name='listar_pacientes'),
    path('pacientes/cadastrar/', cadastrar_paciente, name='cadastrar_paciente'),
    path('pacientes/<int:pk>/editar/', editar_paciente, name='editar_paciente'),
    path('convenios/', listar_convenios, name='listar_convenios'),
    path('convenios/cadastrar/', cadastrar_convenio, name='cadastrar_convenio'),
    path('convenios/<int:pk>/editar/', editar_convenio, name='editar_convenio'),
    path('consultas/', listar_consultas, name='listar_consultas'),
]
