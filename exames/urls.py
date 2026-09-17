from django.urls import path
from . import views

app_name = 'exames'
urlpatterns = [
    path('', views.listar, name='lista'),
    path('novo/', views.novo, name='novo'),
    path('<uuid:pk>/', views.detalhe, name='detalhe'),
    path('<uuid:pk>/download/', views.baixar, name='download'),
    path('<uuid:pk>/corrigir/', views.novo, name='corrigir'),
    path('<uuid:pk>/invalidar/', views.invalidacao, name='invalidar'),
    path('<uuid:pk>/inspecionar/', views.inspecao, name='inspecionar'),
]
