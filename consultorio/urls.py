from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path

from core.views import sair

handler403 = 'django.views.defaults.permission_denied'

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'entrar/',
        LoginView.as_view(template_name='core/login.html'),
        name='entrar',
    ),
    path('sair/', sair, name='sair'),
    path('', include('core.urls')),
    path('locacao/', include('locacao.urls')),
]
