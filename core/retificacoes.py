from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .assinatura import gravar_assinatura_manuscrita
from .forms import _validar_png_opcional
from .integridade_documentos import tipos_documentos, verificar_integridade, texto_para_hash_retificacao, url_documento
from .models import RetificacaoDocumento
from .permissoes import usuario_pode_registrar_prontuario, dentista_do_usuario, usuario_pode_emitir_prescricao


class RetificacaoDocumentoForm(forms.ModelForm):
    assinatura_base64 = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        model = RetificacaoDocumento
        fields = ('nome_profissional', 'cro', 'justificativa', 'conteudo')

    def clean_assinatura_base64(self):
        if self.instance.prescricao_id:
            from .prescricoes import validar_assinatura_prescricao
            return validar_assinatura_prescricao(self.cleaned_data.get('assinatura_base64'))
        return _validar_png_opcional(self.cleaned_data.get('assinatura_base64'), True)


@require_http_methods(['GET', 'POST'])
def retificar_documento(request, tipo, pk):
    campos = {'evolucao': 'evolucao', 'anamnese': 'anamnese', 'plano_tratamento': 'plano', 'autorizacao_custo': 'autorizacao', 'prescricao': 'prescricao'}
    if tipo not in campos:
        raise Http404
    original = get_object_or_404(tipos_documentos()[tipo], pk=pk)
    if not usuario_pode_registrar_prontuario(request.user, original.paciente):
        raise PermissionDenied
    if tipo == 'prescricao' and not usuario_pode_emitir_prescricao(request.user, original.paciente):
        raise PermissionDenied
    dentista = dentista_do_usuario(request.user)
    registro = RetificacaoDocumento(autor=request.user, **{campos[tipo]: original})
    form = RetificacaoDocumentoForm(request.POST or None, instance=registro, initial={
        'nome_profissional': dentista.nome_completo if dentista else request.user.get_full_name(),
    })
    if tipo == 'prescricao':
        form.fields['nome_profissional'].disabled = True
    integridade = verificar_integridade(original)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            original = tipos_documentos()[tipo].objects.select_for_update().get(pk=pk)
            integridade = verificar_integridade(original)
            if not usuario_pode_registrar_prontuario(request.user, original.paciente):
                raise PermissionDenied
            if tipo == 'prescricao' and not usuario_pode_emitir_prescricao(request.user, original.paciente):
                raise PermissionDenied
            if not integridade.integra or (tipo == 'prescricao' and original.status != 'assinada'):
                form.add_error(None, 'Retificação bloqueada: a integridade do original não foi confirmada.')
            else:
                registro = form.save()
                gravar_assinatura_manuscrita(
                    tipo_documento='retificacao', documento_id=registro.pk,
                    papel='dentista', nome_assinante=registro.nome_profissional,
                    imagem_data_url=form.cleaned_data['assinatura_base64'],
                    conteudo_para_hash=texto_para_hash_retificacao(registro),
                    paciente=original.paciente, usuario=request.user,
                    ip=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                if tipo == 'prescricao':
                    from .prescricoes import _auditar
                    _auditar(request, original, f'Retificação {registro.pk} assinada')
                return redirect(url_documento(original))
    return render(request, 'core/form_retificacao.html', {
        'titulo': 'Retificação de documento', 'paciente': original.paciente,
        'form': form, 'integridade': integridade, 'url_original': url_documento(original),
    })
