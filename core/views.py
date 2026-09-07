from decimal import Decimal
import json
from datetime import datetime

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from locacao.models import Dentista

from .tabela_uniodonto import FATOR_US_UNIODONTO
from .models import (
    Convenio,
    Paciente,
    Consulta,
    MaterialUsado,
    Procedimento,
    PrecoProcedimento,
    LancamentoAtendimento,
    AuditoriaConsulta,
    ProcedimentoUniodonto,
)
from .forms import (
    ConvenioForm,
    PacienteForm,
    MaterialUsadoForm,
    ConsultaForm,
    StatusConsultaForm,
    ProcedimentoForm,
    LancamentoForm,
    ComplementarDentistaForm,
)
from .permissoes import (
    exige_financeiro,
    usuario_pode_financeiro,
    usuario_pode_lancar,
    usuario_pode_complementar_dentista,
    usuario_pode_editar_catalogo,
    usuario_e_administrador,
    dentista_do_usuario,
)

def inicio(request):
    return render(request, 'core/inicio.html')


@login_not_required
def sair(request):
    logout(request)
    return redirect('entrar')

def listar_pacientes(request):
    termo = request.GET.get('q', '').strip()
    pacientes = Paciente.objects.filter(ativo=True)
    if termo:
        pacientes = pacientes.filter(nome_completo__icontains=termo)
    pacientes = pacientes.order_by('nome_completo')
    return render(request, 'core/listar_pacientes.html', {'pacientes': pacientes, 'termo': termo})

def cadastrar_paciente(request):
    if request.method == 'POST':
        form = PacienteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('core:listar_pacientes')
    else:
        form = PacienteForm()
    return render(request, 'core/form_paciente.html', {
        'form': form,
        'titulo': 'Cadastrar Paciente',
    })


