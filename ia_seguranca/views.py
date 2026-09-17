import logging
import os
import tempfile

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Consulta
from core.assinatura import gravar_assinatura_manuscrita
from core.evolucao import texto_para_hash_evolucao
from core.forms import RegistroEvolucaoClinicaForm
from core.models import AssinaturaEletronica, RegistroEvolucaoClinica
from core.permissoes import (
    dentista_do_usuario,
    usuario_pode_registrar_prontuario,
)

from .servicos import transcrever_e_registrar


logger = logging.getLogger(__name__)


def _sufixo_audio(content_type):
    return {
        'audio/webm': '.webm',
        'audio/ogg': '.ogg',
        'audio/wav': '.wav',
        'audio/x-wav': '.wav',
        'audio/mpeg': '.mp3',
        'audio/mp4': '.m4a',
        'audio/x-m4a': '.m4a',
    }[content_type]


def _salvar_audio_temporario(audio, consulta_id):
    """Persiste o upload com nome controlado e aplica o limite real de bytes."""
    content_type = (audio.content_type or '').split(';', 1)[0].strip().lower()
    if content_type not in settings.IA_AUDIO_CONTENT_TYPES:
        raise ValueError('Formato de áudio não permitido.')
    if audio.size is None or audio.size > settings.IA_AUDIO_MAX_BYTES:
        raise ValueError('O áudio excede o limite permitido.')

    destino = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb',
            prefix=f'consulta_{consulta_id}_',
            suffix=_sufixo_audio(content_type),
            delete=False,
        ) as arquivo:
            destino = arquivo.name
            for pedaco in audio.chunks():
                total += len(pedaco)
                if total > settings.IA_AUDIO_MAX_BYTES:
                    raise ValueError('O áudio excede o limite permitido.')
                arquivo.write(pedaco)
        return destino
    except Exception:
        if destino:
            try:
                os.unlink(destino)
            except OSError:
                pass
        raise


@login_required
@require_POST
def transcrever_consulta(request, pk):
    """Recebe um audio gravado no navegador e devolve a transcricao."""
    consulta = get_object_or_404(Consulta, pk=pk)
    if not usuario_pode_registrar_prontuario(
        request.user, consulta.paciente, consulta
    ):
        raise PermissionDenied

    from .models import ConsentimentoIA

    consentimento_valido = ConsentimentoIA.objects.filter(
        paciente=consulta.paciente,
        finalidade='transcricao_voz',
        concedido=True,
        concedido_em__isnull=False,
        revogado_em__isnull=True,
    ).exists()
    if not consentimento_valido:
        return JsonResponse(
            {'erro': 'Não há consentimento válido para transcrição de voz.'},
            status=403,
        )

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"erro": "Nenhum audio recebido."}, status=400)

    try:
        destino = _salvar_audio_temporario(audio, consulta.pk)
    except ValueError as exc:
        return JsonResponse({'erro': str(exc)}, status=400)

    try:
        registro = transcrever_e_registrar(
            destino,
            usuario=request.user,
            paciente=consulta.paciente,
            consulta=consulta,
        )
    except ValueError:
        return JsonResponse({'erro': 'Não foi possível validar o áudio.'}, status=400)
    except RuntimeError:
        return JsonResponse({'erro': 'Não foi possível processar o áudio agora.'}, status=503)
    except Exception:
        logger.exception('Falha inesperada ao transcrever consulta %s.', consulta.pk)
        return JsonResponse({'erro': 'Não foi possível processar o áudio agora.'}, status=503)
    finally:
        try:
            os.unlink(destino)
        except OSError:
            pass

    return JsonResponse({
        "registro_id": registro.id,
        "texto": registro.saida_sugerida,
    })


@login_required
@require_POST
def salvar_evolucao(request, pk):
    """Salva o texto revisado pelo dentista como evolucao clinica."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from .models import RegistroAuditoriaIA

    consulta = get_object_or_404(Consulta, pk=pk)
    if not usuario_pode_registrar_prontuario(
        request.user, consulta.paciente, consulta
    ):
        raise PermissionDenied

    texto = (request.POST.get("texto") or "").strip()
    procedimento = (request.POST.get("procedimento_etapa") or "").strip()
    registro_id = (request.POST.get("registro_id") or '').strip()

    if not texto:
        messages.error(request, "O texto da evolucao esta vazio.")
        return redirect('core:ficha_consulta', pk=pk)

    if not procedimento:
        messages.error(request, "Informe o procedimento/etapa antes de salvar.")
        return redirect('core:ficha_consulta', pk=pk)

    if not registro_id:
        messages.error(
            request,
            'A evolução por voz precisa estar vinculada à transcrição auditada.',
        )
        return redirect('core:ficha_consulta', pk=pk)

    dados_formulario = request.POST.copy()
    dados_formulario['data'] = consulta.data.isoformat()
    dados_formulario['procedimento_etapa'] = procedimento
    dados_formulario['descricao_clinica'] = texto
    form = RegistroEvolucaoClinicaForm(dados_formulario)
    if not form.is_valid():
        messages.error(
            request,
            'Complete os dados profissionais e a assinatura para salvar a evolução.',
        )
        return redirect('core:ficha_consulta', pk=pk)

    # O identificador vem do navegador e não é uma autorização: ele só pode
    # apontar para a transcrição desta consulta, criada pelo mesmo usuário e
    # ainda pendente de decisão.
    registro_auditoria = RegistroAuditoriaIA.objects.filter(
        pk=registro_id,
        paciente=consulta.paciente,
        consulta=consulta,
        usuario=request.user,
        recurso='transcricao_voz',
        decisao='pendente',
    ).first()
    if registro_auditoria is None:
        messages.error(request, 'Registro de auditoria incompatível.')
        return redirect('core:ficha_consulta', pk=pk)

    with transaction.atomic():
        registro = form.save(commit=False)
        registro.paciente = consulta.paciente
        registro.dentista = dentista_do_usuario(request.user)
        registro.criado_por = request.user
        registro.save()
        gravar_assinatura_manuscrita(
            tipo_documento=AssinaturaEletronica.TipoDocumento.EVOLUCAO,
            documento_id=registro.pk,
            papel=AssinaturaEletronica.Papel.DENTISTA,
            nome_assinante=registro.nome_profissional,
            imagem_data_url=form.cleaned_data['assinatura_base64'],
            conteudo_para_hash=texto_para_hash_evolucao(registro),
            paciente=consulta.paciente,
            usuario=request.user,
            ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        registro_auditoria.decisao = 'editada'
        registro_auditoria.texto_final = texto
        registro_auditoria.decidido_em = timezone.now()
        registro_auditoria.save(
            update_fields=['decisao', 'texto_final', 'decidido_em']
        )

    messages.success(request, "Evolucao clinica salva com sucesso.")
    return redirect('core:ficha_consulta', pk=pk)
