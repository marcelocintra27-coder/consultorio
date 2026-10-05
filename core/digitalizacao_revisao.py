"""Lista, foto protegida e revisão das fichas digitalizadas."""
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Consulta,
    DigitalizacaoFicha,
    Paciente,
    RegistroAcesso,
    TrocaPacienteDigitalizacao,
)
from .permissoes import (
    digitalizacoes_visiveis,
    dentista_do_usuario,
    usuario_e_administrador,
    usuario_pode_enviar_digitalizacao,
    usuario_pode_listar_digitalizacoes,
    usuario_pode_marcar_engano,
    usuario_pode_receber_troca_digitalizacao,
    usuario_pode_revisar_digitalizacao,
    usuario_pode_trocar_paciente_digitalizacao,
    _e_secretaria,
)

POR_PAGINA = 20
TIPOS_FOTO = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


def enviadas_hoje(user):
    inicio, fim = _janela(timezone.localdate(), timezone.localdate())
    return DigitalizacaoFicha.objects.filter(
        digitalizado_por=user,
        criado_em__gte=inicio,
        criado_em__lt=fim,
    ).select_related('paciente').order_by('-criado_em')


def ficha_recem_enviada(user, bruto):
    bruto = (bruto or '').strip()
    if not bruto.isdigit():
        return None
    return digitalizacoes_visiveis(user).filter(
        pk=int(bruto),
    ).select_related('paciente').first()


def fichas_recem_enviadas(user, request):
    lote = (request.GET.get('lote') or '').strip()
    if lote:
        try:
            identificador = uuid.UUID(lote)
        except ValueError:
            return []
        return list(
            digitalizacoes_visiveis(user).filter(lote=identificador)
            .select_related('paciente')
            .order_by('ordem', 'pk')
        )
    uma = ficha_recem_enviada(user, request.GET.get('enviada'))
    return [uma] if uma else []


ROTULOS_TIPO = {
    'cadastro': ('cadastro', 'cadastros'),
    'anamnese': ('anamnese', 'anamneses'),
    'evolucao': ('evolução', 'evoluções'),
    'outro': ('outro', 'outros'),
}


class GrupoDigitalizacao:
    def __init__(self, paciente):
        self.paciente = paciente
        self.ids = []
        self.contagens = {}
        self.pendentes = 0
        self.refazer = 0
        self.motivos = []
        self.refazer_tipo = ''
        self.ultimo = None

    @property
    def nome(self):
        if self.paciente is None:
            return 'Sem paciente'
        return self.paciente.nome_completo

    @property
    def resumo_tipos(self):
        partes = []
        for valor, _rotulo in DigitalizacaoFicha.Tipo.choices:
            quantidade = self.contagens.get(valor, 0)
            if not quantidade:
                continue
            singular, plural = ROTULOS_TIPO[valor]
            palavra = singular if quantidade == 1 else plural
            partes.append(f'{quantidade} {palavra}')
        return ', '.join(partes)

    def adicionar(self, ficha):
        self.ids.append(ficha.pk)
        self.contagens[ficha.tipo] = self.contagens.get(ficha.tipo, 0) + 1
        if ficha.status == DigitalizacaoFicha.Status.PENDENTE_REVISAO:
            self.pendentes += 1
        elif ficha.status == DigitalizacaoFicha.Status.REFAZER:
            self.refazer += 1
            if ficha.motivo_refazer and ficha.motivo_refazer not in self.motivos:
                self.motivos.append(ficha.motivo_refazer)
            if not self.refazer_tipo:
                self.refazer_tipo = ficha.tipo
        elif ficha.status == DigitalizacaoFicha.Status.ENGANO:
            if ficha.motivo_engano and ficha.motivo_engano not in self.motivos:
                self.motivos.append(ficha.motivo_engano)
        if self.ultimo is None:
            self.ultimo = ficha


def agrupar_fichas(fichas):
    grupos = {}
    ordem = []
    for ficha in fichas.order_by('-criado_em', '-pk'):
        chave = ficha.paciente_id
        grupo = grupos.get(chave)
        if grupo is None:
            grupo = GrupoDigitalizacao(ficha.paciente)
            grupos[chave] = grupo
            ordem.append(chave)
        grupo.adicionar(ficha)
    return [grupos[chave] for chave in ordem]


def anotar_acoes(user, ficha):
    ficha.pode_revisar = usuario_pode_revisar_digitalizacao(user, ficha)
    ficha.pode_engano = usuario_pode_marcar_engano(user, ficha)
    ficha.pode_trocar = usuario_pode_trocar_paciente_digitalizacao(user, ficha)
    ficha.lista_troca = list(pacientes_para_troca(user, ficha))
    return ficha


