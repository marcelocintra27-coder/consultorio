from django.db import models


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
