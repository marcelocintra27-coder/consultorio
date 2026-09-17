from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete, m2m_changed
from django.dispatch import receiver

from . import models as m
from .integridade_documentos import documento_bloqueado

PROTEGIDOS = (
    m.Evolucao, m.RegistroEvolucaoClinica, m.FichaCadastroAnamnese,
    m.FichaPlanoTratamento, m.FichaAutorizacaoCusto,
    m.ItemConsentimentoProcedimento, m.ResponsavelPlanoTratamento,
    m.ItemAutorizacaoCusto, m.AssinaturaEletronica, m.RetificacaoDocumento,
    m.Prescricao, m.ItemPrescricao,
)


@receiver(pre_delete)
def preservar_documentos(sender, instance, using, **kwargs):
    from locacao.models import Dentista
    if sender == Dentista:
        if any(documento_bloqueado(item) for item in m.ItemConsentimentoProcedimento.objects.using(using).filter(dentistas=instance)):
            raise ValidationError('Profissional vinculado a item de documento assinado.')
    if sender in PROTEGIDOS and documento_bloqueado(instance):
        raise ValidationError('Original, assinatura, retificação ou legado não pode ser excluído.')
    # O Collector do Django faz SET_NULL sem chamar save/update do modelo.
    # Impede a exclusão de referências que mutilaria documentos protegidos.
    for modelo in PROTEGIDOS:
        for campo in modelo._meta.fields:
            if campo.is_relation and campo.remote_field.model == sender:
                for vinculado in modelo.objects.using(using).filter(**{campo.attname: instance.pk}):
                    if documento_bloqueado(vinculado):
                        raise ValidationError('Registro referenciado por documento clínico preservado.')


@receiver(m2m_changed, sender=m.ItemConsentimentoProcedimento.dentistas.through)
def preservar_profissionais_itens(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ('pre_add', 'pre_remove', 'pre_clear'):
        return
    if reverse:
        itens = m.ItemConsentimentoProcedimento.objects.filter(dentistas=instance)
        if pk_set:
            itens = m.ItemConsentimentoProcedimento.objects.filter(pk__in=pk_set)
    else:
        itens = [instance]
    for item in itens:
        pai = m.FichaPlanoTratamento.objects.select_for_update().get(pk=item.ficha_id)
        if documento_bloqueado(pai):
            raise ValidationError('Profissionais de item assinado são imutáveis.')
