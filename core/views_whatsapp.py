import hmac
import json
import os
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .models import MensagemWhatsApp
from .permissoes import (
    usuario_pode_preparar_lembretes,
    usuario_pode_simular_resposta_whatsapp,
    usuario_pode_ver_lembretes_whatsapp,
)
from .whatsapp import (
    ErroWhatsApp,
    assinatura_webhook_valida,
    preparar_lembretes,
    registrar_resposta,
)


def _data_da_lista(request):
    bruto = (request.GET.get('data') or '').strip()
    if bruto:
        try:
            return datetime.strptime(bruto, '%Y-%m-%d').date()
        except ValueError:
            pass
    return timezone.localdate() + timedelta(days=1)


def listar_lembretes_whatsapp(request):
    if not usuario_pode_ver_lembretes_whatsapp(request.user):
        raise PermissionDenied
    data = _data_da_lista(request)
    lembretes = list(
        MensagemWhatsApp.objects.filter(
            direcao=MensagemWhatsApp.Direcao.ENVIADA,
            consulta__data=data,
        )
        .select_related('paciente', 'consulta', 'consulta__dentista')
        .prefetch_related(
            Prefetch(
                'respostas',
                queryset=MensagemWhatsApp.objects.order_by('-criado_em', '-pk'),
            )
        )
        .order_by('consulta__hora_inicio', 'pk')
    )
    for lembrete in lembretes:
        respostas = list(lembrete.respostas.all())
        lembrete.resposta_exibida = respostas[0] if respostas else None
    atencao = [
        item for item in lembretes
        if item.resposta_exibida and item.resposta_exibida.acao in {
            MensagemWhatsApp.Acao.DESMARCOU,
            MensagemWhatsApp.Acao.PRECISA_ATENCAO,
        }
    ]
    return render(request, 'core/listar_lembretes_whatsapp.html', {
        'lembretes': lembretes,
        'data': data,
        'total_atencao': len(atencao),
        'pode_simular': usuario_pode_simular_resposta_whatsapp(request.user),
    })


@require_POST
def preparar_lembretes_amanha(request):
    if not usuario_pode_preparar_lembretes(request.user):
        raise PermissionDenied
    amanha = timezone.localdate() + timedelta(days=1)
    try:
        quantidade = preparar_lembretes(amanha)
    except ErroWhatsApp as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, f'Lembretes preparados: {quantidade}.')
    return redirect(f"{reverse('core:listar_consultas')}?data={amanha.isoformat()}")


@require_POST
def simular_resposta_whatsapp(request, pk):
    if not usuario_pode_simular_resposta_whatsapp(request.user):
        raise PermissionDenied
    lembrete = get_object_or_404(
        MensagemWhatsApp,
        pk=pk,
        direcao=MensagemWhatsApp.Direcao.ENVIADA,
    )
    texto = (request.POST.get('texto') or '').strip()
    if not texto:
        messages.error(request, 'Informe o texto da resposta do paciente.')
    else:
        registrar_resposta(lembrete.telefone, texto)
        messages.success(request, 'Resposta simulada registrada.')
    destino = reverse('core:listar_lembretes_whatsapp')
    if lembrete.consulta_id:
        destino = f'{destino}?data={lembrete.consulta.data.isoformat()}'
    return redirect(destino)


def _mensagens_do_payload(payload):
    mensagens = []
    for entrada in payload.get('entry') or []:
        for mudanca in entrada.get('changes') or []:
            valor = mudanca.get('value') or {}
            for mensagem in valor.get('messages') or []:
                mensagens.append(mensagem)
    return mensagens


@login_not_required
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def whatsapp_webhook(request):
    if request.method == 'GET':
        token = (request.GET.get('hub.verify_token') or '').strip()
        desafio = request.GET.get('hub.challenge') or ''
        modo = (request.GET.get('hub.mode') or '').strip()
        esperado = (os.environ.get('WHATSAPP_VERIFY_TOKEN') or '').strip()
        if (
            modo == 'subscribe'
            and esperado
            and desafio
            and hmac.compare_digest(token, esperado)
        ):
            return HttpResponse(desafio, content_type='text/plain')
        return HttpResponse(status=403)

    corpo = request.body or b''
    cabecalho = request.headers.get('X-Hub-Signature-256', '')
    if not assinatura_webhook_valida(corpo, cabecalho):
        return HttpResponse(status=403)
    try:
        payload = json.loads(corpo.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)
    for mensagem in _mensagens_do_payload(payload):
        texto = ''
        if mensagem.get('type') == 'text':
            texto = ((mensagem.get('text') or {}).get('body') or '')
        else:
            texto = mensagem.get('type') or ''
        try:
            registrar_resposta(
                mensagem.get('from') or '',
                texto,
                id_externo=mensagem.get('id') or '',
            )
        except ErroWhatsApp:
            continue
    return JsonResponse({'status': 'ok'})
