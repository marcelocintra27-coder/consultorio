from decimal import Decimal
import json
from datetime import datetime, timedelta


from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from locacao.models import Dentista

from .assinatura import gravar_assinatura_manuscrita
from .anamnese import (
    SAUDE_BUCAL,
    SAUDE_CONDICOES,
    TEXTO_DECLARACAO_ANAMNESE,
    eh_menor_de_idade,
    renovar_token,
    rotulos_checklist,
    sincronizar_paciente,
    texto_para_hash,
)
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
    RepasseUniodonto,
    soma_producao_uniodonto,
    AssinaturaEletronica,
    FichaCadastroAnamnese,
)
from .forms import (
    ConvenioForm,
    PacienteForm,
    MaterialUsadoForm,
    ConsultaForm,
    StatusConsultaForm,
    ProcedimentoForm,
    LancamentoForm,
    LancamentoUniodontoForm,
    ComplementarDentistaForm,
    RepasseUniodontoForm,
    AssinaturaTesteForm,
    FichaAnamneseForm,
    AssinaturaDentistaAnamneseForm,
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
        'paciente': paciente,
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


def _parse_competencia(mes_str):
    try:
        return datetime.strptime(mes_str, '%Y-%m').date().replace(day=1)
    except (TypeError, ValueError):
        return None


def _dentista_repasse_request(request):
    if usuario_e_administrador(request.user):
        bruto = request.GET.get('dentista') or request.POST.get('dentista')
        if bruto:
            return get_object_or_404(Dentista, pk=bruto, ativo=True)
        return None
    dentista = dentista_do_usuario(request.user)
    if dentista is None:
        raise PermissionDenied
    return dentista


@exige_financeiro
def listar_repasses_uniodonto(request):
    admin = usuario_e_administrador(request.user)
    dentista_user = dentista_do_usuario(request.user)
    if not admin and dentista_user is None:
        raise PermissionDenied
    mes_str = request.GET.get('mes', '').strip()
    competencia = _parse_competencia(mes_str) if mes_str else None
    extratos = RepasseUniodonto.objects.select_related('dentista')
    dentista_filtro = None
    if admin:
        dentista_id = request.GET.get('dentista', '').strip()
        if dentista_id:
            dentista_filtro = get_object_or_404(Dentista, pk=dentista_id, ativo=True)
            extratos = extratos.filter(dentista=dentista_filtro)
    else:
        extratos = extratos.filter(dentista=dentista_user)
    if competencia:
        extratos = extratos.filter(competencia=competencia)
    return render(request, 'core/listar_repasses_uniodonto.html', {
        'extratos': extratos,
        'mes_input': mes_str,
        'dentista_filtro': dentista_filtro,
        'dentistas': Dentista.objects.filter(ativo=True).order_by('nome_completo')
        if admin
        else None,
    })


def _contexto_form_repasse(request, form, sugerido, titulo, extrato=None):
    return {
        'form': form,
        'sugerido': sugerido,
        'titulo': titulo,
        'extrato': extrato,
        'liquido_calculado': extrato.liquido_calculado if extrato else None,
        'diferenca': extrato.diferenca() if extrato else None,
        'url_sugestao': reverse('core:sugestao_producao_uniodonto'),
    }


@exige_financeiro
def cadastrar_repasse_uniodonto(request):
    admin = usuario_e_administrador(request.user)
    dentista_fixo = None if admin else dentista_do_usuario(request.user)
    if not admin and dentista_fixo is None:
        raise PermissionDenied
    dentista = _dentista_repasse_request(request) or dentista_fixo
    competencia = _parse_competencia(
        request.GET.get('competencia') or request.POST.get('competencia', '')
    )
    if competencia is None:
        competencia = timezone.localdate().replace(day=1)
    sugerido = soma_producao_uniodonto(dentista, competencia)
    if request.method == 'POST':
        form = RepasseUniodontoForm(
            request.POST, dentista_fixo=dentista_fixo
        )
        if form.is_valid():
            extrato = form.save(commit=False)
            extrato.cadastrado_por = request.user
            extrato.save()
            return redirect('core:listar_repasses_uniodonto')
    else:
        iniciais = {
            'competencia': competencia.strftime('%Y-%m'),
            'producao_bruta': sugerido,
            'glosa': 0,
            'estorno': 0,
            'inss_retido': 0,
            'irrf_retido': 0,
        }
        if dentista:
            iniciais['dentista'] = dentista.pk
        form = RepasseUniodontoForm(
            initial=iniciais, dentista_fixo=dentista_fixo
        )
    return render(
        request,
        'core/form_repasse_uniodonto.html',
        _contexto_form_repasse(request, form, sugerido, 'Novo repasse Uniodonto'),
    )


@exige_financeiro
def editar_repasse_uniodonto(request, pk):
    extrato = get_object_or_404(
        RepasseUniodonto.objects.select_related('dentista'),
        pk=pk,
    )
    if not usuario_pode_editar_catalogo(request.user, extrato.dentista):
        raise PermissionDenied
    admin = usuario_e_administrador(request.user)
    dentista_fixo = None if admin else extrato.dentista
    sugerido = soma_producao_uniodonto(extrato.dentista, extrato.competencia)
    if request.method == 'POST':
        form = RepasseUniodontoForm(
            request.POST, instance=extrato, dentista_fixo=dentista_fixo
        )
        if form.is_valid():
            form.save()
            return redirect('core:listar_repasses_uniodonto')
    else:
        form = RepasseUniodontoForm(
            instance=extrato, dentista_fixo=dentista_fixo
        )
    return render(
        request,
        'core/form_repasse_uniodonto.html',
        _contexto_form_repasse(
            request, form, sugerido, 'Editar repasse Uniodonto', extrato
        ),
    )


@exige_financeiro
def sugestao_producao_uniodonto(request):
    dentista = _dentista_repasse_request(request)
    if dentista is None:
        return JsonResponse({'sugerido': '0.00'})
    if not usuario_pode_editar_catalogo(request.user, dentista):
        raise PermissionDenied
    competencia = _parse_competencia(request.GET.get('competencia', ''))
    if competencia is None:
        competencia = timezone.localdate().replace(day=1)
    sugerido = soma_producao_uniodonto(dentista, competencia)
    return JsonResponse({'sugerido': f'{sugerido:.2f}'})


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


def _usa_lancamento_uniodonto(consulta):
    convenio = consulta.paciente.convenio
    return bool(convenio and convenio.usa_tabela_oficial)


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
    usa_uniodonto = _usa_lancamento_uniodonto(consulta)
    bound = getattr(request, '_lancamento_form', None)
    if bound is not None:
        lancamento_form = bound
    elif pode_lancar and consulta.dentista_id:
        if usa_uniodonto:
            lancamento_form = LancamentoUniodontoForm()
            if consulta.eh_legado:
                lancamento_form.fields['tipo'].initial = (
                    LancamentoAtendimento.Tipo.AJUSTE
                )
        else:
            lancamento_form = LancamentoForm(dentista=consulta.dentista)
            if consulta.paciente.convenio_id:
                lancamento_form.fields['percentual_desconto'].initial = (
                    consulta.paciente.convenio.percentual_desconto
                )
            if consulta.eh_legado:
                lancamento_form.fields['tipo'].initial = (
                    LancamentoAtendimento.Tipo.AJUSTE
                )
    else:
        lancamento_form = None
    bound_comp = getattr(request, '_complementar_form', None)
    if bound_comp is not None:
        complementar_form = bound_comp
    elif pode_complementar and not consulta.dentista_id:
        complementar_form = ComplementarDentistaForm()

    precos = {}
    sugestoes_desconto = {}
    itens_uniodonto = {}
    if lancamento_form and usa_uniodonto:
        for item in lancamento_form.fields['procedimento_uniodonto'].queryset:
            itens_uniodonto[str(item.pk)] = {
                'codigo': item.codigo,
                'valor_us': str(item.valor_us),
                'valor_reais': str(item.valor_reais),
            }
    elif lancamento_form and 'procedimento' in lancamento_form.fields:
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
        'usa_lancamento_uniodonto': usa_uniodonto,
        'fator_us_uniodonto': FATOR_US_UNIODONTO,
        'precos_json': json.dumps(precos),
        'itens_uniodonto_json': json.dumps(itens_uniodonto),
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
    consulta = get_object_or_404(
        Consulta.objects.select_related('paciente__convenio', 'dentista'),
        pk=pk,
    )
    if not usuario_pode_lancar(request.user, consulta):
        raise PermissionDenied
    if not consulta.dentista_id:
        raise PermissionDenied
    if _usa_lancamento_uniodonto(consulta):
        form = LancamentoUniodontoForm(request.POST)
        if not form.is_valid():
            request._lancamento_form = form
            return ficha_consulta(request, pk)
        dados = form.cleaned_data
        item = dados['procedimento_uniodonto']
        LancamentoAtendimento.objects.create(
            consulta=consulta,
            procedimento=None,
            procedimento_uniodonto=item,
            nome_procedimento=item.nome,
            codigo_tuss=item.codigo,
            valor_us=item.valor_us,
            fator_us=item.fator_us,
            dentista=consulta.dentista,
            convenio=consulta.paciente.convenio,
            particular=False,
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
                f'lançamento {dados["tipo"]}: {item.codigo} — {item.nome}',
            )
        return redirect('core:ficha_consulta', pk=consulta.pk)
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


def _ip_do_pedido(request):
    return request.META.get('REMOTE_ADDR')


def teste_assinatura(request):
    if request.method == 'POST':
        form = AssinaturaTesteForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            paciente = dados.get('paciente')
            conteudo = '|'.join(
                [
                    AssinaturaEletronica.TipoDocumento.COMPONENTE_TESTE,
                    str(paciente.pk if paciente else 0),
                    dados['papel'],
                    dados['nome_assinante'],
                    dados.get('cpf_assinante') or '',
                ]
            )
            gravar_assinatura_manuscrita(
                tipo_documento=AssinaturaEletronica.TipoDocumento.COMPONENTE_TESTE,
                documento_id=paciente.pk if paciente else 0,
                papel=dados['papel'],
                nome_assinante=dados['nome_assinante'],
                imagem_data_url=dados['imagem_base64'],
                conteudo_para_hash=conteudo,
                paciente=paciente,
                cpf_assinante=dados.get('cpf_assinante') or '',
                usuario=request.user,
                ip=_ip_do_pedido(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            return redirect('core:teste_assinatura')
    else:
        form = AssinaturaTesteForm(
            initial={'nome_assinante': request.user.get_full_name() or request.user.username}
        )
    recentes = AssinaturaEletronica.objects.select_related('paciente', 'usuario')[:8]
    return render(request, 'core/form_assinatura_teste.html', {
        'form': form,
        'recentes': recentes,
        'titulo': 'Assinatura eletrônica (componente)',
    })


def ver_imagem_assinatura(request, pk):
    assinatura = get_object_or_404(AssinaturaEletronica, pk=pk)
    if not assinatura.imagem:
        raise PermissionDenied
    return FileResponse(assinatura.imagem.open('rb'), content_type='image/png')


def _ficha_aberta(paciente):
    return FichaCadastroAnamnese.objects.filter(
        paciente=paciente,
        status__in=[
            FichaCadastroAnamnese.Status.RASCUNHO,
            FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA,
        ],
    ).first()


def _criar_rascunho_anamnese(paciente, usuario):
    existente = _ficha_aberta(paciente)
    if existente:
        return existente
    return FichaCadastroAnamnese.objects.create(
        paciente=paciente,
        criado_por=usuario if usuario.is_authenticated else None,
        nome_completo=paciente.nome_completo,
        data_nascimento=paciente.data_nascimento,
        cpf=paciente.cpf,
        telefone=paciente.telefone,
        whatsapp=paciente.whatsapp or '',
        email=paciente.email or '',
        endereco=paciente.endereco or '',
        token_expira_em=timezone.now() + timedelta(days=14),
    )


def _assinaturas_da_ficha(ficha):
    return AssinaturaEletronica.objects.filter(
        tipo_documento=AssinaturaEletronica.TipoDocumento.ANAMNESE,
        documento_id=ficha.pk,
    )


def _gravar_assinatura_anamnese(
    request, ficha, papel, nome, cpf, data_url, usuario=None
):
    gravar_assinatura_manuscrita(
        tipo_documento=AssinaturaEletronica.TipoDocumento.ANAMNESE,
        documento_id=ficha.pk,
        papel=papel,
        nome_assinante=nome,
        imagem_data_url=data_url,
        conteudo_para_hash=texto_para_hash(ficha),
        paciente=ficha.paciente,
        cpf_assinante=cpf or '',
        usuario=usuario,
        ip=_ip_do_pedido(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def listar_fichas_anamnese(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    fichas = paciente.fichas_anamnese.all()
    ficha_aberta = _ficha_aberta(paciente)
    link_publico = ''
    if ficha_aberta and ficha_aberta.status == FichaCadastroAnamnese.Status.RASCUNHO:
        link_publico = request.build_absolute_uri(
            reverse('core:ficha_anamnese_publica', args=[ficha_aberta.token])
        )
    return render(request, 'core/listar_fichas_anamnese.html', {
        'paciente': paciente,
        'fichas': fichas,
        'ficha_aberta': ficha_aberta,
        'link_publico': link_publico,
    })


@require_POST
def nova_ficha_anamnese(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    ficha = _criar_rascunho_anamnese(paciente, request.user)
    return redirect('core:editar_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk)


@require_POST
def renovar_link_anamnese(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    ficha = FichaCadastroAnamnese.objects.filter(
        pk=ficha_pk, paciente=paciente
    ).first()
    if ficha is None:
        messages.error(
            request,
            'Essa ficha não existe mais. Abra a lista de anamnese do paciente.',
        )
        return redirect('core:listar_fichas_anamnese', pk=paciente.pk)
    if ficha.status != FichaCadastroAnamnese.Status.RASCUNHO:
        messages.error(
            request,
            'Não dá para gerar um link novo: o paciente já enviou esta ficha. '
            'Abra o registro e conclua com a assinatura do dentista.',
        )
        return redirect(
            'core:ver_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk
        )
    renovar_token(ficha)
    messages.success(request, 'Novo link gerado. O anterior deixa de funcionar.')
    return redirect('core:listar_fichas_anamnese', pk=paciente.pk)


def editar_ficha_anamnese(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    ficha = get_object_or_404(
        FichaCadastroAnamnese, pk=ficha_pk, paciente=paciente
    )
    if ficha.status != FichaCadastroAnamnese.Status.RASCUNHO:
        return redirect(
            'core:ver_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk
        )
    return _salvar_ficha_anamnese(
        request,
        ficha,
        publico=False,
        template='core/form_ficha_anamnese.html',
    )


def ver_ficha_anamnese(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    ficha = get_object_or_404(
        FichaCadastroAnamnese, pk=ficha_pk, paciente=paciente
    )
    if ficha.status == FichaCadastroAnamnese.Status.RASCUNHO:
        return redirect(
            'core:editar_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk
        )
    form = AssinaturaDentistaAnamneseForm(request.POST or None)
    if (
        request.method == 'POST'
        and ficha.status == FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
        and form.is_valid()
    ):
        dentista = dentista_do_usuario(request.user)
        with transaction.atomic():
            if dentista and not ficha.dentista_id:
                ficha.dentista = dentista
                ficha.save(update_fields=['dentista'])
            _gravar_assinatura_anamnese(
                request,
                ficha,
                AssinaturaEletronica.Papel.DENTISTA,
                request.user.get_full_name() or request.user.username,
                '',
                form.cleaned_data['assinatura_dentista_base64'],
                usuario=request.user,
            )
            ficha.status = FichaCadastroAnamnese.Status.CONCLUIDA
            ficha.save(update_fields=['status', 'atualizado_em'])
        messages.success(request, 'Ficha concluída com a assinatura do dentista.')
        return redirect(
            'core:ver_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk
        )
    return render(request, 'core/ver_ficha_anamnese.html', {
        'paciente': paciente,
        'ficha': ficha,
        'form': form,
        'texto_declaracao': TEXTO_DECLARACAO_ANAMNESE,
        'saude_rotulos': rotulos_checklist(ficha.saude_condicoes, SAUDE_CONDICOES),
        'bucal_rotulos': rotulos_checklist(ficha.saude_bucal, SAUDE_BUCAL),
        'assinaturas': _assinaturas_da_ficha(ficha),
        'pode_assinar_dentista': (
            ficha.status == FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
        ),
        'titulo': 'Ficha de cadastro e anamnese',
    })


@login_not_required
def ficha_anamnese_publica(request, token):
    ficha = FichaCadastroAnamnese.objects.filter(token=token).select_related(
        'paciente'
    ).first()
    if ficha is None or not ficha.link_publico_ativo:
        if (
            ficha is not None
            and ficha.status != FichaCadastroAnamnese.Status.RASCUNHO
        ):
            return render(
                request,
                'core/ficha_anamnese_enviada.html',
                {'ja_enviada': True},
            )
        return render(request, 'core/ficha_anamnese_indisponivel.html')
    return _salvar_ficha_anamnese(
        request,
        ficha,
        publico=True,
        template='core/form_ficha_anamnese.html',
    )


@login_not_required
def ficha_anamnese_enviada(request, token):
    ficha = FichaCadastroAnamnese.objects.filter(token=token).first()
    if ficha is None:
        return render(request, 'core/ficha_anamnese_indisponivel.html')
    return render(request, 'core/ficha_anamnese_enviada.html', {
        'ja_enviada': False,
    })


def _salvar_ficha_anamnese(request, ficha, *, publico, template):
    acao = request.POST.get('acao', 'enviar')
    if publico:
        acao = 'enviar'
    exigir = acao != 'rascunho'
    coletar_paciente = exigir
    coletar_dentista = (not publico) and acao == 'concluir'
    if request.method == 'POST':
        form = FichaAnamneseForm(
            request.POST,
            instance=ficha,
            exigir_completo=exigir,
            coletar_paciente=coletar_paciente,
            coletar_dentista=coletar_dentista,
        )
        if form.is_valid():
            with transaction.atomic():
                ficha = form.save(commit=False)
                ficha.preenchida_por = (
                    FichaCadastroAnamnese.PreenchidaPor.PACIENTE
                    if publico
                    else FichaCadastroAnamnese.PreenchidaPor.EQUIPE
                )
                if acao == 'rascunho':
                    ficha.status = FichaCadastroAnamnese.Status.RASCUNHO
                elif coletar_dentista:
                    ficha.status = FichaCadastroAnamnese.Status.CONCLUIDA
                    dentista = dentista_do_usuario(request.user)
                    if dentista:
                        ficha.dentista = dentista
                else:
                    ficha.status = FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
                ficha.save()
                sincronizar_paciente(ficha)
                if acao != 'rascunho':
                    menor = eh_menor_de_idade(ficha.data_nascimento)
                    if menor:
                        papel = AssinaturaEletronica.Papel.RESPONSAVEL
                        nome = ficha.nome_responsavel
                        cpf = ''
                    else:
                        papel = AssinaturaEletronica.Papel.PACIENTE
                        nome = ficha.nome_completo
                        cpf = ficha.cpf
                    _gravar_assinatura_anamnese(
                        request,
                        ficha,
                        papel,
                        nome,
                        cpf,
                        form.cleaned_data['assinatura_paciente_base64'],
                        usuario=request.user if request.user.is_authenticated else None,
                    )
                    if coletar_dentista:
                        _gravar_assinatura_anamnese(
                            request,
                            ficha,
                            AssinaturaEletronica.Papel.DENTISTA,
                            request.user.get_full_name() or request.user.username,
                            '',
                            form.cleaned_data['assinatura_dentista_base64'],
                            usuario=request.user,
                        )
            if publico:
                return redirect('core:ficha_anamnese_enviada', token=ficha.token)
            messages.success(request, 'Ficha salva.')
            if ficha.status == FichaCadastroAnamnese.Status.RASCUNHO:
                return redirect(
                    'core:editar_ficha_anamnese',
                    pk=ficha.paciente_id,
                    ficha_pk=ficha.pk,
                )
            return redirect(
                'core:ver_ficha_anamnese',
                pk=ficha.paciente_id,
                ficha_pk=ficha.pk,
            )
    else:
        form = FichaAnamneseForm(
            instance=ficha,
            exigir_completo=False,
            coletar_paciente=False,
            coletar_dentista=False,
        )
    menor = eh_menor_de_idade(ficha.data_nascimento)
    return render(request, template, {
        'form': form,
        'ficha': ficha,
        'paciente': ficha.paciente,
        'publico': publico,
        'texto_declaracao': TEXTO_DECLARACAO_ANAMNESE,
        'menor': menor,
        'titulo': 'Cadastro e anamnese',
    })