def pacientes_para_troca(user, ficha):
    if not usuario_pode_trocar_paciente_digitalizacao(user, ficha):
        return Paciente.objects.none()
    if usuario_e_administrador(user):
        pacientes = Paciente.objects.filter(ativo=True)
    else:
        dentista = dentista_do_usuario(user)
        if dentista is None:
            return Paciente.objects.none()
        vinculados = Consulta.objects.filter(dentista=dentista).values('paciente_id')
        pacientes = Paciente.objects.filter(pk__in=vinculados, ativo=True)
    if ficha.paciente_id:
        pacientes = pacientes.exclude(pk=ficha.paciente_id)
    return pacientes.order_by('nome_completo')


def inicial_envio(request, user):
    inicial = {}
    bruto = (request.GET.get('paciente') or '').strip()
    if bruto.isdigit():
        paciente = Paciente.objects.filter(pk=int(bruto), ativo=True).first()
        if paciente and usuario_pode_enviar_digitalizacao(user, paciente):
            inicial['paciente'] = paciente.pk
    tipo = (request.GET.get('tipo') or '').strip()
    if tipo in DigitalizacaoFicha.Tipo.values:
        inicial['tipo'] = tipo
    return inicial


def _janela(data_inicial, data_final):
    fuso = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(data_inicial, time.min), fuso)
    fim = timezone.make_aware(
        datetime.combine(data_final + timedelta(days=1), time.min), fuso,
    )
    return inicio, fim


def _ficha_ou_404(user, pk):
    if not usuario_pode_listar_digitalizacoes(user):
        raise PermissionDenied
    return get_object_or_404(digitalizacoes_visiveis(user), pk=pk)


def _aplicar_filtros(request, fichas):
    situacao = (request.GET.get('situacao') or '').strip()
    if situacao in DigitalizacaoFicha.Status.values:
        fichas = fichas.filter(status=situacao)
    nome = (request.GET.get('paciente') or '').strip()
    if nome:
        fichas = fichas.filter(paciente__nome_completo__icontains=nome)
    enviado = (request.GET.get('enviado_por') or '').strip()
    if enviado.isdigit():
        fichas = fichas.filter(digitalizado_por_id=int(enviado))
    de = _data(request.GET.get('de'))
    ate = _data(request.GET.get('ate'))
    aviso = ''
    if de and ate and ate < de:
        aviso = 'A data final não pode ser anterior à inicial.'
    else:
        if de:
            inicio, _fim = _janela(de, de)
            fichas = fichas.filter(criado_em__gte=inicio)
        if ate:
            _inicio, fim = _janela(ate, ate)
            fichas = fichas.filter(criado_em__lt=fim)
    return fichas, {
        'situacao': situacao,
        'paciente': nome,
        'enviado_por': enviado,
        'de': request.GET.get('de') or '',
        'ate': request.GET.get('ate') or '',
        'aviso': aviso,
    }


