from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.db import IntegrityError, OperationalError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from core.models import Paciente
from .models import Exame
from .forms import ExameForm, JustificativaForm
from .permissoes import pode_corrigir
from .services import BloqueioTransitorioEsgotado, autorizar, incluir, invalidar, reinspecionar, evento
from .uploads import UploadPrivado
from .storage import abrir_verificado


def paciente_autorizado(request, paciente_pk):
    paciente = get_object_or_404(Paciente, pk=paciente_pk)
    autorizar(request.user, paciente)
    return paciente


def objeto(request, paciente_pk, pk):
    paciente = paciente_autorizado(request, paciente_pk)
    exame = Exame.objects.filter(pk=pk, paciente=paciente).first()
    if exame is None:
        evento(request.user, 'acesso_negado', 'objeto_indisponivel')
        from django.http import Http404
        raise Http404
    return exame


@login_required
@never_cache
@require_GET
def listar(request, paciente_pk):
    paciente = paciente_autorizado(request, paciente_pk)
    evento(request.user, 'listagem')
    return render(request, 'exames/lista.html', {'paciente': paciente, 'exames': Exame.objects.filter(paciente=paciente)})


@csrf_exempt
@login_required
@never_cache
def novo(request, paciente_pk, pk=None):
    paciente = paciente_autorizado(request, paciente_pk)
    anterior = objeto(request, paciente_pk, pk) if pk else None
    if anterior and not pode_corrigir(request.user, anterior):
        evento(request.user, 'acesso_negado', 'negado')
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    handler = UploadPrivado(request)
    request.upload_handlers = [handler]
    try:
        return _novo(request, paciente, anterior)
    except (OSError, ImproperlyConfigured, OperationalError, ValidationError):
        evento(request.user, 'falha_armazenamento', 'indisponivel')
        return HttpResponse('Armazenamento ou processamento indisponível. Nenhum arquivo foi liberado.', status=503)
    finally:
        handler.fechar()


@csrf_protect
def _novo(request, paciente, anterior):
    if request.method not in ('GET', 'POST'):
        return HttpResponse(status=405)
    form = ExameForm(request.POST if request.method == 'POST' else None,
                     request.FILES if request.method == 'POST' else None,
                     paciente=paciente, user=request.user, anterior=anterior)
    if request.method == 'POST':
        try:
            if getattr(request, 'exames_upload_erro', False):
                raise ValidationError('Envie somente um arquivo por vez, respeitando o limite de tamanho.')
            if form.is_valid():
                exame = incluir(request.user, paciente, form.cleaned_data, anterior)
                messages.success(request, 'Arquivo registrado. Consulte abaixo o resultado da inspeção.')
                return redirect('core:exames:detalhe', paciente_pk=paciente.pk, pk=exame.pk)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else 'Registro já corrigido por outra operação. Atualize a página.')
        evento(request.user, 'upload_rejeitado', 'validacao')
    return render(request, 'exames/form.html', {'paciente': paciente, 'form': form, 'anterior': anterior})


@login_required
@never_cache
@require_GET
def detalhe(request, paciente_pk, pk):
    exame = objeto(request, paciente_pk, pk)
    evento(request.user, 'consulta', exame=exame)
    return render(request, 'exames/detalhe.html', {'paciente': exame.paciente, 'exame': exame,
                  'pode_corrigir': pode_corrigir(request.user, exame), 'form': JustificativaForm()})


@login_required
@never_cache
@require_GET
def baixar(request, paciente_pk, pk):
    exame = objeto(request, paciente_pk, pk)
    if exame.seguranca != 'liberado':
        evento(request.user, 'download_negado', 'seguranca', exame)
        return HttpResponse('Arquivo bloqueado. Consulte o estado da inspeção.', status=409)
    try:
        arquivo = abrir_verificado(exame)
    except (ValidationError, OSError):
        evento(request.user, 'integridade_falhou', 'bloqueado', exame)
        return HttpResponse('Arquivo indisponível: falha de integridade.', status=409)
    try:
        evento(request.user, 'download_iniciado', exame=exame)
    except Exception:
        arquivo.close()
        raise
    extensao = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf'}[exame.tipo]
    resposta = FileResponse(arquivo, as_attachment=True, filename=f'exame-{exame.pk}.{extensao}', content_type=exame.tipo)
    resposta['X-Content-Type-Options'] = 'nosniff'
    resposta['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return resposta


@login_required
@never_cache
@require_POST
def invalidacao(request, paciente_pk, pk):
    exame = objeto(request, paciente_pk, pk)
    form = JustificativaForm(request.POST)
    if form.is_valid():
        try:
            invalidar(request.user, exame, form.cleaned_data['justificativa'])
            messages.success(request, 'Registro invalidado. Original e histórico preservados.')
        except (ValidationError, IntegrityError):
            messages.error(request, 'Registro já invalidado ou substituído.')
        except BloqueioTransitorioEsgotado:
            messages.error(request, 'Não foi possível invalidar o registro agora. Tente novamente.')
    else:
        messages.error(request, 'Informe uma justificativa de até 1000 caracteres.')
    return redirect('core:exames:detalhe', paciente_pk=paciente_pk, pk=pk)


@login_required
@never_cache
@require_POST
def inspecao(request, paciente_pk, pk):
    exame = objeto(request, paciente_pk, pk)
    try:
        reinspecionar(request.user, exame)
        messages.info(request, 'Inspeção registrada. Confira o estado do arquivo.')
    except ValidationError:
        messages.error(request, 'Arquivo não está pendente de inspeção.')
    return redirect('core:exames:detalhe', paciente_pk=paciente_pk, pk=pk)
