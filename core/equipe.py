"""Equipe: dentistas e funcionários num lugar só, sem a tela técnica do Django.

Criar um funcionário aqui cria, de uma vez, o acesso (usuário e senha) e a
função dele no sistema. Antes eram duas telas técnicas separadas, e esquecer a
segunda deixava a pessoa sem enxergar nada.
"""
import logging

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from locacao.models import Dentista, PerfilUsuario, TurnoLocacao

from .permissoes import exige_financeiro
from .troca_senha import mensagens_da_validacao

logger = logging.getLogger(__name__)
User = get_user_model()

FUNCOES = [
    (PerfilUsuario.Papel.SECRETARIA, 'Secretária / recepção'),
    (PerfilUsuario.Papel.AUXILIAR, 'Auxiliar de dentista'),
    (PerfilUsuario.Papel.DENTISTA, 'Dentista'),
]
NOME_FUNCAO = dict(FUNCOES)
PRECISA_DENTISTA = {PerfilUsuario.Papel.AUXILIAR, PerfilUsuario.Papel.DENTISTA}


def _dentistas_ativas():
    return Dentista.objects.filter(ativo=True).order_by('nome_completo')


class _FuncaoMixin:
    """Regras de função e dentista, iguais às do perfil, em português simples."""

    def _limpar_funcao(self, dados):
        funcao = dados.get('funcao')
        dentista = dados.get('dentista')
        if funcao in PRECISA_DENTISTA and not dentista:
            if funcao == PerfilUsuario.Papel.AUXILIAR:
                self.add_error('dentista', 'Escolha a dentista com quem a auxiliar trabalha.')
            else:
                self.add_error('dentista', 'Escolha o cadastro desta dentista na lista.')
        if funcao == PerfilUsuario.Papel.SECRETARIA:
            dados['dentista'] = None
        return dados


class _SenhaMixin:
    def _limpar_senha(self, dados, usuario):
        senha = dados.get('senha')
        confirmar = dados.get('confirmar_senha')
        if senha and confirmar and senha != confirmar:
            self.add_error('confirmar_senha', 'As duas senhas não são iguais. Digite de novo.')
            return dados
        if senha:
            try:
                password_validation.validate_password(senha, user=usuario)
            except ValidationError as erro:
                for texto in mensagens_da_validacao(erro):
                    self.add_error('senha', texto)
        return dados


def _campo_senha(rotulo):
    return forms.CharField(
        label=rotulo, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )


class NovoFuncionarioForm(_FuncaoMixin, _SenhaMixin, forms.Form):
    nome = forms.CharField(label='Nome completo', max_length=150)
    funcao = forms.ChoiceField(label='Função', choices=FUNCOES, widget=forms.RadioSelect)
    dentista = forms.ModelChoiceField(
        label='Trabalha com qual dentista?', queryset=Dentista.objects.none(), required=False,
        empty_label='Escolha a dentista',
        help_text='Auxiliar: a dentista com quem trabalha. Dentista: o cadastro dela.',
    )
    usuario = forms.CharField(
        label='Nome para entrar no sistema', max_length=150,
        help_text='Uma palavra só, sem espaço e sem acento. Ex.: renata',
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'autocapitalize': 'none'}),
    )
    senha = _campo_senha('Senha provisória')
    confirmar_senha = _campo_senha('Repita a senha provisória')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentista'].queryset = _dentistas_ativas()

    def clean_usuario(self):
        usuario = self.cleaned_data['usuario'].strip()
        if ' ' in usuario:
            raise ValidationError('Não use espaço. Ex.: renata ou renata.silva')
        try:
            UnicodeUsernameValidator()(usuario)
        except ValidationError:
            raise ValidationError('Use só letras, números e . _ - (sem espaço).')
        if User.objects.filter(username__iexact=usuario).exists():
            raise ValidationError('Esse nome já é usado por outra pessoa. Escolha outro.')
        return usuario

    def clean(self):
        dados = super().clean()
        self._limpar_funcao(dados)
        provisorio = User(username=dados.get('usuario') or '', first_name=dados.get('nome') or '')
        return self._limpar_senha(dados, provisorio)


