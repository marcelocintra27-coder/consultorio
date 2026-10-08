"""Troca de senha da própria conta e bloqueio até a primeira troca."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import password_validation, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.debug import sensitive_post_parameters

from locacao.models import PerfilUsuario

from .permissoes import perfil_do_usuario

AVISO_TROCA_OBRIGATORIA = (
    'Por segurança, crie a sua própria senha antes de continuar.'
)
MENSAGEM_SENHA_ALTERADA = 'Senha alterada com sucesso.'


def marcar_troca_obrigatoria(usuario):
    """Marca o perfil existente. Sem perfil, não há onde gravar a obrigação."""
    if getattr(usuario, 'pk', None) is None:
        return
    PerfilUsuario.objects.filter(
        usuario_id=usuario.pk,
        deve_trocar_senha=False,
    ).update(deve_trocar_senha=True)


def concluir_troca_obrigatoria(usuario):
    if getattr(usuario, 'pk', None) is None:
        return
    PerfilUsuario.objects.filter(
        usuario_id=usuario.pk,
        deve_trocar_senha=True,
    ).update(deve_trocar_senha=False)


def mensagens_da_validacao(erro):
    """Traduz os códigos da validação de senha do Django para português simples."""
    itens = getattr(erro, 'error_list', None) or [erro]
    return [texto_da_validacao(item) for item in itens]


def texto_da_validacao(item):
    codigo = getattr(item, 'code', None)
    params = getattr(item, 'params', None) or {}
    if codigo == 'password_too_short':
        minimo = params.get('min_length', 8)
        return (
            f'A senha nova é curta demais. Use pelo menos {minimo} caracteres.'
        )
    if codigo == 'password_too_similar':
        return 'A senha nova é parecida demais com os seus dados.'
    if codigo == 'password_too_common':
        return 'Essa senha é muito comum. Escolha outra.'
    if codigo == 'password_entirely_numeric':
        return 'A senha nova não pode ter só números.'
    return 'Essa senha não atende às regras de segurança.'


class TrocaSenhaObrigatoriaMiddleware:
    """Enquanto a troca for obrigatória, só a própria tela, o login e o sair passam."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._deve_redirecionar(request):
            return redirect('core:trocar_senha')
        return self.get_response(request)

    def _deve_redirecionar(self, request):
        usuario = getattr(request, 'user', None)
        if usuario is None or not usuario.is_authenticated:
            return False
        if self._liberado(request):
            return False
        perfil = perfil_do_usuario(usuario)
        return bool(perfil and perfil.deve_trocar_senha)

    def _liberado(self, request):
        caminho = request.path
        if caminho.startswith(settings.STATIC_URL):
            return True
        media = getattr(settings, 'MEDIA_URL', '') or ''
        if media and caminho.startswith(media):
            return True
        return caminho in self._caminhos_liberados()

    def _caminhos_liberados(self):
        return {
            reverse('entrar'),
            reverse('sair'),
            reverse('core:trocar_senha'),
            reverse('admin:login'),
            reverse('admin:logout'),
        }


class TrocarSenhaForm(PasswordChangeForm):
    error_messages = {
        'password_incorrect': 'A senha atual está incorreta.',
        'password_mismatch': 'As senhas novas não são iguais.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'senha atual'
        self.fields['old_password'].error_messages['required'] = (
            'Informe a senha atual.'
        )
        self.fields['new_password1'].label = 'senha nova'
        self.fields['new_password1'].help_text = ''
        self.fields['new_password1'].error_messages['required'] = (
            'Informe a senha nova.'
        )
        self.fields['new_password2'].label = 'repetir senha nova'
        self.fields['new_password2'].help_text = ''
        self.fields['new_password2'].error_messages['required'] = (
            'Repita a senha nova.'
        )

    def clean(self):
        senha_nova = self.cleaned_data.get('new_password1')
        repetida = self.cleaned_data.get('new_password2')
        if senha_nova and repetida and senha_nova != repetida:
            self.add_error(
                'new_password2',
                self.error_messages['password_mismatch'],
            )
            return self.cleaned_data
        if repetida and 'new_password2' not in self.errors:
            try:
                password_validation.validate_password(repetida, self.user)
            except ValidationError as erro:
                self.add_error(
                    'new_password2',
                    ValidationError(mensagens_da_validacao(erro)),
                )
        return self.cleaned_data


@sensitive_post_parameters('old_password', 'new_password1', 'new_password2')
def trocar_senha(request):
    perfil = perfil_do_usuario(request.user)
    obrigar_troca = bool(perfil and perfil.deve_trocar_senha)
    if request.method == 'POST':
        form = TrocarSenhaForm(request.user, request.POST)
        if form.is_valid():
            usuario = form.save()
            update_session_auth_hash(request, usuario)
            concluir_troca_obrigatoria(usuario)
            messages.success(request, MENSAGEM_SENHA_ALTERADA)
            return redirect('core:inicio')
    else:
        form = TrocarSenhaForm(request.user)
    return render(request, 'core/trocar_senha.html', {
        'form': form,
        'obrigar_troca': obrigar_troca,
        'aviso_troca_obrigatoria': AVISO_TROCA_OBRIGATORIA,
    })
