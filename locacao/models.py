from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models


def primeiro_dia_mes(data):
    if data:
        return data.replace(day=1)
    return data


def arredondar_dinheiro(valor):
    return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Sala(models.Model):
    nome = models.CharField('nome', max_length=100)
    descricao = models.TextField('descrição', blank=True)
    ativa = models.BooleanField('ativa', default=True)

    class Meta:
        verbose_name = 'sala'
        verbose_name_plural = 'salas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Disponibilidade(models.Model):
    class Status(models.TextChoices):
        DISPONIVEL = 'disponivel', 'disponível'
        RESERVADA = 'reservada', 'reservada'
        CANCELADA = 'cancelada', 'cancelada'

    sala = models.ForeignKey(
        Sala,
        verbose_name='sala',
        on_delete=models.PROTECT,
        related_name='disponibilidades',
    )
    data = models.DateField('data')
    hora_inicio = models.TimeField('hora início')
    hora_fim = models.TimeField('hora fim')
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.DISPONIVEL,
    )

    class Meta:
        verbose_name = 'disponibilidade'
        verbose_name_plural = 'disponibilidades'
        ordering = ['data', 'hora_inicio']

    def __str__(self):
        return f'{self.sala} — {self.data} {self.hora_inicio}'


class Dentista(models.Model):
    nome_completo = models.CharField('nome completo', max_length=200)
    sala = models.OneToOneField(
        Sala,
        verbose_name='sala',
        on_delete=models.PROTECT,
        related_name='dentista',
    )
    ativo = models.BooleanField('ativo', default=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'dentista'
        verbose_name_plural = 'dentistas'
        ordering = ['nome_completo']

    def __str__(self):
        return self.nome_completo


class Despesa(models.Model):
    class Tipo(models.TextChoices):
        COMPARTILHADA = 'compartilhada', 'compartilhada'
        INDIVIDUAL = 'individual', 'individual'

    descricao = models.CharField('descrição', max_length=200)
    valor = models.DecimalField('valor', max_digits=10, decimal_places=2)
    competencia = models.DateField(
        'competência',
        help_text='Use o primeiro dia do mês (ex.: 01/09/2026 para setembro).',
    )
    tipo = models.CharField(
        'tipo',
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.COMPARTILHADA,
    )
    pago_por = models.ForeignKey(
        Dentista,
        verbose_name='pago por',
        on_delete=models.PROTECT,
        related_name='despesas_pagas',
    )
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'despesa'
        verbose_name_plural = 'despesas'
        ordering = ['-competencia', 'descricao']

    def __str__(self):
        return f'{self.descricao} ({self.get_tipo_display()})'

    def clean(self):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)

    def save(self, *args, **kwargs):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        if self.valor is not None:
            self.valor = arredondar_dinheiro(self.valor)
        super().save(*args, **kwargs)

    def valor_cota(self):
        if self.tipo != self.Tipo.COMPARTILHADA:
            return Decimal('0.00')
        ativas = Dentista.objects.filter(ativo=True).count()
        if ativas < 1:
            return Decimal('0.00')
        return arredondar_dinheiro(self.valor / ativas)

    valor_cota.short_description = 'cota'


class DividaAvulsa(models.Model):
    descricao = models.CharField('descrição', max_length=200)
    valor = models.DecimalField('valor', max_digits=10, decimal_places=2)
    competencia = models.DateField(
        'competência',
        help_text='Use o primeiro dia do mês (ex.: 01/09/2026 para setembro).',
    )
    de_dentista = models.ForeignKey(
        Dentista,
        verbose_name='de',
        on_delete=models.PROTECT,
        related_name='dividas_avulsas_devidas',
    )
    para_dentista = models.ForeignKey(
        Dentista,
        verbose_name='para',
        on_delete=models.PROTECT,
        related_name='dividas_avulsas_a_receber',
    )
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'dívida avulsa'
        verbose_name_plural = 'dívidas avulsas'
        ordering = ['-competencia', 'descricao']

    def __str__(self):
        return f'{self.de_dentista} → {self.para_dentista}: {self.descricao}'

    def clean(self):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        if (
            self.de_dentista_id
            and self.para_dentista_id
            and self.de_dentista_id == self.para_dentista_id
        ):
            raise ValidationError('A dívida avulsa deve ser entre dentistas diferentes.')
        if self.valor is not None:
            self.valor = arredondar_dinheiro(self.valor)

    def save(self, *args, **kwargs):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        if self.valor is not None:
            self.valor = arredondar_dinheiro(self.valor)
        super().save(*args, **kwargs)


class PagamentoPar(models.Model):
    de_dentista = models.ForeignKey(
        Dentista,
        verbose_name='de',
        on_delete=models.PROTECT,
        related_name='pagamentos_par_feitos',
    )
    para_dentista = models.ForeignKey(
        Dentista,
        verbose_name='para',
        on_delete=models.PROTECT,
        related_name='pagamentos_par_recebidos',
    )
    competencia = models.DateField(
        'competência',
        help_text='Use o primeiro dia do mês (ex.: 01/09/2026 para setembro).',
    )
    valor = models.DecimalField(
        'valor',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Valor líquido do acerto no momento em que foi marcado como pago.',
    )
    pago = models.BooleanField('pago', default=False)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'pagamento entre dentistas'
        verbose_name_plural = 'pagamentos entre dentistas'
        ordering = ['-competencia', 'de_dentista']
        constraints = [
            models.UniqueConstraint(
                fields=['de_dentista', 'para_dentista', 'competencia'],
                name='pagamento_par_dentistas_competencia_unico',
            ),
        ]

    def __str__(self):
        return f'{self.de_dentista} → {self.para_dentista} ({self.competencia:%m/%Y})'

    def clean(self):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        if (
            self.de_dentista_id
            and self.para_dentista_id
            and self.de_dentista_id == self.para_dentista_id
        ):
            raise ValidationError('O pagamento deve ser entre dentistas diferentes.')

    def save(self, *args, **kwargs):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        super().save(*args, **kwargs)
