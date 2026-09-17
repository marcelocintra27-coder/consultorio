"""Proteção ORM dos originais, assinaturas e respectivos itens.

Não altera conteúdo/serialização histórica. Escritas SQL externas ao Django
não passam por estas proteções e exigem controle operacional do banco.
"""
from django.core.exceptions import ValidationError
from django.db import models, transaction


class QuerySetClinico(models.QuerySet):
    def update(self, **kwargs):
        with transaction.atomic(using=self.db):
            for anterior in self.select_for_update():
                validar_alteracao(anterior, kwargs)
                if hasattr(anterior, 'ficha_id') and ('ficha' in kwargs or 'ficha_id' in kwargs):
                    from .integridade_documentos import documento_bloqueado
                    destino = kwargs.get('ficha_id', kwargs.get('ficha'))
                    destino = getattr(destino, 'pk', destino)
                    if not isinstance(destino, int):
                        raise ValidationError('Vínculo clínico deve ser explícito.')
                    pai = type(anterior.ficha).objects.select_for_update().get(pk=destino)
                    if documento_bloqueado(pai):
                        raise ValidationError('Não é permitido inserir itens em documento assinado.')
            return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        # As gravações clínicas precisam dos mesmos controles de save/signals.
        raise ValidationError('Use o fluxo clínico individual para criar registros.')

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError('Atualização clínica em lote não é permitida.')


class ModeloClinicoProtegido(models.Model):
    objects = QuerySetClinico.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        from .integridade_documentos import documento_bloqueado
        with transaction.atomic(using=kwargs.get('using') or self._state.db or 'default'):
            anterior = None
            if self.pk:
                anterior = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if anterior:
                campos = kwargs.get('update_fields')
                valores = {
                    f.attname: getattr(self, f.attname)
                    for f in self._meta.concrete_fields
                    if not campos or f.name in campos or f.attname in campos
                }
                validar_alteracao(anterior, valores)
                if documento_bloqueado(anterior) and all(getattr(anterior, campo) == valor for campo, valor in valores.items()):
                    # Um save sem mudanças não deve atualizar auto_now no original.
                    return
            if hasattr(self, 'ficha_id') and self.ficha_id:
                pai = type(self.ficha).objects.select_for_update().get(pk=self.ficha_id)
                if documento_bloqueado(pai):
                    raise ValidationError('Os itens de um documento assinado são imutáveis.')
            return super().save(*args, **kwargs)


def validar_alteracao(anterior, valores):
    from .integridade_documentos import documento_bloqueado
    if not documento_bloqueado(anterior):
        return
    alterados = set()
    for chave, valor in valores.items():
        campo = anterior._meta.get_field(chave)
        if getattr(anterior, campo.attname) != valor:
            alterados.add(campo.name)
    # Metadados da segunda assinatura; nenhum deles faz parte do conteúdo
    # histórico. O fluxo web verifica integridade antes de concluir.
    if anterior._meta.model_name == 'fichacadastroanamnese' and anterior.status == 'aguardando_dentista':
        permitidos = {'atualizado_em'}
        if valores.get('status') == 'concluida':
            from .integridade_documentos import assinaturas_documento
            if assinaturas_documento(anterior).filter(papel='dentista').exists():
                permitidos.add('status')
        if not anterior.dentista_id:
            permitidos.add('dentista')
        alterados -= permitidos
    if alterados:
        raise ValidationError('Documento assinado ou legado é imutável. Utilize retificação.')
