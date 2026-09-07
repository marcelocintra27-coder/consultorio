from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import Sum


class ConvenioQuerySet(models.QuerySet):
    def catalogo_dentista(self):
        return self.filter(ativo=True, usa_tabela_oficial=False).order_by('nome')


class Convenio(models.Model):
    nome = models.CharField('nome', max_length=100, unique=True)
    ativo = models.BooleanField('ativo', default=True)
    usa_tabela_oficial = models.BooleanField(
        'usa tabela oficial da cooperativa',
        default=False,
        help_text='Uniodonto: preços vêm da tabela compartilhada, não do catálogo da dentista.',
    )
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

    objects = ConvenioQuerySet.as_manager()

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
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='consultas',
        null=True,
        blank=True,
    )
    eh_legado = models.BooleanField('registro legado', default=False)
    valor_historico = models.DecimalField(
        'valor histórico congelado',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    dentista_complementado_em = models.DateTimeField(
        'dentista complementado em',
        null=True,
        blank=True,
    )
    dentista_complementado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='dentista complementado por',
        on_delete=models.PROTECT,
        related_name='consultas_dentista_complementadas',
        null=True,
        blank=True,
    )
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
    def valor_convenio(self):
        if self.eh_legado and self.valor_historico is not None:
            return Decimal(self.valor_historico).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        return Decimal('0.00')

    @property
    def valor_lancamentos(self):
        total = self.lancamentos.aggregate(soma=Sum('valor_final'))['soma']
        if total is None:
            return Decimal('0.00')
        return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def valor_materiais(self):
        total = self.materiais.aggregate(soma=Sum('valor'))['soma']
        if total is None:
            return Decimal('0.00')
        return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def valor_a_cobrar(self):
        return (
            self.valor_convenio + self.valor_lancamentos + self.valor_materiais
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class MaterialUsado(models.Model):
    consulta = models.ForeignKey(
        Consulta,
        verbose_name='consulta',
        on_delete=models.CASCADE,
        related_name='materiais',
    )
    descricao = models.CharField('descrição', max_length=200)
    valor = models.DecimalField('valor', max_digits=10, decimal_places=2)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'material usado'
        verbose_name_plural = 'materiais usados'
        ordering = ['descricao']

    def __str__(self):
        return f'{self.descricao} — {self.consulta}'

    def save(self, *args, **kwargs):
        if self.valor is not None:
            self.valor = Decimal(self.valor).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
        super().save(*args, **kwargs)


class Procedimento(models.Model):
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='procedimentos',
    )
    nome = models.CharField('nome', max_length=200)
    duracao_estimada_minutos = models.PositiveIntegerField(
        'duração estimada (minutos)',
        null=True,
        blank=True,
    )
    ativo = models.BooleanField('ativo', default=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'procedimento'
        verbose_name_plural = 'procedimentos'
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(
                fields=['dentista', 'nome'],
                name='procedimento_unico_por_dentista',
            ),
        ]

    def __str__(self):
        return f'{self.nome} — {self.dentista}'

    def preco_sugerido(self):
        if not self.duracao_estimada_minutos:
            return None
        dentista = self.dentista
        if not dentista.valor_hora:
            return None
        horas = Decimal(self.duracao_estimada_minutos) / Decimal(60)
        return (horas * dentista.valor_hora).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )


