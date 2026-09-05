from datetime import datetime
from decimal import Decimal

from django.db import models


class Convenio(models.Model):
    nome = models.CharField('nome', max_length=100, unique=True)
    ativo = models.BooleanField('ativo', default=True)
    valor_hora = models.DecimalField(
        'valor da hora',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    percentual_desconto = models.DecimalField(
        'percentual de desconto',
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    percentual_imposto = models.DecimalField(
        'percentual de imposto',
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    class Meta:
        verbose_name = 'convênio'
        verbose_name_plural = 'convênios'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Paciente(models.Model):
    nome_completo = models.CharField('nome completo', max_length=200)
    cpf = models.CharField('CPF', max_length=18, unique=True)
    data_nascimento = models.DateField('data de nascimento')
    telefone = models.CharField('telefone', max_length=20)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True)
    email = models.EmailField('e-mail', blank=True)
    endereco = models.TextField('endereço', blank=True)
    convenio = models.ForeignKey(
        Convenio,
        verbose_name='convênio',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pacientes',
    )
    carteirinha = models.CharField('número da carteirinha', max_length=40, blank=True)
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'paciente'
        verbose_name_plural = 'pacientes'
        ordering = ['nome_completo']

    def __str__(self):
        return self.nome_completo

class Evolucao(models.Model):
    paciente = models.ForeignKey(Paciente, verbose_name='paciente', on_delete=models.CASCADE, related_name='evolucoes')
    data = models.DateField('data do atendimento')
    descricao = models.TextField('descricao do procedimento')

    class Meta:
        verbose_name = 'evolucao'
        verbose_name_plural = 'evolucoes'
        ordering = ['data']

    def __str__(self):
        return f'{self.paciente.nome_completo} - {self.data}'


class Consulta(models.Model):
    class Status(models.TextChoices):
        AGENDADA = 'agendada', 'agendada'
        REALIZADA = 'realizada', 'realizada'
        FALTOU = 'faltou', 'faltou'
        CANCELADA = 'cancelada', 'cancelada'

    class FormaPagamento(models.TextChoices):
        DINHEIRO = 'dinheiro', 'dinheiro'
        CARTAO_CREDITO = 'cartao_credito', 'cartão de crédito'
        PIX = 'pix', 'pix'
        OUTROS = 'outros', 'outros'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.PROTECT,
        related_name='consultas',
    )
    data = models.DateField('data')
    hora_inicio = models.TimeField('hora início')
    hora_fim = models.TimeField('hora fim')
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.AGENDADA,
    )
    pago = models.BooleanField('pago', default=False)
    forma_pagamento = models.CharField(
        'forma de pagamento',
        max_length=20,
        choices=FormaPagamento.choices,
        blank=True,
        default='',
    )
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'consulta'
        verbose_name_plural = 'consultas'
        ordering = ['data', 'hora_inicio']

    def __str__(self):
        return f'{self.paciente.nome_completo} - {self.data} {self.hora_inicio}'

    @property
    def duracao_minutos(self):
        inicio = datetime.combine(self.data, self.hora_inicio)
        fim = datetime.combine(self.data, self.hora_fim)
        if fim <= inicio:
            return 0
        return int((fim - inicio).total_seconds() // 60)

    @property
    def valor_a_cobrar(self):
        convenio = self.paciente.convenio if self.paciente_id else None
        if not convenio:
            return Decimal('0.00')
        horas = Decimal(self.duracao_minutos) / Decimal(60)
        valor_bruto = horas * convenio.valor_hora
        valor_com_desconto = valor_bruto * (
            Decimal('1') - convenio.percentual_desconto / Decimal(100)
        )
        return (
            valor_com_desconto
            * (Decimal('1') + convenio.percentual_imposto / Decimal(100))
        ).quantize(Decimal('0.01'))
