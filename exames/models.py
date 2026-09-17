"""Registros aditivos; correções e estados são eventos, nunca sobrescritas."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class ImutavelQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Registro imutável. Utilize o fluxo de correção.')

    def delete(self):
        raise ValidationError('Exclusão definitiva não permitida.')

    def bulk_update(self, *args, **kwargs):
        raise ValidationError('Atualização em lote não permitida.')

    def bulk_create(self, *args, **kwargs):
        raise ValidationError('Utilize inclusão individual auditada.')


class Imutavel(models.Model):
    objects = ImutavelQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = 'objects'

    def save(self, *args, **kwargs):
        if not self._state.adding or (self.pk and type(self).objects.filter(pk=self.pk).exists()):
            raise ValidationError('Registro imutável.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Exclusão definitiva não permitida.')


class Exame(Imutavel):
    class Categoria(models.TextChoices):
        FOTO = 'foto', 'Fotografia clínica'
        RADIOGRAFIA = 'radiografia', 'Radiografia'
        EXAME = 'exame', 'Exame complementar'
        LAUDO = 'laudo', 'Laudo'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paciente = models.ForeignKey('core.Paciente', on_delete=models.PROTECT)
    consulta = models.ForeignKey('core.Consulta', on_delete=models.PROTECT, null=True, blank=True)
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    titulo = models.CharField(max_length=160)
    data_exame = models.DateField(null=True, blank=True)
    observacao = models.TextField(blank=True, max_length=4000)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    chave = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tamanho = models.PositiveIntegerField()
    tipo = models.CharField(max_length=40)
    sha256 = models.CharField(max_length=64)
    anterior = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='substituto')
    justificativa = models.CharField(max_length=1000, blank=True)

    class Meta(Imutavel.Meta):
        ordering = ['-criado_em']
        constraints = [models.CheckConstraint(condition=Q(tamanho__gt=0), name='exame_nao_vazio')]

    def clean(self):
        if self.consulta_id and self.consulta.paciente_id != self.paciente_id:
            raise ValidationError('Consulta deve pertencer ao paciente.')
        if self.anterior_id and (self.anterior.paciente_id != self.paciente_id or not self.justificativa.strip()):
            raise ValidationError('Correção exige mesmo paciente e justificativa.')

    @property
    def invalidado(self):
        return self.eventos.filter(acao__in=['invalidado', 'substituido']).exists()

    @property
    def seguranca(self):
        evento = self.eventos.filter(acao__in=['liberado', 'quarentena', 'rejeitado', 'integridade_falhou']).order_by('-pk').first()
        return evento.acao if evento else 'quarentena'

    @property
    def estado(self):
        return 'Invalidado / substituído' if self.invalidado else {
            'liberado': 'Disponível', 'quarentena': 'Quarentena — inspeção pendente',
            'rejeitado': 'Bloqueado pela inspeção', 'integridade_falhou': 'Integridade comprometida',
        }[self.seguranca]


class EventoExame(Imutavel):
    exame = models.ForeignKey(Exame, on_delete=models.PROTECT, related_name='eventos', null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    acao = models.CharField(max_length=40)
    resultado = models.CharField(max_length=80)
    justificativa = models.CharField(max_length=1000, blank=True)

    @property
    def descricao(self):
        return {'incluido': 'Arquivo incluído', 'liberado': 'Inspeção aprovada',
                'quarentena': 'Inspeção pendente', 'rejeitado': 'Arquivo bloqueado pela inspeção',
                'integridade_falhou': 'Falha de integridade', 'consulta': 'Detalhes consultados',
                'consulta_admin': 'Detalhes consultados na administração',
                'download_iniciado': 'Download autorizado e iniciado', 'download_negado': 'Download bloqueado',
                'invalidado': 'Registro invalidado', 'substituido': 'Registro substituído'}.get(self.acao, self.acao)

    class Meta(Imutavel.Meta):
        ordering = ['-pk']
        constraints = [models.UniqueConstraint(fields=['exame'], condition=Q(acao__in=['invalidado', 'substituido']), name='exame_invalidacao_unica')]