def editar_paciente(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if request.method == 'POST':
        form = PacienteForm(request.POST, instance=paciente)
        if form.is_valid():
            form.save()
            return redirect('core:listar_pacientes')
    else:
        form = PacienteForm(instance=paciente)
    return render(request, 'core/form_paciente.html', {
        'form': form,
        'titulo': 'Editar Paciente',
    })


@exige_financeiro
def listar_convenios(request):
    termo = request.GET.get('q', '').strip()
    convenios = Convenio.objects.filter(ativo=True)
    if termo:
        convenios = convenios.filter(nome__icontains=termo)
    convenios = convenios.order_by('nome')
    return render(request, 'core/listar_convenios.html', {
        'convenios': convenios,
        'termo': termo,
    })


@exige_financeiro
def cadastrar_convenio(request):
    if request.method == 'POST':
        form = ConvenioForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('core:listar_convenios')
    else:
        form = ConvenioForm()
    return render(request, 'core/form_convenio.html', {
        'form': form,
        'titulo': 'Cadastrar Convênio',
    })


@exige_financeiro
def editar_convenio(request, pk):
    convenio = get_object_or_404(Convenio, pk=pk, ativo=True)
    if request.method == 'POST':
        form = ConvenioForm(request.POST, instance=convenio)
        if form.is_valid():
            form.save()
            return redirect('core:listar_convenios')
    else:
        form = ConvenioForm(instance=convenio)
    return render(request, 'core/form_convenio.html', {
        'form': form,
        'titulo': 'Editar Convênio',
    })


@exige_financeiro
def listar_tabela_uniodonto(request):
    termo = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    itens = ProcedimentoUniodonto.objects.filter(ativo=True)
    if termo:
        itens = itens.filter(Q(codigo__icontains=termo) | Q(nome__icontains=termo))
    if categoria:
        itens = itens.filter(categoria=categoria)
    itens = itens.order_by('categoria', 'nome')
    return render(request, 'core/listar_tabela_uniodonto.html', {
        'itens': itens,
        'termo': termo,
        'categoria': categoria,
        'categorias': ProcedimentoUniodonto.Categoria.choices,
        'fator_us': FATOR_US_UNIODONTO,
        'total': ProcedimentoUniodonto.objects.filter(ativo=True).count(),
    })


def listar_consultas(request):
    data_str = request.GET.get('data', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = (
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio', 'dentista')
        .order_by('hora_inicio')
    )
    return render(request, 'core/listar_consultas.html', {
        'consultas': consultas,
        'data': data,
    })


@exige_financeiro
@require_POST
def marcar_consulta_paga(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    acao = request.POST.get('acao')
    if acao == 'marcar':
        consulta.pago = True
        consulta.save(update_fields=['pago'])
    elif acao == 'desmarcar':
        consulta.pago = False
        consulta.save(update_fields=['pago'])
    return redirect(
        f"{reverse('core:listar_consultas')}?data={consulta.data.isoformat()}"
    )


@exige_financeiro
def listar_pagamentos_consulta(request):
    data_str = request.GET.get('data', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = (
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio')
        .order_by('hora_inicio')
    )
    return render(request, 'core/listar_pagamentos_consulta.html', {
        'consultas': consultas,
        'data': data,
        'formas_pagamento': Consulta.FormaPagamento.choices,
    })


@exige_financeiro
@require_POST
def salvar_forma_pagamento(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    forma = (request.POST.get('forma_pagamento') or '').strip()
    opcoes = {choice[0] for choice in Consulta.FormaPagamento.choices}
    if forma == '' or forma in opcoes:
        consulta.forma_pagamento = forma
        consulta.save(update_fields=['forma_pagamento'])
    return redirect(
        f"{reverse('core:listar_pagamentos_consulta')}?data={consulta.data.isoformat()}"
    )


@exige_financeiro
def listar_materiais_dia(request):
    data_str = request.GET.get('data', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = (
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio', 'dentista')
        .prefetch_related('materiais')
        .order_by('hora_inicio')
    )
    for consulta in consultas:
        consulta.pode_lancar = usuario_pode_lancar(request.user, consulta)
    return render(request, 'core/listar_materiais_dia.html', {
        'consultas': consultas,
        'data': data,
    })


@exige_financeiro
def materiais_consulta(request, pk):
    consulta = get_object_or_404(
        Consulta.objects.select_related('paciente__convenio', 'dentista'),
        pk=pk,
    )
    if not usuario_pode_lancar(request.user, consulta):
        raise PermissionDenied
    materiais = consulta.materiais.all()
    if request.method == 'POST':
        form = MaterialUsadoForm(request.POST)
        if form.is_valid():
            material = form.save(commit=False)
            material.consulta = consulta
            material.save()
            return redirect('core:materiais_consulta', pk=consulta.pk)
    else:
        form = MaterialUsadoForm()
    return render(request, 'core/materiais_consulta.html', {
        'consulta': consulta,
        'materiais': materiais,
        'form': form,
    })


@exige_financeiro
def editar_material_usado(request, pk):
    material = get_object_or_404(
        MaterialUsado.objects.select_related('consulta__paciente__convenio'),
        pk=pk,
    )
    consulta = material.consulta
    if not usuario_pode_lancar(request.user, consulta):
        raise PermissionDenied
    if request.method == 'POST':
        form = MaterialUsadoForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            return redirect('core:materiais_consulta', pk=consulta.pk)
    else:
        form = MaterialUsadoForm(instance=material)
    return render(request, 'core/form_material.html', {
        'form': form,
        'consulta': consulta,
        'titulo': 'Editar Material',
    })


@exige_financeiro
@require_POST
def excluir_material_usado(request, pk):
    material = get_object_or_404(MaterialUsado, pk=pk)
    if not usuario_pode_lancar(request.user, material.consulta):
        raise PermissionDenied
    consulta_id = material.consulta_id
    material.delete()
    return redirect('core:materiais_consulta', pk=consulta_id)


def _registrar_auditoria(consulta, usuario, descricao):
    AuditoriaConsulta.objects.create(
        consulta=consulta,
        usuario=usuario,
        descricao=descricao,
    )


def agendar_consulta(request):
    if request.method == 'POST':
        form = ConsultaForm(request.POST)
        if form.is_valid():
            consulta = form.save(commit=False)
            consulta.eh_legado = False
            consulta.save()
            return redirect(
                f"{reverse('core:listar_consultas')}?data={consulta.data.isoformat()}"
            )
    else:
        form = ConsultaForm(initial={'data': timezone.localdate()})
    return render(request, 'core/form_consulta.html', {
        'form': form,
        'titulo': 'Agendar consulta',
    })


def ficha_consulta(request, pk):
    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente__convenio',
            'dentista',
            'dentista_complementado_por',
        ).prefetch_related('lancamentos__convenio', 'lancamentos__cadastrado_por'),
        pk=pk,
    )
    pode_financeiro = usuario_pode_financeiro(request.user)
    pode_lancar = usuario_pode_lancar(request.user, consulta)
    pode_complementar = usuario_pode_complementar_dentista(request.user, consulta)

    status_form = StatusConsultaForm(instance=consulta)
    complementar_form = None
    bound = getattr(request, '_lancamento_form', None)
    if bound is not None:
        lancamento_form = bound
    elif pode_lancar and consulta.dentista_id:
        lancamento_form = LancamentoForm(dentista=consulta.dentista)
        if consulta.paciente.convenio_id:
            lancamento_form.fields['percentual_desconto'].initial = (
                consulta.paciente.convenio.percentual_desconto
            )
        if consulta.eh_legado:
            lancamento_form.fields['tipo'].initial = LancamentoAtendimento.Tipo.AJUSTE
    else:
        lancamento_form = None
    bound_comp = getattr(request, '_complementar_form', None)
    if bound_comp is not None:
        complementar_form = bound_comp
    elif pode_complementar and not consulta.dentista_id:
        complementar_form = ComplementarDentistaForm()

    precos = {}
    sugestoes_desconto = {}
    if lancamento_form:
        for proc in lancamento_form.fields['procedimento'].queryset.prefetch_related(
            'precos'
        ):
            precos[str(proc.pk)] = {
                '': str(
                    next(
                        (p.valor for p in proc.precos.all() if p.convenio_id is None),
                        '',
                    )
                )
            }
            for preco in proc.precos.all():
                if preco.convenio_id:
                    precos[str(proc.pk)][str(preco.convenio_id)] = str(preco.valor)
        for conv in Convenio.objects.catalogo_dentista():
            sugestoes_desconto[str(conv.pk)] = str(conv.percentual_desconto)

    return render(request, 'core/ficha_consulta.html', {
        'consulta': consulta,
        'status_form': status_form,
        'lancamento_form': lancamento_form,
        'complementar_form': complementar_form,
        'pode_financeiro': pode_financeiro,
        'pode_lancar': pode_lancar,
        'pode_complementar': pode_complementar,
        'precos_json': json.dumps(precos),
        'sugestoes_desconto_json': json.dumps(sugestoes_desconto),
        'auditorias': consulta.auditorias.select_related('usuario')[:20]
        if pode_financeiro
        else [],
    })


@require_POST
def alterar_status_consulta(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    form = StatusConsultaForm(request.POST, instance=consulta)
    if form.is_valid():
        form.save()
        if consulta.eh_legado:
            _registrar_auditoria(
                consulta,
                request.user,
                f'status alterado para {consulta.get_status_display()}',
            )
    return redirect('core:ficha_consulta', pk=consulta.pk)


@exige_financeiro
@require_POST
def lancar_atendimento(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    if not usuario_pode_lancar(request.user, consulta):
        raise PermissionDenied
    if not consulta.dentista_id:
        raise PermissionDenied
    form = LancamentoForm(request.POST, dentista=consulta.dentista)
    if not form.is_valid():
        request._lancamento_form = form
        return ficha_consulta(request, pk)
    dados = form.cleaned_data
    procedimento = dados['procedimento']
    convenio = dados['convenio']
    particular = convenio is None
    LancamentoAtendimento.objects.create(
        consulta=consulta,
        procedimento=procedimento,
        nome_procedimento=procedimento.nome,
        dentista=consulta.dentista,
        convenio=convenio,
        particular=particular,
        valor_tabela=dados['valor_tabela'],
        percentual_desconto=dados['percentual_desconto'],
        valor_final=dados['valor_final'],
        tipo=dados['tipo'],
        cadastrado_por=request.user,
    )
    if consulta.eh_legado:
        _registrar_auditoria(
            consulta,
            request.user,
            f'lançamento {dados["tipo"]}: {procedimento.nome}',
        )
    return redirect('core:ficha_consulta', pk=consulta.pk)


@exige_financeiro
@require_POST
def complementar_dentista(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    if not usuario_pode_complementar_dentista(request.user, consulta):
        raise PermissionDenied
    if consulta.dentista_id:
        return redirect('core:ficha_consulta', pk=consulta.pk)
    form = ComplementarDentistaForm(request.POST)
    if not form.is_valid():
        request._complementar_form = form
        return ficha_consulta(request, pk)
    dentista = form.cleaned_data['dentista']
    valor_antes = consulta.valor_historico
    consulta.dentista = dentista
    consulta.dentista_complementado_em = timezone.now()
    consulta.dentista_complementado_por = request.user
    consulta.save(
        update_fields=[
            'dentista',
            'dentista_complementado_em',
            'dentista_complementado_por',
        ]
    )
    _registrar_auditoria(
        consulta,
        request.user,
        f'dentista complementar: {dentista.nome_completo}',
    )
    consulta.refresh_from_db()
    if consulta.valor_historico != valor_antes:
        consulta.valor_historico = valor_antes
        consulta.save(update_fields=['valor_historico'])
    return redirect('core:ficha_consulta', pk=consulta.pk)


def _dentista_catalogo(request):
    if usuario_e_administrador(request.user):
        dentista_id = request.GET.get('dentista') or request.POST.get('dentista_id')
        if dentista_id:
            return get_object_or_404(Dentista, pk=dentista_id, ativo=True)
        return Dentista.objects.filter(ativo=True).order_by('nome_completo').first()
    return dentista_do_usuario(request.user)


@exige_financeiro
def listar_procedimentos(request):
    dentista = _dentista_catalogo(request)
    if dentista is None:
        raise PermissionDenied
    if not usuario_pode_editar_catalogo(request.user, dentista):
        raise PermissionDenied
    procedimentos = (
        Procedimento.objects.filter(dentista=dentista)
        .prefetch_related('precos__convenio')
        .order_by('nome')
    )
    return render(request, 'core/listar_procedimentos.html', {
        'dentista': dentista,
        'procedimentos': procedimentos,
        'dentistas': Dentista.objects.filter(ativo=True).order_by('nome_completo')
        if usuario_e_administrador(request.user)
        else None,
        'convenios': Convenio.objects.catalogo_dentista(),
    })


def _salvar_precos(request, procedimento):
    particular = (request.POST.get('preco_particular') or '').strip()
    if particular != '':
        PrecoProcedimento.objects.update_or_create(
            procedimento=procedimento,
            convenio=None,
            defaults={'valor': Decimal(particular)},
        )
    for convenio in Convenio.objects.catalogo_dentista():
        bruto = (request.POST.get(f'preco_convenio_{convenio.pk}') or '').strip()
        if bruto == '':
            continue
        PrecoProcedimento.objects.update_or_create(
            procedimento=procedimento,
            convenio=convenio,
            defaults={'valor': Decimal(bruto)},
        )


@exige_financeiro
def cadastrar_procedimento(request):
    dentista = _dentista_catalogo(request)
    if dentista is None or not usuario_pode_editar_catalogo(request.user, dentista):
        raise PermissionDenied
    if request.method == 'POST':
        form = ProcedimentoForm(request.POST)
        if form.is_valid():
            procedimento = form.save(commit=False)
            procedimento.dentista = dentista
            procedimento.save()
            _salvar_precos(request, procedimento)
            return redirect(
                f"{reverse('core:listar_procedimentos')}?dentista={dentista.pk}"
            )
    else:
        form = ProcedimentoForm()
    return render(request, 'core/form_procedimento.html', {
        'form': form,
        'dentista': dentista,
        'convenios': Convenio.objects.catalogo_dentista(),
        'precos': {'particular': ''},
        'titulo': 'Cadastrar procedimento',
    })


@exige_financeiro
def editar_procedimento(request, pk):
    procedimento = get_object_or_404(
        Procedimento.objects.select_related('dentista'),
        pk=pk,
    )
    if not usuario_pode_editar_catalogo(request.user, procedimento.dentista):
        raise PermissionDenied
    if request.method == 'POST':
        form = ProcedimentoForm(request.POST, instance=procedimento)
        if form.is_valid():
            form.save()
            _salvar_precos(request, procedimento)
            return redirect(
                f"{reverse('core:listar_procedimentos')}?dentista={procedimento.dentista_id}"
            )
    else:
        form = ProcedimentoForm(instance=procedimento)
    precos = {'particular': ''}
    for preco in procedimento.precos.all():
        if preco.convenio_id is None:
            precos['particular'] = preco.valor
        else:
            precos[str(preco.convenio_id)] = preco.valor
    return render(request, 'core/form_procedimento.html', {
        'form': form,
        'dentista': procedimento.dentista,
        'convenios': Convenio.objects.catalogo_dentista(),
        'precos': precos,
        'titulo': 'Editar procedimento',
    })

