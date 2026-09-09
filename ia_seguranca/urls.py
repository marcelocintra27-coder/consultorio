from django.urls import path

from . import views

app_name = "ia_seguranca"

urlpatterns = [
    path(
        "consultas/<int:pk>/transcrever/",
        views.transcrever_consulta,
        name="transcrever_consulta",
    ),
    path(
        "consultas/<int:pk>/salvar-evolucao/",
        views.salvar_evolucao,
        name="salvar_evolucao",
    ),
]