class PrecoProcedimento(models.Model):
    procedimento = models.ForeignKey(
        Procedimento,
        verbose_name='procedimento',
        on_delete=models.CASCADE,
        related_name='precos',
    )
    convenio = models.ForeignKey(
        Convenio,
        verbose_name='convênio',
        on_delete=models.PROTECT,
        related_name='precos_procedimento',
        null=True,
        blank=True,
        help_text='Vazio = tabela particular.',
    )
    valor = models.DecimalField('valor', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'preço de procedimento'
        verbose_name_plural = 'preços de procedimento'
        constraints = [
            models.UniqueConstraint(
                fields=['procedimento', 'convenio'],
                name='preco_unico_procedimento_tabela',
                nulls_distinct=False,
            ),
        ]

    def __str__(self):
        tabela = self.convenio.nome if self.convenio_id else 'particular'
        return f'{self.procedimento.nome} ({tabela})'

    def save(self, *args, **kwargs):
        if self.valor is not None:
            self.valor = Decimal(self.valor).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        super().save(*args, **kwargs)


class LancamentoAtendimento(models.Model):
    class Tipo(models.TextChoices):
        ATENDIMENTO = 'atendimento', 'atendimento'
        AJUSTE = 'ajuste', 'ajuste'

    consulta = models.ForeignKey(
        Consulta,
        verbose_name='consulta',
        on_delete=models.CASCADE,
        related_name='lancamentos',
    )
    procedimento = models.ForeignKey(
        Procedimento,
        verbose_name='procedimento do catálogo',
        on_delete=models.SET_NULL,
        related_name='lancamentos',
        null=True,
        blank=True,
    )
    nome_procedimento = models.CharField('procedimento', max_length=200)
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='lancamentos_atendimento',
    )
    convenio = models.ForeignKey(
        Convenio,
        verbose_name='tabela convênio',
        on_delete=models.PROTECT,
        related_name='lancamentos_atendimento',
        null=True,
        blank=True,
    )
    particular = models.BooleanField('tabela particular', default=True)
    valor_tabela = models.DecimalField(
        'valor de tabela', max_digits=10, decimal_places=2
    )
    percentual_desconto = models.DecimalField(
        'desconto aplicado (%)',
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    valor_final = models.DecimalField(
        'valor final', max_digits=10, decimal_places=2
    )
    tipo = models.CharField(
        'tipo',
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.ATENDIMENTO,
    )
    cadastrado_em = models.DateTimeField('data do lançamento', auto_now_add=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='lançado por',
        on_delete=models.PROTECT,
        related_name='lancamentos_atendimento',
    )

    class Meta:
        verbose_name = 'lançamento de atendimento'
        verbose_name_plural = 'lançamentos de atendimento'
        ordering = ['cadastrado_em']

    def __str__(self):
        return f'{self.nome_procedimento} — {self.valor_final}'

    def nome_tabela(self):
        if self.particular or not self.convenio_id:
            return 'particular'
        return self.convenio.nome

    def save(self, *args, **kwargs):
        for campo in ('valor_tabela', 'percentual_desconto', 'valor_final'):
            valor = getattr(self, campo)
            if valor is not None:
                setattr(
                    self,
                    campo,
                    Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                )
        super().save(*args, **kwargs)


class AuditoriaConsulta(models.Model):
    consulta = models.ForeignKey(
        Consulta,
        verbose_name='consulta',
        on_delete=models.CASCADE,
        related_name='auditorias',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='usuário',
        on_delete=models.PROTECT,
        related_name='auditorias_consulta',
    )
    descricao = models.CharField('descrição', max_length=300)
    cadastrado_em = models.DateTimeField('data e hora', auto_now_add=True)

    class Meta:
        verbose_name = 'auditoria de consulta'
        verbose_name_plural = 'auditorias de consulta'
        ordering = ['-cadastrado_em']

    def __str__(self):
        return f'{self.consulta_id} — {self.descricao}'


class ProcedimentoUniodonto(models.Model):
    class Categoria(models.TextChoices):
        NAO_CLASSIFICADA = 'nao_classificada', 'Não classificada'
        DENTISTICA = 'dentistica', 'Dentística'
        ENDODONTIA = 'endodontia', 'Endodontia'
        PERIODONTIA = 'periodontia', 'Periodontia'

    codigo = models.CharField('código TUSS', max_length=20, unique=True)
    nome = models.CharField('nome', max_length=300)
    categoria = models.CharField(
        'categoria',
        max_length=32,
        choices=Categoria.choices,
        default=Categoria.NAO_CLASSIFICADA,
    )
    valor_us = models.DecimalField('valor US', max_digits=12, decimal_places=2)
    valor_reais = models.DecimalField('valor R$', max_digits=10, decimal_places=2)
    fator_us = models.DecimalField(
        'fator US',
        max_digits=8,
        decimal_places=4,
        default=Decimal('0.1712'),
    )
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'procedimento Uniodonto'
        verbose_name_plural = 'procedimentos Uniodonto'
        ordering = ['categoria', 'nome']

    def __str__(self):
        return f'{self.codigo} — {self.nome}'

    def save(self, *args, **kwargs):
        if self.valor_us is not None:
            self.valor_us = Decimal(self.valor_us).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        if self.valor_reais is not None:
            self.valor_reais = Decimal(self.valor_reais).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        if self.fator_us is not None:
            self.fator_us = Decimal(self.fator_us).quantize(
                Decimal('0.0001'), rounding=ROUND_HALF_UP
            )
        super().save(*args, **kwargs)