def _data(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _query(request, pagina):
    dados = request.GET.copy()
    dados['pagina'] = str(pagina)
    return dados.urlencode()


@login_required
@require_GET
def listar_digitalizacoes(request):
    if not usuario_pode_listar_digitalizacoes(request.user):
        raise PermissionDenied
    visiveis = digitalizacoes_visiveis(request.user)
    fichas, filtros = _aplicar_filtros(request, visiveis)
    if filtros['situacao'] != DigitalizacaoFicha.Status.ENGANO:
        fichas = fichas.exclude(status=DigitalizacaoFicha.Status.ENGANO)
    grupos = agrupar_fichas(fichas)
    paginas = Paginator(grupos, POR_PAGINA)
    pagina = paginas.get_page(request.GET.get('pagina') or 1)
    secretaria = (
        _e_secretaria(request.user) and not usuario_e_administrador(request.user)
    )
    enviadores = User.objects.filter(
        pk__in=visiveis.values('digitalizado_por_id'),
    ).order_by('first_name', 'username')
    return render(request, 'core/listar_digitalizacoes.html', {
        'titulo': 'Minhas fichas enviadas' if secretaria else 'Fichas digitalizadas',
        'pagina': pagina,
        'filtros': filtros,
        'situacoes': DigitalizacaoFicha.Status.choices,
        'enviadores': enviadores,
        'pendentes': visiveis.filter(
            status=DigitalizacaoFicha.Status.PENDENTE_REVISAO,
        ).count(),
        'refazer': visiveis.filter(status=DigitalizacaoFicha.Status.REFAZER).count(),
        'secretaria': secretaria,
        'query_anterior': _query(request, pagina.previous_page_number()) if pagina.has_previous() else '',
        'query_proxima': _query(request, pagina.next_page_number()) if pagina.has_next() else '',
    })


def _fichas_do_paciente(user, paciente_id):
    if not usuario_pode_listar_digitalizacoes(user):
        raise PermissionDenied
    return digitalizacoes_visiveis(user).filter(paciente_id=paciente_id)


@login_required
@require_GET
def folhas_paciente(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    fichas = list(
        _fichas_do_paciente(request.user, paciente.pk)
        .order_by('ordem', 'criado_em', 'pk')
    )
    if not fichas:
        raise Http404
    for ficha in fichas:
        anotar_acoes(request.user, ficha)
    return render(request, 'core/folhas_paciente_digitalizacao.html', {
        'titulo': paciente.nome_completo,
        'paciente': paciente,
        'fichas': fichas,
        'pode_conferir_todas': any(ficha.pode_revisar and ficha.status == DigitalizacaoFicha.Status.PENDENTE_REVISAO for ficha in fichas),
        'secretaria': (
            _e_secretaria(request.user) and not usuario_e_administrador(request.user)
        ),
    })


@login_required
@require_GET
def folhas_sem_paciente(request):
    fichas = list(
        _fichas_do_paciente(request.user, None)
        .order_by('ordem', 'criado_em', 'pk')
    )
    if not fichas:
        raise Http404
    for ficha in fichas:
        anotar_acoes(request.user, ficha)
    return render(request, 'core/folhas_paciente_digitalizacao.html', {
        'titulo': 'Sem paciente',
        'paciente': None,
        'fichas': fichas,
        'pode_conferir_todas': any(ficha.pode_revisar and ficha.status == DigitalizacaoFicha.Status.PENDENTE_REVISAO for ficha in fichas),
        'secretaria': (
            _e_secretaria(request.user) and not usuario_e_administrador(request.user)
        ),
    })


@login_required
@require_POST
def conferir_folhas_paciente(request, pk):
    return _conferir_folhas(request, pk)


@login_required
@require_POST
def conferir_folhas_sem_paciente(request):
    return _conferir_folhas(request, None)


def _conferir_folhas(request, paciente_id):
    if not usuario_pode_listar_digitalizacoes(request.user):
        raise PermissionDenied
    fichas = list(
        digitalizacoes_visiveis(request.user).filter(
            paciente_id=paciente_id,
            status=DigitalizacaoFicha.Status.PENDENTE_REVISAO,
        )
    )
    if paciente_id is None:
        destino = redirect('core:folhas_digitalizacao_sem_paciente')
    else:
        destino = redirect('core:folhas_digitalizacao_paciente', pk=paciente_id)
    if not fichas:
        raise Http404
    if not any(usuario_pode_revisar_digitalizacao(request.user, ficha) for ficha in fichas):
        raise PermissionDenied
    agora = timezone.now()
    with transaction.atomic():
        for ficha in fichas:
            if not usuario_pode_revisar_digitalizacao(request.user, ficha):
                continue
            ficha.status = DigitalizacaoFicha.Status.CONFIRMADA
            ficha.motivo_refazer = ''
            ficha.revisado_por = request.user
            ficha.revisado_em = agora
            ficha.save(update_fields=[
                'status', 'motivo_refazer', 'revisado_por', 'revisado_em',
            ])
    messages.success(request, 'Folhas pendentes marcadas como conferidas.')
    return destino


@login_required
@require_GET
def detalhe_digitalizacao(request, pk):
    ficha = anotar_acoes(request.user, _ficha_ou_404(request.user, pk))
    return render(request, 'core/detalhe_digitalizacao.html', {
        'ficha': ficha,
        'pode_revisar': ficha.pode_revisar,
        'pode_engano': ficha.pode_engano,
        'pode_trocar': ficha.pode_trocar,
        'pacientes_troca': ficha.lista_troca,
        'trocas': ficha.trocas_paciente.select_related(
            'paciente_anterior', 'paciente_novo', 'trocado_por',
        ),
        'secretaria': (
            _e_secretaria(request.user) and not usuario_e_administrador(request.user)
        ),
    })


@login_required
@require_GET
def foto_digitalizacao(request, pk):
    ficha = _ficha_ou_404(request.user, pk)
    nome = ficha.imagem.name or ''
    extensao = Path(nome).suffix.lower()
    tipo = TIPOS_FOTO.get(extensao)
    if not tipo or not ficha.imagem:
        raise Http404
    try:
        arquivo = ficha.imagem.open('rb')
    except OSError as exc:
        raise Http404 from exc
    try:
        RegistroAcesso.objects.create(
            usuario=request.user,
            tipo=RegistroAcesso.Tipo.ABRIU_FOTO,
            digitalizacao=ficha,
        )
    except Exception:
        arquivo.close()
        raise
    resposta = FileResponse(
        arquivo,
        content_type=tipo,
        filename=f'ficha-{ficha.pk}{extensao}',
    )
    resposta['Content-Disposition'] = f'inline; filename="ficha-{ficha.pk}{extensao}"'
    resposta['X-Content-Type-Options'] = 'nosniff'
    resposta['Cache-Control'] = 'private, no-store'
    return resposta


@login_required
@require_POST
def revisar_digitalizacao(request, pk):
    ficha = _ficha_ou_404(request.user, pk)
    if not usuario_pode_revisar_digitalizacao(request.user, ficha):
        raise PermissionDenied
    acao = (request.POST.get('acao') or '').strip()
    if acao == 'conferida':
        ficha.status = DigitalizacaoFicha.Status.CONFIRMADA
        ficha.motivo_refazer = ''
    elif acao == 'refazer':
        motivo = (request.POST.get('motivo_refazer') or '').strip()
        if not motivo:
            messages.error(request, 'Informe o motivo para refazer a foto.')
            return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
        if len(motivo) > 2000:
            messages.error(request, 'O motivo deve ter até 2000 caracteres.')
            return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
        ficha.status = DigitalizacaoFicha.Status.REFAZER
        ficha.motivo_refazer = motivo
    else:
        return HttpResponse('Ação de revisão inválida.', status=400)
    ficha.revisado_por = request.user
    ficha.revisado_em = timezone.now()
    ficha.save(update_fields=[
        'status', 'motivo_refazer', 'revisado_por', 'revisado_em',
    ])
    messages.success(request, f'Ficha marcada como {ficha.get_status_display()}.')
    return redirect('core:detalhe_digitalizacao', pk=ficha.pk)


@login_required
@require_POST
def marcar_engano_digitalizacao(request, pk):
    ficha = _ficha_ou_404(request.user, pk)
    if not usuario_pode_marcar_engano(request.user, ficha):
        raise PermissionDenied
    motivo = (request.POST.get('motivo_engano') or '').strip()
    if len(motivo) > 2000:
        messages.error(request, 'O motivo deve ter até 2000 caracteres.')
        return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
    ficha.status = DigitalizacaoFicha.Status.ENGANO
    ficha.motivo_engano = motivo
    ficha.save(update_fields=['status', 'motivo_engano'])
    messages.success(request, 'Ficha marcada como enviada por engano.')
    return redirect('core:detalhe_digitalizacao', pk=ficha.pk)


@login_required
@require_POST
def trocar_paciente_digitalizacao(request, pk):
    ficha = _ficha_ou_404(request.user, pk)
    if not usuario_pode_trocar_paciente_digitalizacao(request.user, ficha):
        raise PermissionDenied
    motivo = (request.POST.get('motivo') or '').strip()
    if not motivo:
        messages.error(request, 'Informe o motivo da troca de paciente.')
        return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
    if len(motivo) > 2000:
        messages.error(request, 'O motivo deve ter até 2000 caracteres.')
        return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
    bruto = (request.POST.get('paciente') or '').strip()
    novo = Paciente.objects.filter(pk=int(bruto), ativo=True).first() if bruto.isdigit() else None
    if not usuario_pode_receber_troca_digitalizacao(request.user, novo):
        raise PermissionDenied
    if novo.pk == ficha.paciente_id:
        messages.error(request, 'Escolha um paciente diferente.')
        return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
    anterior_id = ficha.paciente_id
    with transaction.atomic():
        TrocaPacienteDigitalizacao.objects.create(
            ficha=ficha,
            paciente_anterior_id=anterior_id,
            paciente_novo=novo,
            motivo=motivo,
            trocado_por=request.user,
        )
        ficha.paciente = novo
        ficha.save(update_fields=['paciente'])
    messages.success(request, f'Paciente alterado para {novo.nome_completo}.')
    return redirect('core:detalhe_digitalizacao', pk=ficha.pk)
