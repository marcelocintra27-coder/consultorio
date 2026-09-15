from decimal import Decimal
import json
from datetime import date, datetime, timedelta
from uuid import uuid4


from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required, login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from locacao.models import Dentista, Despesa, PerfilUsuario, Sala

from .assinatura import gravar_assinatura_manuscrita
from .caixa import registrar_movimento_automatico
from .conciliacao import sugerir_origens, valor_origem
from .evolucao import texto_para_hash_evolucao
from .autorizacao import (
    TEXTO_DECLARACAO_AUTORIZACAO,
    texto_para_hash_autorizacao,
)
from .plano import (
    CIENCIA_ITENS,
    COMPLEXIDADE_ITENS,
    TEXTO_AVISO_MULTIPLOS_PROFISSIONAIS,
    TEXTO_DECLARACAO_PLANO,
    texto_para_hash_plano,
)
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
from .ia_digitalizacao import processar_digitalizacao_com_ia
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
    ContaReceber,
    ParcelaContaReceber,
    RecebimentoPaciente,
    AuditoriaFinanceira,
    Fornecedor,
    CategoriaContaPagar,
    ContaPagar,
    BaixaContaPagar,
    AuditoriaContaPagar,
    CaixaDiario,
    MovimentoCaixa,
    AuditoriaCaixa,
    ImportacaoExtrato,
    LancamentoExtrato,
    Conciliacao,
    ItemConciliacao,
    AjusteConciliacao,
    AuditoriaConciliacao,
    FormaPagamentoConfiguravel,
    AuditoriaFormaPagamento,
    AssinaturaEletronica,
    FichaCadastroAnamnese,
    DigitalizacaoFicha,
    RegistroEvolucaoClinica,
    FichaPlanoTratamento,
    FichaAutorizacaoCusto,
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
    ContaReceberForm,
    ContaReceberParcelaFormSet,
    RecebimentoPacienteForm,
    EstornoRecebimentoForm,
    FornecedorForm,
    CategoriaContaPagarForm,
    ContaPagarForm,
    BaixaContaPagarForm,
    AbrirCaixaForm,
    MovimentoManualCaixaForm,
    FecharCaixaForm,
    ImportacaoExtratoManualForm,
    LancamentoExtratoManualForm,
    ItemConciliacaoForm,
    AjusteConciliacaoForm,
    MotivoCancelamentoForm,
    FormaPagamentoConfiguravelForm,
    RelatorioFinanceiroFiltroForm,
    AssinaturaTesteForm,
    DigitalizacaoFichaForm,
    FichaAnamneseForm,
    AssinaturaDentistaAnamneseForm,
    RegistroEvolucaoClinicaForm,
    FichaPlanoTratamentoForm,
    FichaAutorizacaoCustoForm,
    montar_itens_formset,
    montar_itens_autorizacao_formset,
    montar_profissionais_formset,
)
from .permissoes import (
    exige_financeiro,
    exige_operacao_financeira,
    usuario_pode_financeiro,
    usuario_pode_lancar,
    usuario_pode_complementar_dentista,
    usuario_pode_editar_catalogo,
    usuario_e_administrador,
    dentista_do_usuario,
    usuario_pode_acessar_prontuario,
    usuario_pode_registrar_prontuario,
    usuario_pode_gerenciar_agenda,
    usuario_pode_acessar_consulta,
    consultas_visiveis_para_usuario,
    usuario_pode_agendar_consulta,
    usuario_pode_acessar_cadastro_paciente,
    pacientes_visiveis_para_usuario,
    usuario_pode_cadastrar_paciente,
    usuario_pode_editar_cadastro_paciente,
    perfil_do_usuario,
    status_consulta_permitidos,
    usuario_pode_alterar_status_consulta,
)

def inicio(request):
    perfil = perfil_do_usuario(request.user)
    if usuario_e_administrador(request.user):
        return render(request, 'core/inicio.html', {
            'dashboard_administrador': True,
            'consultas_em_andamento': Consulta.objects.filter(
                status__in=[
                    Consulta.Status.AGENDADA,
                    Consulta.Status.CONFIRMADA,
                    Consulta.Status.PRESENTE,
                ]
            ).count(),
            'dentistas_ativos': Dentista.objects.filter(ativo=True).count(),
            'salas_ativas': Sala.objects.filter(ativa=True).count(),
            'perfis_configurados': PerfilUsuario.objects.count(),
        })
    if perfil and perfil.papel == perfil.Papel.SECRETARIA:
        hoje = timezone.localdate()
        consultas_hoje = consultas_visiveis_para_usuario(
            request.user,
            Consulta.objects.filter(data=hoje)
            .select_related('paciente', 'dentista')
            .order_by('hora_inicio'),
        )
        return render(request, 'core/inicio.html', {
            'dashboard_secretaria': True,
            'hoje': hoje,
            'consultas_hoje': consultas_hoje,
            'total_consultas_hoje': consultas_hoje.count(),
            'consultas_agendadas_hoje': consultas_hoje.filter(
                status=Consulta.Status.AGENDADA
            ).count(),
            'consultas_realizadas_hoje': consultas_hoje.filter(
                status=Consulta.Status.REALIZADA
            ).count(),
            'consultas_canceladas_hoje': consultas_hoje.filter(
                status=Consulta.Status.CANCELADA
            ).count(),
        })
    if (
        perfil
        and perfil.papel == perfil.Papel.DENTISTA
        and perfil.dentista_id
    ):
        hoje = timezone.localdate()
        consultas_hoje = consultas_visiveis_para_usuario(
            request.user,
            Consulta.objects.filter(data=hoje)
            .select_related('paciente', 'dentista')
            .order_by('hora_inicio'),
        )
        anamneses_pendentes = FichaCadastroAnamnese.objects.filter(
            dentista_id=perfil.dentista_id,
            paciente__consultas__dentista_id=perfil.dentista_id,
            status=FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA,
        ).select_related('paciente').distinct()
        autorizacoes_pendentes = FichaAutorizacaoCusto.objects.filter(
            consulta__dentista_id=perfil.dentista_id,
            status=FichaAutorizacaoCusto.Status.RASCUNHO,
        ).select_related('paciente', 'consulta')
        return render(request, 'core/inicio.html', {
            'dashboard_dentista': True,
            'hoje': hoje,
            'consultas_hoje': consultas_hoje,
            'total_consultas_hoje': consultas_hoje.count(),
            'consultas_em_atendimento_hoje': consultas_hoje.filter(
                status=Consulta.Status.PRESENTE
            ).count(),
            'anamneses_pendentes': anamneses_pendentes,
            'autorizacoes_pendentes': autorizacoes_pendentes,
        })
    return render(request, 'core/inicio.html')


@exige_financeiro
def administracao(request):
    """Centraliza o acesso administrativo já disponível no Django Admin.

    O portal não replica formulários técnicos nem altera permissões do Admin.
    A autorização explícita de administrador de negócio evita que ``is_staff``
    isolado use esta área como acesso a dados operacionais.
    """
    return render(request, 'core/administracao.html')


@login_not_required
def sair(request):
    logout(request)
    return redirect('entrar')

def listar_pacientes(request):
    termo = request.GET.get('q', '').strip()
    pacientes = pacientes_visiveis_para_usuario(
        request.user,
        Paciente.objects.filter(ativo=True),
    )
    if termo:
        pacientes = pacientes.filter(nome_completo__icontains=termo)
    pacientes = pacientes.order_by('nome_completo')
    perfil = getattr(request.user, 'perfil', None)
    pode_clinico = bool(
        usuario_e_administrador(request.user)
        or (perfil and perfil.papel == perfil.Papel.DENTISTA)
    )
    return render(request, 'core/listar_pacientes.html', {
        'pacientes': pacientes,
        'termo': termo,
        'pode_cadastrar_paciente': usuario_pode_cadastrar_paciente(request.user),
        'pode_clinico': pode_clinico,
    })

def cadastrar_paciente(request):
    if not usuario_pode_cadastrar_paciente(request.user):
        raise PermissionDenied
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
    if not usuario_pode_editar_cadastro_paciente(request.user, paciente):
        raise PermissionDenied
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
        'pode_clinico': usuario_pode_acessar_prontuario(request.user, paciente),
    })


@login_required
def digitalizacao_upload(request):
    if request.method == 'POST':
        form = DigitalizacaoFichaForm(request.POST, request.FILES)
        if form.is_valid():
            digitalizacao = form.save(commit=False)
            digitalizacao.digitalizado_por = request.user
            digitalizacao.save()
            messages.success(
                request,
                'Digitalização enviada. A ficha ficou pendente de revisão.',
            )
            return redirect('core:digitalizacao_upload')
        messages.error(
            request,
            'Não foi possível enviar. Confira os avisos no formulário.',
        )
    else:
        form = DigitalizacaoFichaForm()
    return render(request, 'core/digitalizacao_upload.html', {
        'form': form,
    })


