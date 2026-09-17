"""Fluxo de prescrições: autoria profissional, rascunho e assinatura existente."""
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from django import forms
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_GET

from .assinatura import gravar_assinatura_manuscrita, png_de_data_url
from .forms import _validar_png_opcional
from .integridade_documentos import verificar_integridade, contexto_integridade, assinaturas_documento
from .models import Paciente, Prescricao, ItemPrescricao
from .permissoes import usuario_pode_acessar_prontuario, usuario_pode_emitir_prescricao, dentista_do_usuario
from .prescricao_conteudo import texto_para_hash_prescricao


def validar_assinatura_prescricao(valor, obrigatoria=True):
    valor = _validar_png_opcional(valor, obrigatoria)
    if valor:
        try:
            with Image.open(BytesIO(png_de_data_url(valor))) as imagem:
                if imagem.format != 'PNG' or max(imagem.size) > 4096:
                    raise ValueError('Formato ou dimensão inválida.')
                imagem.verify()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError('Assinatura PNG inválida. Desenhe novamente.') from exc
    return valor


class PrescricaoForm(forms.ModelForm):
    assinatura_base64 = forms.CharField(required=False, widget=forms.HiddenInput())
    versao = forms.IntegerField(min_value=0, widget=forms.HiddenInput())

    class Meta:
        model = Prescricao
        fields = ('cro', 'texto_livre', 'orientacoes')
        widgets = {'texto_livre': forms.Textarea(attrs={'rows': 4}), 'orientacoes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, assinar=False, **kwargs):
        self.assinar = assinar
        super().__init__(*args, **kwargs)
        self.fields['versao'].initial = self.instance.versao if self.instance.pk else 0
        self.fields['cro'].required = assinar
        for campo in ('texto_livre', 'orientacoes'):
            self.fields[campo].max_length = 10000

    def clean_assinatura_base64(self):
        return validar_assinatura_prescricao(self.cleaned_data.get('assinatura_base64'), self.assinar)


class ItemPrescricaoForm(forms.ModelForm):
    class Meta:
        model = ItemPrescricao
        fields = ('medicamento', 'concentracao_apresentacao', 'quantidade', 'posologia', 'via', 'duracao', 'orientacoes')
        widgets = {'posologia': forms.Textarea(attrs={'rows': 2}), 'orientacoes': forms.Textarea(attrs={'rows': 2})}


class BaseItensPrescricaoFormSet(BaseInlineFormSet):
    def __init__(self, *args, assinar=False, **kwargs):
        self.assinar = assinar
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            dados = form.cleaned_data
            item = dados.get('id')
            if item and item.ficha_id != self.instance.pk:
                raise forms.ValidationError('Medicamento não pertence a esta prescrição.')
            if not dados or dados.get('DELETE'):
                continue
            if self.assinar:
                if not (dados.get('medicamento') or '').strip():
                    form.add_error('medicamento', 'Informe o medicamento.')
                if not (dados.get('posologia') or '').strip():
                    form.add_error('posologia', 'Informe a posologia.')


ItensPrescricaoFormSet = inlineformset_factory(
    Prescricao, ItemPrescricao, form=ItemPrescricaoForm,
    formset=BaseItensPrescricaoFormSet, extra=1, can_delete=True,
    max_num=50, validate_max=True, absolute_max=60,
)


def _paciente_autorizado(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    if not usuario_pode_acessar_prontuario(request.user, paciente):
        raise PermissionDenied
    return paciente


def _auditar(request, ficha, evento, nova=False):
    LogEntry.objects.create(
        user=request.user, content_type=ContentType.objects.get_for_model(ficha),
        object_id=str(ficha.pk), object_repr=f'Prescrição {ficha.pk}',
        action_flag=ADDITION if nova else CHANGE,
        change_message=f'{evento}; versão {ficha.versao}.',
    )


@never_cache
@require_GET
def listar_prescricoes(request, pk):
    paciente = _paciente_autorizado(request, pk)
    return render(request, 'core/listar_prescricoes.html', {
        'titulo': 'Prescrições', 'paciente': paciente,
        'prescricoes': paciente.prescricoes.select_related('dentista'),
        'pode_emitir': usuario_pode_emitir_prescricao(request.user, paciente),
    })


@never_cache
@require_http_methods(['GET', 'POST'])
def editar_prescricao(request, pk, ficha_pk=None):
    paciente = _paciente_autorizado(request, pk)
    if not usuario_pode_emitir_prescricao(request.user, paciente):
        raise PermissionDenied
    # O bloqueio da linha e a versão impedem gravação de um formulário antigo
    # sobre uma nova edição ou sobre a assinatura feita em outra aba.
    with transaction.atomic():
        if ficha_pk:
            qs = Prescricao.objects.select_for_update() if request.method == 'POST' else Prescricao.objects
            ficha = get_object_or_404(qs, pk=ficha_pk, paciente=paciente)
            if not usuario_pode_emitir_prescricao(request.user, paciente, ficha):
                raise PermissionDenied
            if ficha.status != Prescricao.Status.RASCUNHO:
                if request.method == 'POST':
                    return HttpResponse('Prescrição assinada é imutável. Utilize retificação.', status=409)
                return redirect('core:ver_prescricao', pk=pk, ficha_pk=ficha.pk)
        else:
            profissional = dentista_do_usuario(request.user)
            ficha = Prescricao(
                paciente=paciente, dentista=profissional, criado_por=request.user,
                nome_paciente=paciente.nome_completo, cpf_paciente=paciente.cpf or '',
                data_nascimento_paciente=paciente.data_nascimento,
                nome_profissional=profissional.nome_completo,
            )
        versao_atual = ficha.versao if ficha.pk else 0
        acao = request.POST.get('acao', 'rascunho')
        assinar = acao == 'assinar'
        form = PrescricaoForm(request.POST if request.method == 'POST' else None, instance=ficha, assinar=assinar)
        itens = ItensPrescricaoFormSet(request.POST if request.method == 'POST' else None, instance=ficha, prefix='itens', assinar=assinar)
        if request.method == 'POST':
            valido = form.is_valid()
            itens_validos = itens.is_valid()
            if acao not in ('rascunho', 'assinar'):
                form.add_error(None, 'Ação inválida.')
            elif valido and form.cleaned_data['versao'] != versao_atual:
                form.add_error(None, 'Este rascunho foi atualizado. Reabra a prescrição antes de salvar.')
            elif valido and itens_validos:
                preenchidos = [f for f in itens.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
                if assinar and not preenchidos and not form.cleaned_data['texto_livre'].strip():
                    form.add_error(None, 'Inclua medicamento e posologia ou preencha o texto livre.')
                else:
                    nova = ficha.pk is None
                    ficha = form.save(commit=False)
                    ficha.versao = versao_atual + 1
                    ficha.save()
                    instancias = itens.save(commit=False)
                    for removido in itens.deleted_objects:
                        removido.delete()
                    for item in instancias:
                        item.ficha = ficha
                        item.save()
                    # Ordem de apresentação estável, incluindo linhas já existentes.
                    ordem = 0
                    for item_form in preenchidos:
                        item = item_form.instance
                        item.ordem = ordem
                        item.save(update_fields=['ordem'])
                        ordem += 1
                    if assinar:
                        ficha.status = Prescricao.Status.ASSINADA
                        ficha.emitida_em = timezone.now()
                        ficha.save(update_fields=['status', 'emitida_em'])
                        gravar_assinatura_manuscrita(
                            tipo_documento='prescricao', documento_id=ficha.pk,
                            papel='dentista', nome_assinante=ficha.nome_profissional,
                            imagem_data_url=form.cleaned_data['assinatura_base64'],
                            conteudo_para_hash=texto_para_hash_prescricao(ficha),
                            paciente=paciente, usuario=request.user,
                            ip=request.META.get('REMOTE_ADDR'),
                            user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        )
                    _auditar(request, ficha, 'Prescrição assinada' if assinar else 'Rascunho salvo', nova=nova)
                    return redirect('core:ver_prescricao', pk=pk, ficha_pk=ficha.pk)
        return render(request, 'core/form_prescricao.html', {
            'titulo': 'Editar prescrição' if ficha_pk else 'Nova prescrição',
            'paciente': paciente, 'ficha': ficha, 'form': form, 'itens': itens,
        })


@never_cache
@require_GET
def ver_prescricao(request, pk, ficha_pk):
    paciente = _paciente_autorizado(request, pk)
    ficha = get_object_or_404(Prescricao, pk=ficha_pk, paciente=paciente)
    contexto = contexto_integridade(ficha)
    pode_emitir = usuario_pode_emitir_prescricao(request.user, paciente)
    if not pode_emitir:
        contexto['url_retificar'] = None
    return render(request, 'core/ver_prescricao.html', {
        **contexto, 'titulo': 'Prescrição', 'paciente': paciente, 'ficha': ficha,
        'itens': ficha.itens.all(), 'assinatura': assinaturas_documento(ficha).first(),
        'pode_editar': ficha.status == 'rascunho' and usuario_pode_emitir_prescricao(request.user, paciente, ficha),
        'pode_exportar': ficha.status == 'assinada' and contexto['integridade'].integra and all(r.integridade.integra for r in contexto['retificacoes']),
        'auditoria': LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(ficha), object_id=str(ficha.pk)).select_related('user').order_by('action_time'),
    })


@never_cache
@require_GET
def imprimir_prescricao(request, pk, ficha_pk, pdf=False):
    paciente = _paciente_autorizado(request, pk)
    ficha = get_object_or_404(Prescricao, pk=ficha_pk, paciente=paciente)
    contexto = contexto_integridade(ficha)
    ocorrencias = list(contexto['integridade'].ocorrencias)
    for retificacao in contexto['retificacoes']:
        ocorrencias.extend(retificacao.integridade.ocorrencias)
    if ficha.status != 'assinada' or ocorrencias:
        return render(request, 'core/integridade_indisponivel.html', {
            'ocorrencias': ocorrencias or ['A prescrição ainda é um rascunho.'],
        }, status=409)
    assinatura = assinaturas_documento(ficha).get(papel='dentista')
    if pdf:
        from .prescricao_pdf import gerar_pdf_prescricao
        conteudo = gerar_pdf_prescricao(ficha, assinatura, contexto['retificacoes'])
        resposta = HttpResponse(conteudo, content_type='application/pdf')
        resposta['Content-Disposition'] = f'attachment; filename="prescricao-{ficha.pk}.pdf"'
        return resposta
    return render(request, 'core/imprimir_prescricao.html', {
        **contexto, 'ficha': ficha, 'assinatura': assinatura, 'itens': ficha.itens.all(),
    })
