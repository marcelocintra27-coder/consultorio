from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'entrar/',
        LoginView.as_view(template_name='core/login.html'),
        name='entrar',
    ),
    path('sair/', LogoutView.as_view(), name='sair'),
    path('', include('core.urls')),
    path('locacao/', include('locacao.urls')),
]