@login_required
@require_POST
def digitalizacao_processar_ia(request, pk):
    digitalizacao = get_object_or_404(DigitalizacaoFicha, pk=pk)
    ok = processar_digitalizacao_com_ia(digitalizacao)
    if ok:
        messages.success(
            request,
            'A leitura da ficha com a IA foi concluída.',
        )
    else:
        messages.error(
            request,
            'Não foi possível ler a ficha com a IA. Tente de novo em instantes.',
        )
    return redirect('core:digitalizacao_upload')


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
    status_selecionado = request.GET.get('status', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = consultas_visiveis_para_usuario(
        request.user,
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio', 'dentista')
        .order_by('hora_inicio'),
    )
    status_validos = {valor for valor, _ in Consulta.Status.choices}
    if status_selecionado in status_validos:
        consultas = consultas.filter(status=status_selecionado)
    else:
        status_selecionado = ''
    return render(request, 'core/listar_consultas.html', {
        'consultas': consultas,
        'data': data,
        'status_selecionado': status_selecionado,
        'status_choices': Consulta.Status.choices,
        'pode_agendar': usuario_pode_agendar_consulta(request.user),
        'pode_financeiro': usuario_pode_financeiro(request.user),
        'pode_visualizar_valores': usuario_pode_financeiro(request.user) or bool(
            dentista_do_usuario(request.user)
        ),
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


def _auditar_forma_pagamento(*, forma_pagamento, usuario, acao, descricao, dados=None):
    AuditoriaFormaPagamento.objects.create(
        forma_pagamento=forma_pagamento,
        usuario=usuario,
        acao=acao,
        descricao=descricao,
        dados=dados or {},
    )


@exige_financeiro
def listar_formas_pagamento_configuraveis(request):
    return render(request, 'core/listar_formas_pagamento.html', {
        'formas': FormaPagamentoConfiguravel.objects.prefetch_related('auditorias__usuario'),
    })


@exige_financeiro
def cadastrar_forma_pagamento_configuravel(request):
    form = FormaPagamentoConfiguravelForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            forma = form.save(commit=False)
            forma.full_clean()
            forma.save()
            _auditar_forma_pagamento(
                forma_pagamento=forma,
                usuario=request.user,
                acao='criada',
                descricao='Forma de pagamento configurável criada.',
            )
            return redirect('core:listar_formas_pagamento_configuraveis')
    return render(request, 'core/form_financeiro_cadastro.html', {
        'form': form,
        'titulo': 'Nova forma de pagamento',
        'voltar_url': 'core:listar_formas_pagamento_configuraveis',
    })


@exige_financeiro
def editar_forma_pagamento_configuravel(request, pk):
    forma = get_object_or_404(FormaPagamentoConfiguravel, pk=pk)
    form = FormaPagamentoConfiguravelForm(request.POST or None, instance=forma)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            forma = form.save(commit=False)
            forma.full_clean()
            forma.save()
            _auditar_forma_pagamento(
                forma_pagamento=forma,
                usuario=request.user,
                acao='atualizada',
                descricao='Configuração de forma de pagamento atualizada.',
                dados={'ativo': forma.ativo, 'tipo_taxa': forma.tipo_taxa},
            )
            return redirect('core:listar_formas_pagamento_configuraveis')
    return render(request, 'core/form_financeiro_cadastro.html', {
        'form': form,
        'titulo': 'Editar forma de pagamento',
        'voltar_url': 'core:listar_formas_pagamento_configuraveis',
    })


def _registrar_auditoria_financeira(
    *, conta, usuario, acao, descricao, parcela=None, recebimento=None, dados=None
):
    AuditoriaFinanceira.objects.create(
        conta=conta,
        parcela=parcela,
        recebimento=recebimento,
        usuario=usuario,
        acao=acao,
        descricao=descricao,
        dados=dados or {},
    )


@exige_financeiro
def listar_contas_receber(request):
    termo = request.GET.get('q', '').strip()
    contas = ContaReceber.objects.select_related('paciente', 'consulta').prefetch_related(
        'parcelas__recebimentos'
    )
    if termo:
        contas = contas.filter(
            Q(paciente__nome_completo__icontains=termo)
            | Q(descricao__icontains=termo)
        )
    return render(request, 'core/listar_contas_receber.html', {
        'contas': contas.order_by('data_emissao', 'pk'),
        'termo': termo,
    })


@exige_financeiro
def listar_inadimplencia(request):
    """Lista parcelas vencidas com saldo derivado dos eventos financeiros.

    A consulta usa apenas contas a receber de pacientes. Não inclui os
    conceitos financeiros separados de Uniodonto, locação, despesas, dívidas
    ou acertos entre dentistas.
    """
    hoje = timezone.localdate()
    termo = request.GET.get('q', '').strip()
    faixa = request.GET.get('faixa', '').strip()
    campo_decimal = DecimalField(max_digits=12, decimal_places=2)
    zero = Value(Decimal('0.00'), output_field=campo_decimal)

    parcelas = ParcelaContaReceber.objects.select_related(
        'conta__paciente'
    ).annotate(
        valor_recebido_calculado=Coalesce(
            Sum(
                'recebimentos__valor',
                filter=Q(recebimentos__tipo=RecebimentoPaciente.Tipo.RECEBIMENTO),
            ),
            zero,
            output_field=campo_decimal,
        ),
        desconto_calculado=Coalesce(
            Sum(
                'recebimentos__desconto',
                filter=Q(recebimentos__tipo=RecebimentoPaciente.Tipo.RECEBIMENTO),
            ),
            zero,
            output_field=campo_decimal,
        ),
        valor_estornado_calculado=Coalesce(
            Sum(
                'recebimentos__valor',
                filter=Q(recebimentos__tipo=RecebimentoPaciente.Tipo.ESTORNO),
            ),
            zero,
            output_field=campo_decimal,
        ),
    ).annotate(
        saldo_calculado=ExpressionWrapper(
            F('valor_original')
            - F('valor_recebido_calculado')
            - F('desconto_calculado')
            + F('valor_estornado_calculado'),
            output_field=campo_decimal,
        )
    ).filter(
        vencimento__lt=hoje,
        saldo_calculado__gt=Decimal('0.00'),
    )
    if termo:
        parcelas = parcelas.filter(
            Q(conta__paciente__nome_completo__icontains=termo)
            | Q(conta__descricao__icontains=termo)
        )

    faixas = {
        '1-30': (1, 30, '1 a 30 dias'),
        '31-60': (31, 60, '31 a 60 dias'),
        '61-90': (61, 90, '61 a 90 dias'),
        '90+': (91, None, 'Mais de 90 dias'),
    }
    parcelas = list(parcelas.order_by('vencimento', 'pk'))
    for parcela in parcelas:
        parcela.dias_atraso = (hoje - parcela.vencimento).days
        parcela.saldo_calculado = Decimal(parcela.saldo_calculado).quantize(
            Decimal('0.01')
        )

    if faixa in faixas:
        inicio, fim, _ = faixas[faixa]
        parcelas = [
            parcela
            for parcela in parcelas
            if parcela.dias_atraso >= inicio
            and (fim is None or parcela.dias_atraso <= fim)
        ]
    else:
        faixa = ''

    contas_ids = {parcela.conta_id for parcela in parcelas}
    auditorias_por_conta = {}
    if contas_ids:
        auditorias = AuditoriaFinanceira.objects.filter(
            conta_id__in=contas_ids
        ).select_related('usuario').order_by('-criado_em')
        for auditoria in auditorias:
            auditorias_por_conta.setdefault(auditoria.conta_id, []).append(auditoria)
    for parcela in parcelas:
        parcela.historico_financeiro = auditorias_por_conta.get(parcela.conta_id, [])

    return render(request, 'core/listar_inadimplencia.html', {
        'parcelas': parcelas,
        'termo': termo,
        'faixa': faixa,
        'faixas': faixas,
        'hoje': hoje,
        'saldo_total': sum(
            (parcela.saldo_calculado for parcela in parcelas), Decimal('0.00')
        ).quantize(Decimal('0.01')),
    })


def _valor_total(queryset, campo='valor'):
    """Soma monetária sem misturar ausência de registros com valores nulos."""
    total = queryset.aggregate(total=Sum(campo))['total'] or Decimal('0.00')
    return Decimal(total).quantize(Decimal('0.01'))


@exige_financeiro
def relatorios_financeiros(request):
    """Consolida fontes financeiras existentes sem criar movimentos ou vínculos.

    A visão realizada usa exclusivamente MovimentoCaixa, que já é a fonte
    auditável do caixa. A visão prevista usa as datas de vencimento ou
    competência já cadastradas, sem inferir competência para dados legados que
    não a possuem.
    """
    hoje = timezone.localdate()
    inicio_padrao = hoje.replace(day=1)
    form = RelatorioFinanceiroFiltroForm(
        request.GET or None,
        initial={'data_inicial': inicio_padrao, 'data_final': hoje},
    )
    if form.is_valid():
        data_inicial = form.cleaned_data['data_inicial']
        data_final = form.cleaned_data['data_final']
    else:
        data_inicial, data_final = inicio_padrao, hoje

    periodo = (data_inicial, data_final)
    movimentos = list(
        MovimentoCaixa.objects.filter(caixa__data__range=periodo)
        .select_related('caixa')
        .order_by('caixa__data', 'pk')
    )
    tipos_entrada = {
        MovimentoCaixa.Tipo.ENTRADA_AUTOMATICA,
        MovimentoCaixa.Tipo.AJUSTE_ENTRADA,
        MovimentoCaixa.Tipo.COMPENSACAO_ENTRADA,
    }
    entradas_realizadas = sum(
        (movimento.valor for movimento in movimentos if movimento.tipo in tipos_entrada),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))
    saidas_realizadas = sum(
        (movimento.valor for movimento in movimentos if movimento.tipo not in tipos_entrada),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    recebimentos = RecebimentoPaciente.objects.filter(recebido_em__date__range=periodo)
    formas_legadas = dict(Consulta.FormaPagamento.choices)
    grupos_recebimento = {}
    for recebimento in recebimentos.select_related(
        'forma_pagamento_configurada',
        'recebimento_original__forma_pagamento_configurada',
    ):
        # Estornos não recebem forma nova; pertencem à forma do recebimento
        # original para que o demonstrativo não separe artificialmente o saldo.
        origem = (
            recebimento.recebimento_original
            if recebimento.tipo == RecebimentoPaciente.Tipo.ESTORNO
            else recebimento
        )
        forma = (
            origem.forma_pagamento_configurada.nome
            if origem.forma_pagamento_configurada_id
            else formas_legadas.get(origem.forma_pagamento, 'Não informada')
        )
        grupo = grupos_recebimento.setdefault(forma, {
            'forma': forma,
            'recebido': Decimal('0.00'),
            'estornado': Decimal('0.00'),
            'desconto': Decimal('0.00'),
        })
        if recebimento.tipo == RecebimentoPaciente.Tipo.RECEBIMENTO:
            grupo['recebido'] += recebimento.valor
            grupo['desconto'] += recebimento.desconto
        else:
            grupo['estornado'] += recebimento.valor
    recebimentos_por_forma = []
    for grupo in grupos_recebimento.values():
        grupo['liquido'] = (
            grupo['recebido'] - grupo['estornado'] - grupo['desconto']
        ).quantize(Decimal('0.01'))
        recebimentos_por_forma.append(grupo)
    recebimentos_por_forma.sort(key=lambda grupo: grupo['forma'])

    ajustes = AjusteConciliacao.objects.filter(
        ativo=True, criado_em__date__range=periodo
    )
    taxas_conciliacao = _valor_total(
        ajustes.exclude(tipo=AjusteConciliacao.Tipo.DIVERGENCIA)
    )
    divergencias_conciliacao = _valor_total(
        ajustes.filter(tipo=AjusteConciliacao.Tipo.DIVERGENCIA)
    )

    parcelas_previstas = ParcelaContaReceber.objects.filter(vencimento__range=periodo)
    previsto_receber = _valor_total(parcelas_previstas, 'valor_original')
    contas_pagar_previstas = ContaPagar.objects.filter(competencia__range=periodo)
    previsto_pagar_contas = _valor_total(contas_pagar_previstas, 'valor_original')
    despesas_legadas = Despesa.objects.filter(
        conta_pagar__isnull=True, competencia__range=periodo
    )
    previsto_despesas_legadas = _valor_total(despesas_legadas)

    despesas_por_categoria = list(
        contas_pagar_previstas.values('categoria__nome').annotate(total=Sum('valor_original'))
        .order_by('categoria__nome')
    )
    if previsto_despesas_legadas:
        despesas_por_categoria.append({
            'categoria__nome': 'Despesas legadas sem conta a pagar',
            'total': previsto_despesas_legadas,
        })

    parcelas_vencidas = ParcelaContaReceber.objects.filter(
        vencimento__range=periodo
    ).prefetch_related('recebimentos')
    saldo_vencido = sum(
        (
            parcela.saldo
            for parcela in parcelas_vencidas
            if parcela.vencimento < hoje and parcela.saldo > Decimal('0.00')
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))
    quantidade_vencida = sum(
        1
        for parcela in parcelas_vencidas
        if parcela.vencimento < hoje and parcela.saldo > Decimal('0.00')
    )

    fechamentos = CaixaDiario.objects.filter(
        data__range=periodo, situacao=CaixaDiario.Situacao.FECHADO
    ).select_related('fechado_por').order_by('data')
    repasses = RepasseUniodonto.objects.filter(competencia__range=periodo)
    total_repasses = _valor_total(repasses, 'liquido_recebido')

    return render(request, 'core/relatorios_financeiros.html', {
        'form': form,
        'data_inicial': data_inicial,
        'data_final': data_final,
        'entradas_realizadas': entradas_realizadas,
        'saidas_realizadas': saidas_realizadas,
        'resultado_realizado': (entradas_realizadas - saidas_realizadas).quantize(Decimal('0.01')),
        'movimentos_realizados': movimentos,
        'recebimentos_por_forma': recebimentos_por_forma,
        'taxas_conciliacao': taxas_conciliacao,
        'divergencias_conciliacao': divergencias_conciliacao,
        'previsto_receber': previsto_receber,
        'previsto_pagar_contas': previsto_pagar_contas,
        'previsto_despesas_legadas': previsto_despesas_legadas,
        'resultado_previsto': (
            previsto_receber - previsto_pagar_contas - previsto_despesas_legadas
        ).quantize(Decimal('0.01')),
        'despesas_por_categoria': despesas_por_categoria,
        'saldo_vencido': saldo_vencido,
        'quantidade_vencida': quantidade_vencida,
        'fechamentos': fechamentos,
        'repasses': repasses,
        'total_repasses': total_repasses,
    })


def _registrar_auditoria_conta_pagar(*, conta, usuario, acao, descricao, baixa=None, dados=None):
    AuditoriaContaPagar.objects.create(
        conta=conta, baixa=baixa, usuario=usuario, acao=acao,
        descricao=descricao, dados=dados or {},
    )


def _auditar_caixa(caixa, usuario, descricao, movimento=None):
    AuditoriaCaixa.objects.create(caixa=caixa, movimento=movimento, usuario=usuario, descricao=descricao)


@exige_financeiro
def caixa_diario(request):
    data = request.GET.get('data') or timezone.localdate().isoformat()
    caixa = CaixaDiario.objects.filter(data=data).prefetch_related('movimentos', 'auditorias').first()
    return render(request, 'core/caixa_diario.html', {'caixa': caixa, 'data': data})


@exige_financeiro
def abrir_caixa(request):
    form = AbrirCaixaForm(request.POST or None, initial={'data': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if CaixaDiario.objects.select_for_update().filter(data=form.cleaned_data['data']).exists():
                form.add_error('data', 'Já existe caixa para esta data.')
            else:
                caixa = form.save(commit=False); caixa.aberto_por = request.user; caixa.save()
                _auditar_caixa(caixa, request.user, 'Caixa aberto.')
                return redirect('core:caixa_diario')
    return render(request, 'core/form_caixa.html', {'form': form, 'titulo': 'Abrir caixa'})


@exige_financeiro
def movimento_manual_caixa(request, pk):
    caixa = get_object_or_404(CaixaDiario, pk=pk)
    form = MovimentoManualCaixaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            caixa = CaixaDiario.objects.select_for_update().get(pk=pk)
            if caixa.situacao != CaixaDiario.Situacao.ABERTO:
                form.add_error(None, 'Caixa fechado é imutável.')
            else:
                movimento = MovimentoCaixa.objects.create(caixa=caixa, usuario=request.user, **form.cleaned_data)
                _auditar_caixa(caixa, request.user, 'Movimento manual registrado.', movimento)
                return redirect('core:caixa_diario')
    return render(request, 'core/form_caixa.html', {'form': form, 'titulo': 'Ajuste ou compensação de caixa', 'caixa': caixa})


@exige_financeiro
def fechar_caixa(request, pk):
    caixa = get_object_or_404(CaixaDiario, pk=pk)
    form = FecharCaixaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            caixa = CaixaDiario.objects.select_for_update().get(pk=pk)
            diferenca = form.cleaned_data['saldo_contado'] - caixa.saldo_esperado
            if caixa.situacao != CaixaDiario.Situacao.ABERTO:
                form.add_error(None, 'Caixa já fechado.')
            elif diferenca and not form.cleaned_data['justificativa_diferenca'].strip():
                form.add_error('justificativa_diferenca', 'Justificativa obrigatória para diferença.')
            else:
                caixa.saldo_contado=form.cleaned_data['saldo_contado']; caixa.justificativa_diferenca=form.cleaned_data['justificativa_diferenca']; caixa.situacao=CaixaDiario.Situacao.FECHADO; caixa.fechado_por=request.user; caixa.fechado_em=timezone.now(); caixa.save()
                _auditar_caixa(caixa, request.user, 'Caixa fechado.')
                return redirect('core:caixa_diario')
    return render(request, 'core/form_caixa.html', {'form': form, 'titulo': 'Fechar caixa', 'caixa': caixa})


def _auditar_conciliacao(*, usuario, acao, descricao, conciliacao=None, importacao=None, dados=None):
    AuditoriaConciliacao.objects.create(
        conciliacao=conciliacao,
        importacao=importacao,
        usuario=usuario,
        acao=acao,
        descricao=descricao,
        dados=dados or {},
    )


def _campo_origem(origem):
    if isinstance(origem, RecebimentoPaciente):
        return 'recebimento'
    if isinstance(origem, BaixaContaPagar):
        return 'baixa'
    if isinstance(origem, MovimentoCaixa):
        return 'movimento_caixa'
    if isinstance(origem, RepasseUniodonto):
        return 'repasse_uniodonto'
    raise ValidationError('Origem financeira inválida para conciliação.')


def _bloquear_origem_para_conciliacao(origem):
    """Obtém lock da origem antes de conferir o limite de conciliação parcial."""
    if isinstance(origem, RecebimentoPaciente):
        return RecebimentoPaciente.objects.select_for_update().get(pk=origem.pk)
    if isinstance(origem, BaixaContaPagar):
        return BaixaContaPagar.objects.select_for_update().get(pk=origem.pk)
    if isinstance(origem, MovimentoCaixa):
        return MovimentoCaixa.objects.select_for_update().get(pk=origem.pk)
    if isinstance(origem, RepasseUniodonto):
        return RepasseUniodonto.objects.select_for_update().get(pk=origem.pk)
    raise ValidationError('Origem financeira inválida para conciliação.')


def _atualizar_situacao_conciliacao(conciliacao, usuario):
    if conciliacao.ajustes.filter(
        ativo=True, tipo=AjusteConciliacao.Tipo.DIVERGENCIA
    ).exists():
        situacao = Conciliacao.Situacao.DIVERGENTE
    else:
        valor = conciliacao.valor_conciliado
        valor_extrato = conciliacao.lancamento_extrato.valor
        situacao = (
            Conciliacao.Situacao.CONCILIADA
            if valor == valor_extrato
            else Conciliacao.Situacao.PARCIAL
        )
    conciliacao.situacao = situacao
    conciliacao.confirmado_por = usuario
    conciliacao.confirmado_em = timezone.now()
    conciliacao.motivo_cancelamento = ''
    conciliacao.cancelado_por = None
    conciliacao.cancelado_em = None
    conciliacao.save()


@exige_financeiro
def listar_conciliacoes(request):
    situacao = request.GET.get('situacao', '').strip()
    lancamentos = LancamentoExtrato.objects.select_related('importacao').order_by('-data', '-pk')
    if situacao:
        lancamentos = lancamentos.filter(conciliacao__situacao=situacao)
    return render(request, 'core/listar_conciliacoes.html', {
        'lancamentos': lancamentos,
        'situacao': situacao,
        'situacoes': Conciliacao.Situacao.choices,
    })


@exige_financeiro
def criar_importacao_extrato_manual(request):
    form = ImportacaoExtratoManualForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            importacao = form.save(commit=False)
            importacao.formato = ImportacaoExtrato.Formato.MANUAL
            importacao.criado_por = request.user
            importacao.full_clean()
            importacao.save()
            _auditar_conciliacao(
                usuario=request.user,
                importacao=importacao,
                acao='importacao_manual_criada',
                descricao='Importação manual de extrato criada.',
            )
            return redirect('core:detalhe_importacao_extrato', pk=importacao.pk)
    return render(request, 'core/form_conciliacao.html', {
        'form': form,
        'titulo': 'Nova origem manual de extrato',
        'voltar_url': reverse('core:listar_conciliacoes'),
    })


@exige_financeiro
def detalhe_importacao_extrato(request, pk):
    importacao = get_object_or_404(
        ImportacaoExtrato.objects.prefetch_related('lancamentos', 'auditorias__usuario'), pk=pk
    )
    return render(request, 'core/detalhe_importacao_extrato.html', {'importacao': importacao})


@exige_financeiro
def criar_lancamento_extrato_manual(request, pk):
    importacao = get_object_or_404(ImportacaoExtrato, pk=pk)
    form = LancamentoExtratoManualForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            importacao = ImportacaoExtrato.objects.select_for_update().get(pk=pk)
            if importacao.situacao != ImportacaoExtrato.Situacao.IMPORTADA:
                form.add_error(None, 'A origem de extrato está cancelada logicamente.')
            elif importacao.formato != ImportacaoExtrato.Formato.MANUAL:
                form.add_error(None, 'Lançamentos manuais só podem ser incluídos em origem manual.')
            else:
                lancamento = form.save(commit=False)
                lancamento.importacao = importacao
                lancamento.indice_origem = importacao.lancamentos.count() + 1
                lancamento.full_clean()
                lancamento.save()
                _auditar_conciliacao(
                    usuario=request.user,
                    importacao=importacao,
                    acao='lancamento_manual_criado',
                    descricao='Lançamento manual de extrato criado.',
                    dados={'lancamento_extrato_id': lancamento.pk},
                )
                return redirect('core:conciliar_lancamento_extrato', pk=lancamento.pk)
    return render(request, 'core/form_conciliacao.html', {
        'form': form,
        'titulo': 'Novo lançamento manual de extrato',
        'voltar_url': reverse('core:detalhe_importacao_extrato', args=[importacao.pk]),
    })


@exige_financeiro
def conciliar_lancamento_extrato(request, pk):
    lancamento = get_object_or_404(
        LancamentoExtrato.objects.select_related('importacao'), pk=pk
    )
    conciliacao, _ = Conciliacao.objects.get_or_create(
        lancamento_extrato=lancamento,
        defaults={'criado_por': request.user},
    )
    form = ItemConciliacaoForm(request.POST or None, natureza=lancamento.natureza)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            conciliacao = Conciliacao.objects.select_for_update().select_related(
                'lancamento_extrato'
            ).get(pk=conciliacao.pk)
            origem = _bloquear_origem_para_conciliacao(form.cleaned_data['origem'])
            campo = _campo_origem(origem)
            valor = form.cleaned_data['valor_conciliado']
            valor_usado = ItemConciliacao.objects.filter(
                ativo=True, **{campo: origem}
            ).aggregate(soma=Sum('valor_conciliado'))['soma'] or Decimal('0.00')
            if valor_usado + valor > valor_origem(origem):
                form.add_error('valor_conciliado', 'Esta origem já possui valor conciliado suficiente.')
            elif conciliacao.valor_conciliado + valor > conciliacao.lancamento_extrato.valor:
                form.add_error('valor_conciliado', 'Não pode exceder o valor do lançamento de extrato.')
            else:
                item = ItemConciliacao(
                    conciliacao=conciliacao,
                    valor_origem=valor_origem(origem),
                    valor_conciliado=valor,
                    criado_por=request.user,
                    **{campo: origem},
                )
                item.full_clean()
                item.save()
                _atualizar_situacao_conciliacao(conciliacao, request.user)
                _auditar_conciliacao(
                    usuario=request.user,
                    conciliacao=conciliacao,
                    acao='item_confirmado',
                    descricao='Vínculo de conciliação confirmado manualmente.',
                    dados={'origem': campo, 'origem_id': origem.pk, 'valor': f'{valor:.2f}'},
                )
                return redirect('core:conciliar_lancamento_extrato', pk=lancamento.pk)
    return render(request, 'core/detalhe_conciliacao.html', {
        'lancamento': lancamento,
        'conciliacao': conciliacao,
        'form': form,
        'sugestoes': sugerir_origens(lancamento),
        'ajuste_form': AjusteConciliacaoForm(),
        'cancelamento_form': MotivoCancelamentoForm(),
    })


@exige_financeiro
def registrar_ajuste_conciliacao(request, pk):
    conciliacao = get_object_or_404(Conciliacao, pk=pk)
    form = AjusteConciliacaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            conciliacao = Conciliacao.objects.select_for_update().get(pk=pk)
            ajuste = form.save(commit=False)
            ajuste.conciliacao = conciliacao
            ajuste.criado_por = request.user
            ajuste.full_clean()
            ajuste.save()
            _atualizar_situacao_conciliacao(conciliacao, request.user)
            _auditar_conciliacao(
                usuario=request.user,
                conciliacao=conciliacao,
                acao='ajuste_registrado',
                descricao='Taxa ou divergência registrada separadamente.',
                dados={'tipo': ajuste.tipo, 'valor': f'{ajuste.valor:.2f}'},
            )
    return redirect('core:conciliar_lancamento_extrato', pk=conciliacao.lancamento_extrato_id)


@exige_financeiro
@require_POST
def cancelar_conciliacao(request, pk):
    conciliacao = get_object_or_404(Conciliacao, pk=pk)
    form = MotivoCancelamentoForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            conciliacao = Conciliacao.objects.select_for_update().get(pk=pk)
            conciliacao.itens.filter(ativo=True).update(ativo=False)
            conciliacao.ajustes.filter(ativo=True).update(ativo=False)
            conciliacao.situacao = Conciliacao.Situacao.CANCELADA
            conciliacao.motivo_cancelamento = form.cleaned_data['motivo']
            conciliacao.cancelado_por = request.user
            conciliacao.cancelado_em = timezone.now()
            conciliacao.save()
            _auditar_conciliacao(
                usuario=request.user,
                conciliacao=conciliacao,
                acao='cancelada_logicamente',
                descricao='Conciliação cancelada logicamente; origens foram preservadas.',
                dados={'motivo': conciliacao.motivo_cancelamento},
            )
    return redirect('core:conciliar_lancamento_extrato', pk=conciliacao.lancamento_extrato_id)


@exige_financeiro
def listar_fornecedores(request):
    termo = request.GET.get('q', '').strip()
    fornecedores = Fornecedor.objects.all()
    if termo:
        fornecedores = fornecedores.filter(nome__icontains=termo)
    return render(request, 'core/listar_fornecedores.html', {
        'fornecedores': fornecedores.order_by('nome'), 'termo': termo,
    })


@exige_financeiro
def cadastrar_fornecedor(request):
    form = FornecedorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('core:listar_fornecedores')
    return render(request, 'core/form_financeiro_cadastro.html', {
        'form': form, 'titulo': 'Novo fornecedor',
        'voltar_url': 'core:listar_fornecedores',
    })


@exige_financeiro
def listar_categorias_conta_pagar(request):
    return render(request, 'core/listar_categorias_conta_pagar.html', {
        'categorias': CategoriaContaPagar.objects.all().order_by('nome'),
    })


@exige_financeiro
def cadastrar_categoria_conta_pagar(request):
    form = CategoriaContaPagarForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('core:listar_categorias_conta_pagar')
    return render(request, 'core/form_financeiro_cadastro.html', {
        'form': form, 'titulo': 'Nova categoria de conta a pagar',
        'voltar_url': 'core:listar_categorias_conta_pagar',
    })


@exige_financeiro
def listar_contas_pagar(request):
    termo = request.GET.get('q', '').strip()
    situacao = request.GET.get('situacao', '').strip()
    contas = ContaPagar.objects.select_related('fornecedor', 'categoria')
    if termo:
        contas = contas.filter(
            Q(fornecedor__nome__icontains=termo) | Q(descricao__icontains=termo)
        )
    situacoes = {valor for valor, _ in ContaPagar.Situacao.choices}
    if situacao in situacoes:
        contas = contas.filter(situacao=situacao)
    else:
        situacao = ''
    return render(request, 'core/listar_contas_pagar.html', {
        'contas': contas.order_by('vencimento', 'pk'), 'termo': termo,
        'situacao': situacao, 'situacoes': ContaPagar.Situacao.choices,
    })


@exige_financeiro
def criar_conta_pagar(request):
    form = ContaPagarForm(request.POST or None, initial={'competencia': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            conta = form.save(commit=False)
            conta.responsavel = request.user
            conta.full_clean()
            conta.save()
            _registrar_auditoria_conta_pagar(
                conta=conta, usuario=request.user,
                acao=AuditoriaContaPagar.Acao.CONTA_CRIADA,
                descricao='Conta a pagar criada e aguardando aprovação.',
                dados={'valor_original': f'{conta.valor_original:.2f}', 'recorrencia': conta.recorrencia},
            )
        return redirect('core:detalhe_conta_pagar', pk=conta.pk)
    return render(request, 'core/form_conta_pagar.html', {
        'form': form, 'titulo': 'Nova conta a pagar',
    })


@exige_financeiro
def detalhe_conta_pagar(request, pk):
    conta = get_object_or_404(
        ContaPagar.objects.select_related(
            'fornecedor', 'categoria', 'responsavel', 'aprovado_por'
        ).prefetch_related('baixas__operador', 'auditorias__usuario'), pk=pk,
    )
    return render(request, 'core/detalhe_conta_pagar.html', {'conta': conta})


@exige_financeiro
@require_POST
def aprovar_conta_pagar(request, pk):
    with transaction.atomic():
        conta = get_object_or_404(ContaPagar.objects.select_for_update(), pk=pk)
        if conta.situacao != ContaPagar.Situacao.PENDENTE_APROVACAO:
            messages.error(request, 'Esta conta não está pendente de aprovação.')
        else:
            conta.situacao = ContaPagar.Situacao.APROVADA
            conta.aprovado_por = request.user
            conta.aprovado_em = timezone.now()
            conta.full_clean()
            conta.save(update_fields=['situacao', 'aprovado_por', 'aprovado_em'])
            _registrar_auditoria_conta_pagar(
                conta=conta, usuario=request.user,
                acao=AuditoriaContaPagar.Acao.CONTA_APROVADA,
                descricao='Conta a pagar aprovada.',
            )
            messages.success(request, 'Conta aprovada para baixa.')
    return redirect('core:detalhe_conta_pagar', pk=pk)


@exige_financeiro
def registrar_baixa_conta_pagar(request, pk):
    conta = get_object_or_404(ContaPagar.objects.select_related('fornecedor'), pk=pk)
    form = BaixaContaPagarForm(
        request.POST or None,
        initial={'chave_operacao': uuid4()} if request.method != 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            conta = get_object_or_404(ContaPagar.objects.select_for_update(), pk=pk)
            chave = form.cleaned_data['chave_operacao']
            if conta.situacao != ContaPagar.Situacao.APROVADA:
                form.add_error(None, 'Somente uma conta aprovada pode receber baixa.')
            elif BaixaContaPagar.objects.filter(chave_operacao=chave).exists():
                form.add_error(None, 'Esta operação já foi registrada.')
            elif form.cleaned_data['valor'] > conta.saldo:
                form.add_error('valor', 'O valor da baixa não pode exceder o saldo.')
            else:
                baixa = BaixaContaPagar(
                    conta=conta, valor=form.cleaned_data['valor'], operador=request.user,
                    chave_operacao=chave, observacoes=form.cleaned_data['observacoes'],
                )
                baixa.full_clean()
                baixa.save()
                registrar_movimento_automatico(baixa=baixa, usuario=request.user)
                if conta.saldo == Decimal('0.00'):
                    conta.situacao = ContaPagar.Situacao.PAGA
                    conta.save(update_fields=['situacao'])
                _registrar_auditoria_conta_pagar(
                    conta=conta, baixa=baixa, usuario=request.user,
                    acao=AuditoriaContaPagar.Acao.BAIXA_REGISTRADA,
                    descricao='Baixa de conta a pagar registrada.',
                    dados={'valor': f'{baixa.valor:.2f}'},
                )
                return redirect('core:detalhe_conta_pagar', pk=conta.pk)
    return render(request, 'core/form_baixa_conta_pagar.html', {
        'form': form, 'conta': conta, 'titulo': 'Registrar baixa',
    })


@exige_financeiro
def criar_conta_receber(request):
    if request.method == 'POST':
        form = ContaReceberForm(request.POST)
        formset = ContaReceberParcelaFormSet(request.POST, prefix='parcelas')
        if form.is_valid() and formset.is_valid():
            parcelas = [item.cleaned_data for item in formset if item.cleaned_data]
            total = sum(
                (item['valor_original'] for item in parcelas), Decimal('0.00')
            ).quantize(Decimal('0.01'))
            if total <= 0:
                form.add_error(None, 'Informe ao menos uma parcela com valor válido.')
            else:
                with transaction.atomic():
                    conta = form.save(commit=False)
                    conta.valor_original = total
                    conta.criado_por = request.user
                    conta.full_clean()
                    conta.save()
                    for numero, item in enumerate(parcelas, start=1):
                        ParcelaContaReceber.objects.create(
                            conta=conta,
                            numero=numero,
                            vencimento=item['vencimento'],
                            valor_original=item['valor_original'],
                        )
                    _registrar_auditoria_financeira(
                        conta=conta,
                        usuario=request.user,
                        acao=AuditoriaFinanceira.Acao.CONTA_CRIADA,
                        descricao='Conta a receber criada.',
                        dados={
                            'valor_original': f'{conta.valor_original:.2f}',
                            'quantidade_parcelas': len(parcelas),
                        },
                    )
                return redirect('core:detalhe_conta_receber', pk=conta.pk)
    else:
        form = ContaReceberForm(initial={'data_emissao': timezone.localdate()})
        formset = ContaReceberParcelaFormSet(prefix='parcelas')
    return render(request, 'core/form_conta_receber.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Nova conta a receber',
    })


@exige_financeiro
def detalhe_conta_receber(request, pk):
    conta = get_object_or_404(
        ContaReceber.objects.select_related('paciente', 'consulta', 'criado_por')
        .prefetch_related(
            'parcelas__recebimentos__operador',
            'parcelas__recebimentos__recebimento_original',
            'auditorias_financeiras__usuario',
        ),
        pk=pk,
    )
    return render(request, 'core/detalhe_conta_receber.html', {'conta': conta})


@exige_financeiro
def registrar_recebimento(request, parcela_pk):
    parcela = get_object_or_404(
        ParcelaContaReceber.objects.select_related('conta__paciente'), pk=parcela_pk
    )
    if request.method == 'POST':
        form = RecebimentoPacienteForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                parcela = get_object_or_404(
                    ParcelaContaReceber.objects.select_for_update().select_related(
                        'conta__paciente'
                    ),
                    pk=parcela_pk,
                )
                valor = form.cleaned_data['valor']
                desconto = form.cleaned_data.get('desconto') or Decimal('0.00')
                forma_configurada = form.cleaned_data.get('forma_pagamento_configurada')
                forma_legada = (
                    forma_configurada.codigo_legado
                    if forma_configurada is not None
                    else form.cleaned_data['forma_pagamento']
                )
                if valor + desconto > parcela.saldo:
                    form.add_error(
                        None,
                        'O valor recebido somado ao desconto não pode exceder o saldo.',
                    )
                else:
                    recebimento = RecebimentoPaciente(
                        parcela=parcela,
                        tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
                        valor=valor,
                        desconto=desconto,
                        forma_pagamento=forma_legada,
                        forma_pagamento_configurada=forma_configurada,
                        observacoes=form.cleaned_data['observacoes'],
                        operador=request.user,
                    )
                    recebimento.full_clean()
                    recebimento.save()
                    registrar_movimento_automatico(recebimento=recebimento, usuario=request.user)
                    _registrar_auditoria_financeira(
                        conta=parcela.conta,
                        parcela=parcela,
                        recebimento=recebimento,
                        usuario=request.user,
                        acao=AuditoriaFinanceira.Acao.RECEBIMENTO_REGISTRADO,
                        descricao='Recebimento de paciente registrado.',
                        dados={
                            'valor': f'{recebimento.valor:.2f}',
                            'desconto': f'{recebimento.desconto:.2f}',
                            'forma_pagamento': recebimento.forma_pagamento,
                            'forma_pagamento_configurada_id': recebimento.forma_pagamento_configurada_id,
                            'numero_recibo': recebimento.numero_recibo,
                        },
                    )
                    return redirect('core:detalhe_conta_receber', pk=parcela.conta_id)
    else:
        form = RecebimentoPacienteForm()
    return render(request, 'core/form_financeiro_operacao.html', {
        'form': form,
        'parcela': parcela,
        'titulo': 'Registrar recebimento',
        'acao': 'Registrar recebimento',
    })


@exige_financeiro
def estornar_recebimento(request, pk):
    recebimento = get_object_or_404(
        RecebimentoPaciente.objects.select_related('parcela__conta__paciente'),
        pk=pk,
        tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
    )
    if request.method == 'POST':
        form = EstornoRecebimentoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                original = get_object_or_404(
                    RecebimentoPaciente.objects.select_for_update().select_related(
                        'parcela__conta__paciente'
                    ),
                    pk=pk,
                    tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
                )
                parcela = ParcelaContaReceber.objects.select_for_update().get(
                    pk=original.parcela_id
                )
                ja_estornado = original.estornos.aggregate(soma=Sum('valor'))['soma']
                saldo_estornavel = original.valor - Decimal(ja_estornado or '0.00')
                if form.cleaned_data['valor'] > saldo_estornavel:
                    form.add_error(
                        'valor',
                        'O estorno não pode exceder o valor ainda estornável.',
                    )
                else:
                    estorno = RecebimentoPaciente(
                        parcela=parcela,
                        tipo=RecebimentoPaciente.Tipo.ESTORNO,
                        valor=form.cleaned_data['valor'],
                        desconto=Decimal('0.00'),
                        observacoes=form.cleaned_data['observacoes'],
                        operador=request.user,
                        recebimento_original=original,
                    )
                    estorno.full_clean()
                    estorno.save()
                    registrar_movimento_automatico(
                        recebimento=estorno, usuario=request.user
                    )
                    _registrar_auditoria_financeira(
                        conta=parcela.conta,
                        parcela=parcela,
                        recebimento=estorno,
                        usuario=request.user,
                        acao=AuditoriaFinanceira.Acao.ESTORNO_REGISTRADO,
                        descricao='Estorno de recebimento registrado.',
                        dados={
                            'valor': f'{estorno.valor:.2f}',
                            'recebimento_original_id': original.pk,
                        },
                    )
                    return redirect('core:detalhe_conta_receber', pk=parcela.conta_id)
    else:
        form = EstornoRecebimentoForm(initial={'valor': recebimento.valor})
    return render(request, 'core/form_financeiro_operacao.html', {
        'form': form,
        'parcela': recebimento.parcela,
        'recebimento': recebimento,
        'titulo': 'Registrar estorno',
        'acao': 'Registrar estorno',
    })


@exige_financeiro
def ver_recibo_recebimento(request, pk):
    recebimento = get_object_or_404(
        RecebimentoPaciente.objects.select_related(
            'parcela__conta__paciente', 'operador'
        ),
        pk=pk,
        tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
    )
    return render(request, 'core/recibo_recebimento.html', {
        'recebimento': recebimento,
        'conta': recebimento.parcela.conta,
    })


@exige_operacao_financeira
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
    consultas = consultas_visiveis_para_usuario(
        request.user,
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio', 'dentista')
        .prefetch_related('materiais')
        .order_by('hora_inicio'),
    )
    for consulta in consultas:
        consulta.pode_lancar = usuario_pode_lancar(request.user, consulta)
    return render(request, 'core/listar_materiais_dia.html', {
        'consultas': consultas,
        'data': data,
    })


@exige_operacao_financeira
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


@exige_operacao_financeira
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


@exige_operacao_financeira
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
    if not usuario_pode_agendar_consulta(request.user):
        raise PermissionDenied
    dentista_logado = dentista_do_usuario(request.user)
    if request.method == 'POST':
        form = ConsultaForm(request.POST)
        if dentista_logado:
            form.fields['dentista'].queryset = Dentista.objects.filter(pk=dentista_logado.pk)
        if form.is_valid():
            consulta = form.save(commit=False)
            consulta.eh_legado = False
            consulta.save()
            return redirect(
                f"{reverse('core:listar_consultas')}?data={consulta.data.isoformat()}"
            )
    else:
        form = ConsultaForm(initial={'data': timezone.localdate()})
        if dentista_logado:
            form.fields['dentista'].queryset = Dentista.objects.filter(pk=dentista_logado.pk)
            form.fields['dentista'].initial = dentista_logado.pk
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
    if not usuario_pode_acessar_consulta(request.user, consulta):
        raise PermissionDenied
    pode_financeiro = usuario_pode_financeiro(request.user)
    pode_lancar = usuario_pode_lancar(request.user, consulta)
    pode_complementar = usuario_pode_complementar_dentista(request.user, consulta)
    pode_gerenciar_agenda = usuario_pode_gerenciar_agenda(request.user, consulta)
    pode_clinico = usuario_pode_acessar_prontuario(
        request.user, consulta.paciente, consulta
    )

    status_permitidos = status_consulta_permitidos(request.user, consulta)
    status_form = StatusConsultaForm(
        instance=consulta,
        status_permitidos=status_permitidos,
    )
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
        'pode_visualizar_valores': pode_lancar,
        'pode_lancar': pode_lancar,
        'pode_complementar': pode_complementar,
        'pode_gerenciar_agenda': pode_gerenciar_agenda,
        'pode_alterar_status': bool(status_permitidos),
        'pode_clinico': pode_clinico,
        'usa_lancamento_uniodonto': usa_uniodonto,
        'fator_us_uniodonto': FATOR_US_UNIODONTO,
        'precos_json': json.dumps(precos),
        'itens_uniodonto_json': json.dumps(itens_uniodonto),
        'sugestoes_desconto_json': json.dumps(sugestoes_desconto),
        'autorizacoes': consulta.autorizacoes_custo.select_related(
            'solicitado_por'
        ),
        'auditorias': consulta.auditorias.select_related('usuario')[:20]
        if pode_financeiro
        else [],
    })


@require_POST
def alterar_status_consulta(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    if not usuario_pode_gerenciar_agenda(request.user, consulta):
        raise PermissionDenied
    status_permitidos = status_consulta_permitidos(request.user, consulta)
    novo_status = request.POST.get('status', '')
    if not usuario_pode_alterar_status_consulta(
        request.user, consulta, novo_status
    ):
        raise PermissionDenied
    form = StatusConsultaForm(
        request.POST,
        instance=consulta,
        status_permitidos=status_permitidos,
    )
    if form.is_valid():
        form.save()
        _registrar_auditoria(
            consulta,
            request.user,
            f'status alterado para {consulta.get_status_display()}',
        )
    return redirect('core:ficha_consulta', pk=consulta.pk)


@exige_operacao_financeira
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
    if assinatura.paciente_id:
        autorizado = usuario_pode_acessar_prontuario(
            request.user, assinatura.paciente
        )
    else:
        # Assinaturas técnicas sem paciente (componente de teste) ficam
        # restritas à administração.
        autorizado = usuario_e_administrador(request.user)
    if not autorizado:
        raise PermissionDenied
    from .integridade_documentos import documento_da_assinatura, verificar_integridade
    if assinatura.tipo_documento != 'componente_teste':
        documento = documento_da_assinatura(assinatura)
        if documento and not usuario_pode_acessar_prontuario(request.user, documento.paciente):
            raise PermissionDenied
        resultado = verificar_integridade(documento) if documento else None
        if resultado is None or not resultado.integra:
            return render(request, 'core/integridade_indisponivel.html', {
                'ocorrencias': resultado.ocorrencias if resultado else ['Documento original não encontrado.'],
            }, status=409)
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
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
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
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = _criar_rascunho_anamnese(paciente, request.user)
    return redirect('core:editar_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk)


@require_POST
def renovar_link_anamnese(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
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
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
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
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = get_object_or_404(
        FichaCadastroAnamnese, pk=ficha_pk, paciente=paciente
    )
    if ficha.status == FichaCadastroAnamnese.Status.RASCUNHO:
        return redirect(
            'core:editar_ficha_anamnese', pk=paciente.pk, ficha_pk=ficha.pk
        )
    form = AssinaturaDentistaAnamneseForm(request.POST or None)
    from .integridade_documentos import verificar_integridade
    integridade = verificar_integridade(ficha)
    if (
        request.method == 'POST'
        and ficha.status == FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
        and integridade.integra
        and form.is_valid()
    ):
        if not usuario_pode_registrar_prontuario(request.user, paciente):
            raise PermissionDenied
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
            and integridade.integra
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


def ficha_evolucao_clinica(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    pode_registrar = usuario_pode_registrar_prontuario(request.user, paciente)
    registros = list(
        RegistroEvolucaoClinica.objects.filter(paciente=paciente).order_by(
            'data', 'criado_em', 'pk'
        )
    )
    ids = [item.pk for item in registros]
    assinaturas = {
        item.documento_id: item
        for item in AssinaturaEletronica.objects.filter(
            tipo_documento=AssinaturaEletronica.TipoDocumento.EVOLUCAO,
            documento_id__in=ids,
        )
    }
    for item in registros:
        item.assinatura = assinaturas.get(item.pk)

    dentista = dentista_do_usuario(request.user)
    nome_sugerido = ''
    if dentista:
        nome_sugerido = dentista.nome_completo
    elif request.user.is_authenticated:
        nome_sugerido = request.user.get_full_name() or request.user.username

    if request.method == 'POST':
        if not pode_registrar:
            raise PermissionDenied
        form = RegistroEvolucaoClinicaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                registro = form.save(commit=False)
                registro.paciente = paciente
                registro.dentista = dentista
                registro.criado_por = request.user
                registro.save()
                gravar_assinatura_manuscrita(
                    tipo_documento=AssinaturaEletronica.TipoDocumento.EVOLUCAO,
                    documento_id=registro.pk,
                    papel=AssinaturaEletronica.Papel.DENTISTA,
                    nome_assinante=registro.nome_profissional,
                    imagem_data_url=form.cleaned_data['assinatura_base64'],
                    conteudo_para_hash=texto_para_hash_evolucao(registro),
                    paciente=paciente,
                    usuario=request.user,
                    ip=_ip_do_pedido(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
            messages.success(request, 'Evolução assinada e gravada.')
            return redirect('core:ficha_evolucao_clinica', pk=paciente.pk)
    else:
        form = RegistroEvolucaoClinicaForm(
            initial={
                'data': date.today(),
                'nome_profissional': nome_sugerido,
            }
        )
        if not pode_registrar:
            form = None

    return render(request, 'core/ficha_evolucao_clinica.html', {
        'paciente': paciente,
        'registros': registros,
        'form': form,
        'pode_registrar': pode_registrar,
        'titulo': 'Evolução clínica',
    })


def _ficha_plano_aberta(paciente):
    return FichaPlanoTratamento.objects.filter(
        paciente=paciente,
        status=FichaPlanoTratamento.Status.RASCUNHO,
    ).first()


def _criar_rascunho_plano(paciente, usuario):
    existente = _ficha_plano_aberta(paciente)
    if existente:
        return existente
    ultima = paciente.fichas_anamnese.order_by('-criado_em').first()
    return FichaPlanoTratamento.objects.create(
        paciente=paciente,
        criado_por=usuario if usuario.is_authenticated else None,
        nome_completo=paciente.nome_completo,
        data_nascimento=paciente.data_nascimento,
        cpf=paciente.cpf,
        telefone=paciente.telefone,
        whatsapp=paciente.whatsapp or '',
        email=paciente.email or '',
        endereco=paciente.endereco or '',
        cidade=(ultima.cidade if ultima else ''),
        uf=(ultima.uf if ultima else ''),
        profissao=(ultima.profissao if ultima else ''),
        nome_responsavel=(ultima.nome_responsavel if ultima else ''),
        data_consentimento=date.today(),
    )


def _assinaturas_mapa(tipo, ids):
    return {
        item.documento_id: item
        for item in AssinaturaEletronica.objects.filter(
            tipo_documento=tipo,
            documento_id__in=ids,
        )
    }


def listar_fichas_plano(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    return render(request, 'core/listar_fichas_plano.html', {
        'paciente': paciente,
        'fichas': paciente.fichas_plano.all(),
        'ficha_aberta': _ficha_plano_aberta(paciente),
        'pode_registrar': usuario_pode_registrar_prontuario(request.user, paciente),
    })


@require_POST
def nova_ficha_plano(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = _criar_rascunho_plano(paciente, request.user)
    return redirect('core:editar_ficha_plano', pk=paciente.pk, ficha_pk=ficha.pk)


def editar_ficha_plano(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = get_object_or_404(
        FichaPlanoTratamento, pk=ficha_pk, paciente=paciente
    )
    if ficha.status != FichaPlanoTratamento.Status.RASCUNHO:
        return redirect(
            'core:ver_ficha_plano', pk=paciente.pk, ficha_pk=ficha.pk
        )
    return _salvar_ficha_plano(request, ficha)


def ver_ficha_plano(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = get_object_or_404(
        FichaPlanoTratamento, pk=ficha_pk, paciente=paciente
    )
    if (
        ficha.status == FichaPlanoTratamento.Status.RASCUNHO
        and usuario_pode_registrar_prontuario(request.user, paciente)
    ):
        return redirect(
            'core:editar_ficha_plano', pk=paciente.pk, ficha_pk=ficha.pk
        )
    itens = list(ficha.itens.prefetch_related('dentistas'))
    profissionais = list(ficha.profissionais.all())
    sig_ficha = _assinaturas_mapa(
        AssinaturaEletronica.TipoDocumento.PLANO_TRATAMENTO, [ficha.pk]
    )
    sig_itens = _assinaturas_mapa(
        AssinaturaEletronica.TipoDocumento.PLANO_PROCEDIMENTO,
        [item.pk for item in itens],
    )
    sig_profs = _assinaturas_mapa(
        AssinaturaEletronica.TipoDocumento.PLANO_PROFISSIONAL,
        [item.pk for item in profissionais],
    )
    paciente_sig = AssinaturaEletronica.objects.filter(
        tipo_documento=AssinaturaEletronica.TipoDocumento.PLANO_TRATAMENTO,
        documento_id=ficha.pk,
        papel__in=[
            AssinaturaEletronica.Papel.PACIENTE,
            AssinaturaEletronica.Papel.RESPONSAVEL,
        ],
    ).first()
    for item in itens:
        item.assinatura = sig_itens.get(item.pk)
    for item in profissionais:
        item.assinatura = sig_profs.get(item.pk)
    return render(request, 'core/ver_ficha_plano.html', {
        'paciente': paciente,
        'ficha': ficha,
        'itens': itens,
        'profissionais': profissionais,
        'assinatura_paciente': paciente_sig,
        'ciencia_rotulos': rotulos_checklist(ficha.ciencia_itens, CIENCIA_ITENS),
        'complexidade_rotulos': rotulos_checklist(
            ficha.complexidade_itens, COMPLEXIDADE_ITENS
        ),
        'texto_aviso': TEXTO_AVISO_MULTIPLOS_PROFISSIONAIS,
        'texto_declaracao': TEXTO_DECLARACAO_PLANO,
        'titulo': 'Plano de tratamento e consentimento',
    })


def _salvar_ficha_plano(request, ficha):
    exigir = request.method == 'POST' and request.POST.get('acao') == 'concluir'
    dentista = dentista_do_usuario(request.user)
    nome_sugerido = (
        dentista.nome_completo
        if dentista
        else (request.user.get_full_name() or request.user.username)
    )
    if request.method == 'POST':
        form = FichaPlanoTratamentoForm(
            request.POST,
            instance=ficha,
            exigir_completo=exigir,
            coletar_paciente=exigir,
        )
        itens = montar_itens_formset(
            exigir_completo=exigir,
            dentista=dentista,
            instance=ficha,
            data=request.POST,
            prefix='itens',
        )
        profissionais = montar_profissionais_formset(
            exigir_completo=exigir,
            instance=ficha,
            data=request.POST,
            prefix='profissionais',
        )
        forms_ok = form.is_valid() and itens.is_valid() and profissionais.is_valid()
        itens_preenchidos = [
            item_form
            for item_form in itens.forms
            if item_form.is_valid() and item_form.linha_preenchida()
        ]
        profs_preenchidos = [
            item_form
            for item_form in profissionais.forms
            if item_form.is_valid() and item_form.linha_preenchida()
        ]
        if exigir and forms_ok and not itens_preenchidos:
            form.add_error(None, 'Inclua ao menos um procedimento com assinatura.')
            forms_ok = False
        if exigir and forms_ok and not profs_preenchidos:
            form.add_error(None, 'Inclua a assinatura de ao menos um profissional.')
            forms_ok = False
        if forms_ok:
            with transaction.atomic():
                ficha = form.save(commit=False)
                if exigir:
                    ficha.status = FichaPlanoTratamento.Status.CONCLUIDA
                else:
                    ficha.status = FichaPlanoTratamento.Status.RASCUNHO
                ficha.save()
                sincronizar_paciente(ficha)
                _gravar_formset_itens(itens, ficha)
                _gravar_formset_profissionais(profissionais, ficha, dentista)
                if exigir:
                    menor = eh_menor_de_idade(ficha.data_nascimento)
                    papel = (
                        AssinaturaEletronica.Papel.RESPONSAVEL
                        if menor
                        else AssinaturaEletronica.Papel.PACIENTE
                    )
                    nome = (
                        ficha.nome_responsavel
                        if menor
                        else ficha.nome_completo
                    )
                    hash_doc = texto_para_hash_plano(ficha)
                    gravar_assinatura_manuscrita(
                        tipo_documento=AssinaturaEletronica.TipoDocumento.PLANO_TRATAMENTO,
                        documento_id=ficha.pk,
                        papel=papel,
                        nome_assinante=nome,
                        imagem_data_url=form.cleaned_data['assinatura_paciente_base64'],
                        conteudo_para_hash=hash_doc,
                        paciente=ficha.paciente,
                        cpf_assinante='' if menor else ficha.cpf,
                        usuario=request.user,
                        ip=_ip_do_pedido(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
                    ficha.refresh_from_db()
                    for item_form in itens.forms:
                        if not item_form.linha_preenchida():
                            continue
                        item = item_form.instance
                        gravar_assinatura_manuscrita(
                            tipo_documento=AssinaturaEletronica.TipoDocumento.PLANO_PROCEDIMENTO,
                            documento_id=item.pk,
                            papel=papel,
                            nome_assinante=nome,
                            imagem_data_url=item_form.cleaned_data['assinatura_base64'],
                            conteudo_para_hash=hash_doc,
                            paciente=ficha.paciente,
                            usuario=request.user,
                            ip=_ip_do_pedido(request),
                            user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        )
                    for item_form in profissionais.forms:
                        if not item_form.linha_preenchida():
                            continue
                        prof = item_form.instance
                        gravar_assinatura_manuscrita(
                            tipo_documento=AssinaturaEletronica.TipoDocumento.PLANO_PROFISSIONAL,
                            documento_id=prof.pk,
                            papel=AssinaturaEletronica.Papel.DENTISTA,
                            nome_assinante=prof.nome,
                            imagem_data_url=item_form.cleaned_data['assinatura_base64'],
                            conteudo_para_hash=hash_doc,
                            paciente=ficha.paciente,
                            usuario=request.user,
                            ip=_ip_do_pedido(request),
                            user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        )
            messages.success(request, 'Ficha salva.')
            if ficha.status == FichaPlanoTratamento.Status.RASCUNHO:
                return redirect(
                    'core:editar_ficha_plano',
                    pk=ficha.paciente_id,
                    ficha_pk=ficha.pk,
                )
            return redirect(
                'core:ver_ficha_plano',
                pk=ficha.paciente_id,
                ficha_pk=ficha.pk,
            )
    else:
        form = FichaPlanoTratamentoForm(instance=ficha)
        itens = montar_itens_formset(
            instance=ficha, prefix='itens', dentista=dentista
        )
        profissionais = montar_profissionais_formset(
            instance=ficha,
            prefix='profissionais',
            initial=[{'nome': nome_sugerido}] if not ficha.profissionais.exists() else None,
        )
    menor = eh_menor_de_idade(ficha.data_nascimento)
    return render(request, 'core/form_ficha_plano.html', {
        'form': form,
        'itens': itens,
        'profissionais': profissionais,
        'ficha': ficha,
        'paciente': ficha.paciente,
        'menor': menor,
        'texto_aviso': TEXTO_AVISO_MULTIPLOS_PROFISSIONAIS,
        'texto_declaracao': TEXTO_DECLARACAO_PLANO,
        'dentista_logado_id': dentista.pk if dentista else '',
        'titulo': 'Plano de tratamento e consentimento',
    })


def _gravar_formset_itens(formset, ficha):
    for indice, item_form in enumerate(formset.forms):
        dados = item_form.cleaned_data
        if not dados:
            continue
        if dados.get('DELETE'):
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        if not item_form.linha_preenchida():
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        item = item_form.save(commit=False)
        item.ficha = ficha
        item.ordem = indice
        item.save()
        item_form.save_m2m()


def _ficha_autorizacao_aberta(paciente):
    return FichaAutorizacaoCusto.objects.filter(
        paciente=paciente,
        status=FichaAutorizacaoCusto.Status.RASCUNHO,
    ).first()


def _criar_rascunho_autorizacao(paciente, usuario, consulta=None):
    existente = _ficha_autorizacao_aberta(paciente)
    if existente:
        if consulta and existente.consulta_id is None:
            existente.consulta = consulta
            existente.save(update_fields=['consulta'])
        return existente
    ultima = paciente.fichas_anamnese.order_by('-criado_em').first()
    return FichaAutorizacaoCusto.objects.create(
        paciente=paciente,
        consulta=consulta,
        solicitado_por=usuario if usuario.is_authenticated else None,
        nome_completo=paciente.nome_completo,
        data_nascimento=paciente.data_nascimento,
        cpf=paciente.cpf,
        nome_responsavel=(ultima.nome_responsavel if ultima else ''),
    )


def listar_fichas_autorizacao(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    return render(request, 'core/listar_fichas_autorizacao.html', {
        'paciente': paciente,
        'fichas': paciente.fichas_autorizacao_custo.select_related(
            'consulta', 'solicitado_por'
        ),
        'ficha_aberta': _ficha_autorizacao_aberta(paciente),
        'pode_registrar': usuario_pode_registrar_prontuario(request.user, paciente),
    })


@require_POST
def nova_ficha_autorizacao(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    consulta = None
    consulta_id = request.POST.get('consulta')
    if consulta_id:
        consulta = get_object_or_404(
            Consulta, pk=consulta_id, paciente=paciente
        )
    if not usuario_pode_registrar_prontuario(request.user, paciente, consulta):
        raise PermissionDenied
    ficha = _criar_rascunho_autorizacao(
        paciente, request.user, consulta=consulta
    )
    return redirect(
        'core:editar_ficha_autorizacao',
        pk=paciente.pk,
        ficha_pk=ficha.pk,
    )


@require_POST
def nova_ficha_autorizacao_consulta(request, pk):
    consulta = get_object_or_404(
        Consulta.objects.select_related('paciente'), pk=pk
    )
    if not usuario_pode_registrar_prontuario(
        request.user, consulta.paciente, consulta
    ):
        raise PermissionDenied
    paciente = consulta.paciente
    if not paciente.ativo:
        raise PermissionDenied
    ficha = _criar_rascunho_autorizacao(
        paciente, request.user, consulta=consulta
    )
    return redirect(
        'core:editar_ficha_autorizacao',
        pk=paciente.pk,
        ficha_pk=ficha.pk,
    )


def editar_ficha_autorizacao(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_registrar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = get_object_or_404(
        FichaAutorizacaoCusto, pk=ficha_pk, paciente=paciente
    )
    if ficha.status != FichaAutorizacaoCusto.Status.RASCUNHO:
        return redirect(
            'core:ver_ficha_autorizacao', pk=paciente.pk, ficha_pk=ficha.pk
        )
    return _salvar_ficha_autorizacao(request, ficha)


def ver_ficha_autorizacao(request, pk, ficha_pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    ficha = get_object_or_404(
        FichaAutorizacaoCusto.objects.select_related(
            'consulta', 'solicitado_por'
        ),
        pk=ficha_pk,
        paciente=paciente,
    )
    if (
        ficha.status == FichaAutorizacaoCusto.Status.RASCUNHO
        and usuario_pode_registrar_prontuario(request.user, paciente)
    ):
        return redirect(
            'core:editar_ficha_autorizacao', pk=paciente.pk, ficha_pk=ficha.pk
        )
    itens = list(ficha.itens.all())
    assinatura = AssinaturaEletronica.objects.filter(
        tipo_documento=AssinaturaEletronica.TipoDocumento.AUTORIZACAO_CUSTO,
        documento_id=ficha.pk,
        papel__in=[
            AssinaturaEletronica.Papel.PACIENTE,
            AssinaturaEletronica.Papel.RESPONSAVEL,
        ],
    ).first()
    return render(request, 'core/ver_ficha_autorizacao.html', {
        'paciente': paciente,
        'ficha': ficha,
        'itens': itens,
        'assinatura': assinatura,
        'texto_declaracao': TEXTO_DECLARACAO_AUTORIZACAO,
        'titulo': 'Autorização de itens com custo',
    })


def _salvar_ficha_autorizacao(request, ficha):
    exigir = request.method == 'POST' and request.POST.get('acao') == 'concluir'
    if request.method == 'POST':
        form = FichaAutorizacaoCustoForm(
            request.POST,
            instance=ficha,
            exigir_completo=exigir,
            coletar_paciente=exigir,
        )
        itens = montar_itens_autorizacao_formset(
            exigir_completo=exigir,
            instance=ficha,
            data=request.POST,
            prefix='itens',
        )
        forms_ok = form.is_valid() and itens.is_valid()
        itens_preenchidos = [
            item_form
            for item_form in itens.forms
            if item_form.is_valid() and item_form.linha_preenchida()
        ]
        if exigir and forms_ok and not itens_preenchidos:
            form.add_error(None, 'Inclua ao menos um item autorizado.')
            forms_ok = False
        if forms_ok:
            with transaction.atomic():
                ficha = form.save(commit=False)
                if exigir:
                    ficha.status = FichaAutorizacaoCusto.Status.CONCLUIDA
                else:
                    ficha.status = FichaAutorizacaoCusto.Status.RASCUNHO
                ficha.save()
                _gravar_formset_autorizacao(itens, ficha)
                if exigir:
                    menor = eh_menor_de_idade(ficha.data_nascimento)
                    papel = (
                        AssinaturaEletronica.Papel.RESPONSAVEL
                        if menor
                        else AssinaturaEletronica.Papel.PACIENTE
                    )
                    nome = (
                        ficha.nome_responsavel
                        if menor
                        else ficha.nome_completo
                    )
                    ficha.refresh_from_db()
                    hash_doc = texto_para_hash_autorizacao(ficha)
                    gravar_assinatura_manuscrita(
                        tipo_documento=(
                            AssinaturaEletronica.TipoDocumento.AUTORIZACAO_CUSTO
                        ),
                        documento_id=ficha.pk,
                        papel=papel,
                        nome_assinante=nome,
                        imagem_data_url=form.cleaned_data[
                            'assinatura_paciente_base64'
                        ],
                        conteudo_para_hash=hash_doc,
                        paciente=ficha.paciente,
                        cpf_assinante='' if menor else ficha.cpf,
                        usuario=request.user,
                        ip=_ip_do_pedido(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
            messages.success(request, 'Autorização salva.')
            if ficha.status == FichaAutorizacaoCusto.Status.RASCUNHO:
                return redirect(
                    'core:editar_ficha_autorizacao',
                    pk=ficha.paciente_id,
                    ficha_pk=ficha.pk,
                )
            return redirect(
                'core:ver_ficha_autorizacao',
                pk=ficha.paciente_id,
                ficha_pk=ficha.pk,
            )
    else:
        form = FichaAutorizacaoCustoForm(instance=ficha)
        itens = montar_itens_autorizacao_formset(
            instance=ficha, prefix='itens'
        )
    menor = eh_menor_de_idade(ficha.data_nascimento)
    voltar_consulta = request.GET.get('consulta') or (
        str(ficha.consulta_id) if ficha.consulta_id else ''
    )
    return render(request, 'core/form_ficha_autorizacao.html', {
        'form': form,
        'itens': itens,
        'ficha': ficha,
        'paciente': ficha.paciente,
        'menor': menor,
        'texto_declaracao': TEXTO_DECLARACAO_AUTORIZACAO,
        'voltar_consulta': voltar_consulta,
        'titulo': 'Autorização de itens com custo',
    })


def _gravar_formset_autorizacao(formset, ficha):
    for indice, item_form in enumerate(formset.forms):
        dados = item_form.cleaned_data
        if not dados:
            continue
        if dados.get('DELETE'):
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        if not item_form.linha_preenchida():
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        item = item_form.save(commit=False)
        item.ficha = ficha
        item.ordem = indice
        item.save()


def _gravar_formset_profissionais(formset, ficha, dentista):
    for indice, item_form in enumerate(formset.forms):
        dados = item_form.cleaned_data
        if not dados:
            continue
        if dados.get('DELETE'):
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        if not item_form.linha_preenchida():
            if item_form.instance.pk:
                item_form.instance.delete()
            continue
        item = item_form.save(commit=False)
        item.ficha = ficha
        item.ordem = indice
        if dentista and item.nome == dentista.nome_completo:
            item.dentista = dentista
        item.save()


