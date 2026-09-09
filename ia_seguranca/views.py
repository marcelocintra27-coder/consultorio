import tempfile
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Consulta

from .servicos import transcrever_e_registrar


@login_required
@require_POST
def transcrever_consulta(request, pk):
    """Recebe um audio gravado no navegador e devolve a transcricao."""
    consulta = get_object_or_404(Consulta, pk=pk)

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"erro": "Nenhum audio recebido."}, status=400)

    destino = Path(tempfile.gettempdir()) / f"consulta_{pk}_{audio.name}"
    with open(destino, "wb") as f:
        for pedaco in audio.chunks():
            f.write(pedaco)

    try:
        registro = transcrever_e_registrar(
            destino,
            usuario=request.user,
            paciente=consulta.paciente,
        )
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)
    finally:
        try:
            destino.unlink()
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

    from core.models import RegistroEvolucaoClinica
    from core.permissoes import dentista_do_usuario

    from .models import RegistroAuditoriaIA

    consulta = get_object_or_404(Consulta, pk=pk)

    texto = (request.POST.get("texto") or "").strip()
    procedimento = (request.POST.get("procedimento_etapa") or "").strip()
    registro_id = request.POST.get("registro_id")

    if not texto:
        messages.error(request, "O texto da evolucao esta vazio.")
        return redirect("ficha_consulta", pk=pk)

    if not procedimento:
        messages.error(request, "Informe o procedimento/etapa antes de salvar.")
        return redirect("ficha_consulta", pk=pk)

    RegistroEvolucaoClinica.objects.create(
        paciente=consulta.paciente,
        data=consulta.data,
        procedimento_etapa=procedimento,
        descricao_clinica=texto,
        dentista=dentista_do_usuario(request.user),
        criado_por=request.user,
    )

    if registro_id:
        RegistroAuditoriaIA.objects.filter(pk=registro_id).update(
            decisao="editada",
            texto_final=texto,
            decidido_em=timezone.now(),
        )

    messages.success(request, "Evolucao clinica salva com sucesso.")
    return redirect("ficha_consulta", pk=pk)