class EditarFuncionarioForm(_FuncaoMixin, forms.Form):
    nome = forms.CharField(label='Nome completo', max_length=150)
    funcao = forms.ChoiceField(label='Função', choices=FUNCOES, widget=forms.RadioSelect)
    dentista = forms.ModelChoiceField(
        label='Trabalha com qual dentista?', queryset=Dentista.objects.none(), required=False,
        empty_label='Escolha a dentista',
        help_text='Auxiliar: a dentista com quem trabalha. Dentista: o cadastro dela.',
    )
    modo_simples = forms.BooleanField(
        label='Letra e botões maiores (modo simples)', required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentista'].queryset = _dentistas_ativas()

    def clean(self):
        return self._limpar_funcao(super().clean())


class SenhaProvisoriaForm(_SenhaMixin, forms.Form):
    senha = _campo_senha('Nova senha provisória')
    confirmar_senha = _campo_senha('Repita a nova senha provisória')

    def __init__(self, *args, usuario, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        return self._limpar_senha(super().clean(), self.usuario)


def _nome(usuario):
    return usuario.get_full_name() or usuario.username


@exige_financeiro
def equipe(request):
    dentistas = _dentistas_ativas().select_related('sala').prefetch_related(
        Prefetch(
            'turnos',
            queryset=TurnoLocacao.objects.filter(ativo=True).select_related('sala'),
        ),
        Prefetch(
            'perfis',
            queryset=PerfilUsuario.objects.filter(
                papel=PerfilUsuario.Papel.DENTISTA,
            ).select_related('usuario'),
            to_attr='acessos',
        ),
    )
    pessoas = []
    for usuario in (
        User.objects.select_related('perfil__dentista')
        .order_by('-is_active', 'first_name', 'username')
    ):
        perfil = getattr(usuario, 'perfil', None)
        if usuario.is_superuser:
            funcao = 'Administrador'
        elif perfil is not None:
            funcao = NOME_FUNCAO.get(perfil.papel, perfil.get_papel_display())
        else:
            funcao = ''
        pessoas.append({
            'usuario': usuario,
            'nome': _nome(usuario),
            'funcao': funcao,
            'dentista': perfil.dentista if perfil else None,
            'troca_pendente': bool(perfil and perfil.deve_trocar_senha),
            'editavel': not usuario.is_superuser and usuario.pk != request.user.pk,
        })
    pessoas.sort(key=lambda pessoa: (not pessoa['usuario'].is_active, pessoa['nome'].lower()))

    from locacao.relacoes import relacoes_de_locacao

    alugueis, donas = relacoes_de_locacao()
    titulares, locatarias = [], []
    for dentista in dentistas:
        if dentista.eh_locataria:
            dentista.donas = donas.get(dentista.pk, [])
            dentista.dias = '; '.join(
                turno.rotulo_curto()
                for turno in sorted(dentista.turnos.all(), key=lambda t: (t.dia_semana, t.hora_inicio))
            )
            locatarias.append(dentista)
        else:
            dentista.alugueis = alugueis.get(dentista.pk, [])
            titulares.append(dentista)
    return render(request, 'core/equipe.html', {
        'titulares': titulares,
        'locatarias': locatarias,
        'pessoas': pessoas,
    })


@sensitive_post_parameters('senha', 'confirmar_senha')
@require_http_methods(['GET', 'POST'])
@exige_financeiro
def novo_funcionario(request):
    if request.method == 'POST':
        form = NovoFuncionarioForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            partes = dados['nome'].strip().split(' ', 1)
            with transaction.atomic():
                usuario = User.objects.create_user(
                    username=dados['usuario'],
                    password=dados['senha'],
                    first_name=partes[0][:150],
                    last_name=(partes[1] if len(partes) > 1 else '')[:150],
                )
                PerfilUsuario.objects.create(
                    usuario=usuario,
                    papel=dados['funcao'],
                    dentista=dados['dentista'],
                    deve_trocar_senha=True,
                )
            logger.info(
                'Equipe: %s criou o acesso %s (%s).',
                request.user.get_username(), usuario.username, dados['funcao'],
            )
            messages.success(
                request,
                f'Acesso de {_nome(usuario)} criado. Entregue a ela o nome '
                f'“{usuario.username}” e a senha provisória. No primeiro acesso, '
                'o sistema pede para criar uma senha própria.',
            )
            return redirect('core:equipe')
    else:
        inicial = {}
        if request.GET.get('funcao') in NOME_FUNCAO:
            inicial['funcao'] = request.GET['funcao']
        dentista_id = request.GET.get('dentista', '')
        if dentista_id.isdigit():
            inicial['dentista'] = _dentistas_ativas().filter(pk=dentista_id).first()
            if inicial['dentista'] is not None:
                inicial['nome'] = inicial['dentista'].nome_completo
        form = NovoFuncionarioForm(initial=inicial)
    return render(request, 'core/form_funcionario.html', {'form': form})


@sensitive_post_parameters('senha', 'confirmar_senha')
@require_http_methods(['GET', 'POST'])
@exige_financeiro
def editar_funcionario(request, pk):
    usuario = get_object_or_404(User.objects.select_related('perfil'), pk=pk)
    # Administradores e a própria conta não são mexidos por esta tela.
    if usuario.is_superuser or usuario.pk == request.user.pk:
        raise PermissionDenied
    perfil = getattr(usuario, 'perfil', None)
    inicial = {
        'nome': _nome(usuario) if usuario.get_full_name() else '',
        'funcao': perfil.papel if perfil else None,
        'dentista': perfil.dentista if perfil else None,
        'modo_simples': perfil.modo_simples if perfil else False,
    }
    form = EditarFuncionarioForm(initial=inicial)
    form_senha = SenhaProvisoriaForm(usuario=usuario)
    acao = request.POST.get('acao') if request.method == 'POST' else None

    if acao == 'dados':
        form = EditarFuncionarioForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            partes = dados['nome'].strip().split(' ', 1)
            with transaction.atomic():
                usuario.first_name = partes[0][:150]
                usuario.last_name = (partes[1] if len(partes) > 1 else '')[:150]
                usuario.save(update_fields=['first_name', 'last_name'])
                perfil, _ = PerfilUsuario.objects.get_or_create(
                    usuario=usuario,
                    defaults={'papel': dados['funcao'], 'dentista': dados['dentista']},
                )
                perfil.papel = dados['funcao']
                perfil.dentista = dados['dentista']
                perfil.modo_simples = dados['modo_simples']
                perfil.save(update_fields=['papel', 'dentista', 'modo_simples'])
            logger.info(
                'Equipe: %s alterou os dados de %s.', request.user.get_username(), usuario.username,
            )
            messages.success(request, f'Dados de {_nome(usuario)} salvos.')
            return redirect('core:equipe')
    elif acao == 'senha':
        form_senha = SenhaProvisoriaForm(request.POST, usuario=usuario)
        if form_senha.is_valid():
            with transaction.atomic():
                usuario.set_password(form_senha.cleaned_data['senha'])
                usuario.save(update_fields=['password'])
                if perfil is not None:
                    perfil.deve_trocar_senha = True
                    perfil.save(update_fields=['deve_trocar_senha'])
            logger.info(
                'Equipe: %s definiu senha provisória para %s.',
                request.user.get_username(), usuario.username,
            )
            messages.success(
                request,
                f'Senha provisória de {_nome(usuario)} trocada. No próximo acesso, '
                'o sistema pede para ela criar uma senha própria.',
            )
            return redirect('core:equipe')
    elif acao in ('desligar', 'religar'):
        usuario.is_active = acao == 'religar'
        usuario.save(update_fields=['is_active'])
        logger.info(
            'Equipe: %s %s o acesso de %s.', request.user.get_username(),
            'religou' if usuario.is_active else 'desligou', usuario.username,
        )
        if usuario.is_active:
            messages.success(request, f'Acesso de {_nome(usuario)} religado.')
        else:
            messages.success(
                request,
                f'Acesso de {_nome(usuario)} desligado. Ela não entra mais no sistema; '
                'o histórico fica guardado.',
            )
        return redirect('core:equipe')

    return render(request, 'core/editar_funcionario.html', {
        'usuario_editado': usuario,
        'nome': _nome(usuario),
        'perfil': perfil,
        'form': form,
        'form_senha': form_senha,
    })
