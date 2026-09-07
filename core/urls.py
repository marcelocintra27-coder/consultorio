from django.urls import path
from .views import (
    inicio,
    listar_pacientes,
    cadastrar_paciente,
    editar_paciente,
    listar_convenios,
    cadastrar_convenio,
    editar_convenio,
    listar_tabela_uniodonto,
    listar_consultas,
    marcar_consulta_paga,
    agendar_consulta,
    ficha_consulta,
    alterar_status_consulta,
    lancar_atendimento,
    complementar_dentista,
    listar_procedimentos,
    cadastrar_procedimento,
    editar_procedimento,
    listar_pagamentos_consulta,
    salvar_forma_pagamento,
    listar_materiais_dia,
    materiais_consulta,
    editar_material_usado,
    excluir_material_usado,
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
    path(
        'convenios/uniodonto/tabela/',
        listar_tabela_uniodonto,
        name='listar_tabela_uniodonto',
    ),
    path('consultas/', listar_consultas, name='listar_consultas'),
    path('consultas/agendar/', agendar_consulta, name='agendar_consulta'),
    path('consultas/<int:pk>/', ficha_consulta, name='ficha_consulta'),
    path(
        'consultas/<int:pk>/status/',
        alterar_status_consulta,
        name='alterar_status_consulta',
    ),
    path(
        'consultas/<int:pk>/lancar/',
        lancar_atendimento,
        name='lancar_atendimento',
    ),
    path(
        'consultas/<int:pk>/dentista/',
        complementar_dentista,
        name='complementar_dentista',
    ),
    path('procedimentos/', listar_procedimentos, name='listar_procedimentos'),
    path(
        'procedimentos/cadastrar/',
        cadastrar_procedimento,
        name='cadastrar_procedimento',
    ),
    path(
        'procedimentos/<int:pk>/editar/',
        editar_procedimento,
        name='editar_procedimento',
    ),
    path(
        'consultas/pagamentos/',
        listar_pagamentos_consulta,
        name='listar_pagamentos_consulta',
    ),
    path(
        'consultas/materiais/',
        listar_materiais_dia,
        name='listar_materiais_dia',
    ),
    path(
        'consultas/<int:pk>/marcar-pago/',
        marcar_consulta_paga,
        name='marcar_consulta_paga',
    ),
    path(
        'consultas/<int:pk>/forma-pagamento/',
        salvar_forma_pagamento,
        name='salvar_forma_pagamento',
    ),
    path(
        'consultas/<int:pk>/materiais/',
        materiais_consulta,
        name='materiais_consulta',
    ),
    path(
        'materiais/<int:pk>/editar/',
        editar_material_usado,
        name='editar_material_usado',
    ),
    path(
        'materiais/<int:pk>/excluir/',
        excluir_material_usado,
        name='excluir_material_usado',
    ),
]
