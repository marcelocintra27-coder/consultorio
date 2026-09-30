"""Relatório de atividade por funcionária e por dia, só para o administrador."""
import csv
from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django import forms

from .models import (
    AuditoriaConsulta,
    AuditoriaPaciente,
    AtividadeDiaria,
    DigitalizacaoFicha,
    RegistroAcesso,
)
from .permissoes import usuario_e_administrador

ACOES_ALTERACAO = {
    AuditoriaPaciente.Acao.ALTERADO,
    AuditoriaPaciente.Acao.DESATIVADO,
    AuditoriaPaciente.Acao.REATIVADO,
}


class FiltroAtividadeForm(forms.Form):
    data_inicial = forms.DateField(
        label='De',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    data_final = forms.DateField(
        label='Até',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    usuaria = forms.ModelChoiceField(
        label='Funcionária',
        required=False,
        queryset=User.objects.order_by('username'),
        empty_label='Todas',
    )


def _exige_administrador(request):
    if not usuario_e_administrador(request.user):
        raise PermissionDenied


def _periodo_padrao():
    hoje = timezone.localdate()
    return hoje - timedelta(days=29), hoje


def _filtro(request):
    inicio_padrao, fim_padrao = _periodo_padrao()
    form = FiltroAtividadeForm(
        request.GET or None,
        initial={'data_inicial': inicio_padrao, 'data_final': fim_padrao},
    )
    if form.is_valid():
        data_inicial = form.cleaned_data.get('data_inicial') or inicio_padrao
        data_final = form.cleaned_data.get('data_final') or fim_padrao
        usuaria = form.cleaned_data.get('usuaria')
    else:
        data_inicial, data_final, usuaria = inicio_padrao, fim_padrao, None
    if data_final < data_inicial:
        form.add_error('data_final', 'A data final não pode ser anterior à inicial.')
        return form, data_inicial, data_final, usuaria, False
    return form, data_inicial, data_final, usuaria, True


def _janela(data_inicial, data_final):
    fuso = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(data_inicial, time.min), fuso)
    fim = timezone.make_aware(
        datetime.combine(data_final + timedelta(days=1), time.min), fuso,
    )
    return inicio, fim


def _dia_local(instante):
    return timezone.localtime(instante).date()


def _novo_bucket(usuario_id, dia):
    return {
        'usuario_id': usuario_id,
        'data': dia,
        'primeira': None,
        'ultima': None,
        'entradas': 0,
        'tentativas': 0,
        'pacientes_cadastrados': 0,
        'pacientes_alterados': 0,
        'consultas': 0,
        'fotos': 0,
    }


def _bucket(buckets, usuario_id, dia, data_inicial, data_final):
    if dia < data_inicial or dia > data_final:
        return None
    chave = (usuario_id, dia)
    if chave not in buckets:
        buckets[chave] = _novo_bucket(usuario_id, dia)
    return buckets[chave]


def linhas_do_relatorio(data_inicial, data_final, usuaria=None):
    inicio, fim = _janela(data_inicial, data_final)
    buckets = {}
    atividades = AtividadeDiaria.objects.filter(
        data__gte=data_inicial, data__lte=data_final,
    )
    if usuaria is not None:
        atividades = atividades.filter(usuario=usuaria)
    for item in atividades:
        linha = _bucket(buckets, item.usuario_id, item.data, data_inicial, data_final)
        linha['primeira'] = item.primeira_atividade
        linha['ultima'] = item.ultima_atividade

    acessos = RegistroAcesso.objects.filter(criado_em__gte=inicio, criado_em__lt=fim)
    if usuaria is not None:
        acessos = acessos.filter(usuario=usuaria)
    for acesso in acessos.exclude(tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU):
        if acesso.usuario_id is None:
            continue
        linha = _bucket(
            buckets, acesso.usuario_id, _dia_local(acesso.criado_em),
            data_inicial, data_final,
        )
        if linha is None:
            continue
        if acesso.tipo == RegistroAcesso.Tipo.ENTROU:
            linha['entradas'] += 1

    usuarios_por_nome = {
        usuario.username: usuario.pk
        for usuario in User.objects.all().only('id', 'username')
    }
    falhas = RegistroAcesso.objects.filter(
        criado_em__gte=inicio,
        criado_em__lt=fim,
        tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU,
    )
    nome_escolhido = usuaria.username if usuaria is not None else None
    for falha in falhas:
        if nome_escolhido is not None and falha.usuario_digitado != nome_escolhido:
            continue
        usuario_id = usuarios_por_nome.get(falha.usuario_digitado)
        if usuario_id is None:
            continue
        linha = _bucket(
            buckets, usuario_id, _dia_local(falha.criado_em),
            data_inicial, data_final,
        )
        if linha is not None:
            linha['tentativas'] += 1

    pacientes = AuditoriaPaciente.objects.filter(criado_em__gte=inicio, criado_em__lt=fim)
    if usuaria is not None:
        pacientes = pacientes.filter(usuario=usuaria)
    for item in pacientes:
        linha = _bucket(
            buckets, item.usuario_id, _dia_local(item.criado_em),
            data_inicial, data_final,
        )
        if linha is None:
            continue
        if item.acao == AuditoriaPaciente.Acao.CRIADO:
            linha['pacientes_cadastrados'] += 1
        elif item.acao in ACOES_ALTERACAO:
            linha['pacientes_alterados'] += 1

    consultas = AuditoriaConsulta.objects.filter(cadastrado_em__gte=inicio, cadastrado_em__lt=fim)
    if usuaria is not None:
        consultas = consultas.filter(usuario=usuaria)
    for item in consultas:
        linha = _bucket(
            buckets, item.usuario_id, _dia_local(item.cadastrado_em),
            data_inicial, data_final,
        )
        if linha is not None:
            linha['consultas'] += 1

    fotos = DigitalizacaoFicha.objects.filter(
        criado_em__gte=inicio, criado_em__lt=fim, digitalizado_por__isnull=False,
    )
    if usuaria is not None:
        fotos = fotos.filter(digitalizado_por=usuaria)
    for item in fotos:
        linha = _bucket(
            buckets, item.digitalizado_por_id, _dia_local(item.criado_em),
            data_inicial, data_final,
        )
        if linha is not None:
            linha['fotos'] += 1

    usuarios = User.objects.in_bulk(linha['usuario_id'] for linha in buckets.values())
    linhas = []
    for linha in buckets.values():
        usuario = usuarios.get(linha['usuario_id'])
        if usuario is None:
            continue
        linha['usuario'] = usuario
        linhas.append(linha)
    linhas.sort(key=lambda item: item['usuario'].username)
    linhas.sort(key=lambda item: item['data'], reverse=True)
    return linhas


def _texto_foto(acesso):
    ficha = acesso.digitalizacao
    if ficha is None:
        return 'Abriu foto de ficha digitalizada'
    if ficha.paciente_id:
        paciente = ficha.paciente.nome_completo
    else:
        paciente = 'sem paciente'
    return f'ficha nº {ficha.pk} — {paciente} — {ficha.get_tipo_display()}'


def _texto_paciente(acao, nome):
    verbos = {
        AuditoriaPaciente.Acao.CRIADO: 'Cadastrou o paciente',
        AuditoriaPaciente.Acao.ALTERADO: 'Alterou o paciente',
        AuditoriaPaciente.Acao.DESATIVADO: 'Desativou o paciente',
        AuditoriaPaciente.Acao.REATIVADO: 'Reativou o paciente',
    }
    return f'{verbos.get(acao, "Alterou o paciente")} {nome}'


def eventos_do_dia(usuario, dia):
    inicio, fim = _janela(dia, dia)
    eventos = []
    for acesso in RegistroAcesso.objects.filter(
        criado_em__gte=inicio, criado_em__lt=fim, usuario=usuario,
    ).select_related('digitalizacao__paciente'):
        if acesso.tipo == RegistroAcesso.Tipo.ENTROU:
            texto = 'Entrou no sistema'
        elif acesso.tipo == RegistroAcesso.Tipo.SAIU:
            texto = 'Saiu do sistema'
        elif acesso.tipo == RegistroAcesso.Tipo.ABRIU_FOTO:
            texto = _texto_foto(acesso)
        else:
            texto = 'Senha incorreta'
        eventos.append((acesso.criado_em, texto))
    for falha in RegistroAcesso.objects.filter(
        criado_em__gte=inicio,
        criado_em__lt=fim,
        tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU,
        usuario_digitado=usuario.username,
    ):
        eventos.append((falha.criado_em, 'Senha incorreta'))
    for item in AuditoriaPaciente.objects.filter(
        criado_em__gte=inicio, criado_em__lt=fim, usuario=usuario,
    ).select_related('paciente'):
        eventos.append((
            item.criado_em, _texto_paciente(item.acao, item.paciente.nome_completo),
        ))
    for item in AuditoriaConsulta.objects.filter(
        cadastrado_em__gte=inicio, cadastrado_em__lt=fim, usuario=usuario,
    ):
        eventos.append((item.cadastrado_em, item.descricao))
    for item in DigitalizacaoFicha.objects.filter(
        criado_em__gte=inicio, criado_em__lt=fim, digitalizado_por=usuario,
    ).select_related('paciente'):
        nome = item.paciente.nome_completo if item.paciente_id else 'sem paciente'
        eventos.append((item.criado_em, f'Enviou foto de ficha de {nome}'))
    eventos.sort(key=lambda item: item[0])
    return [{'quando': quando, 'texto': texto} for quando, texto in eventos]


def _csv(linhas):
    saida = StringIO()
    saida.write('\ufeff')
    writer = csv.writer(saida)
    writer.writerow([
        'Funcionária', 'Dia', 'Primeira atividade', 'Última atividade',
        'Entradas', 'Senha incorreta', 'Pacientes cadastrados',
        'Pacientes alterados', 'Ações em consultas', 'Fotos enviadas',
    ])
    for linha in linhas:
        nome = linha['usuario'].get_full_name() or linha['usuario'].username
        writer.writerow([
            nome,
            linha['data'].strftime('%d/%m/%Y'),
            _hora(linha['primeira']),
            _hora(linha['ultima']),
            linha['entradas'],
            linha['tentativas'],
            linha['pacientes_cadastrados'],
            linha['pacientes_alterados'],
            linha['consultas'],
            linha['fotos'],
        ])
    return saida.getvalue()


def _hora(instante):
    if instante is None:
        return ''
    return timezone.localtime(instante).strftime('%H:%M')


@require_GET
def relatorio_atividade(request):
    _exige_administrador(request)
    form, data_inicial, data_final, usuaria, ok = _filtro(request)
    linhas = linhas_do_relatorio(data_inicial, data_final, usuaria) if ok else []
    return render(request, 'core/relatorio_atividade.html', {
        'form': form,
        'linhas': linhas,
        'data_inicial': data_inicial,
        'data_final': data_final,
        'usuaria': usuaria,
    })


@require_GET
def relatorio_atividade_csv(request):
    _exige_administrador(request)
    _form, data_inicial, data_final, usuaria, ok = _filtro(request)
    linhas = linhas_do_relatorio(data_inicial, data_final, usuaria) if ok else []
    resposta = HttpResponse(_csv(linhas), content_type='text/csv; charset=utf-8')
    resposta['Content-Disposition'] = (
        f'attachment; filename="atividade-{data_inicial.isoformat()}-'
        f'{data_final.isoformat()}.csv"'
    )
    return resposta


@require_GET
def relatorio_atividade_dia(request, usuario_id, dia):
    _exige_administrador(request)
    usuaria = get_object_or_404(User, pk=usuario_id)
    try:
        dia = datetime.strptime(dia, '%Y-%m-%d').date()
    except ValueError:
        raise Http404
    consulta = request.GET.urlencode()
    voltar = reverse('core:relatorio_atividade')
    if consulta:
        voltar = f'{voltar}?{consulta}'
    return render(request, 'core/relatorio_atividade_dia.html', {
        'usuaria': usuaria,
        'dia': dia,
        'eventos': eventos_do_dia(usuaria, dia),
        'voltar': voltar,
    })
