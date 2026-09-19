from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from locacao.models import primeiro_dia_mes
from .protecao_clinica import ModeloClinicoProtegido


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
    cpf = models.CharField('CPF', max_length=18, unique=True, null=True, blank=True)
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
    instagram = models.CharField('Instagram', max_length=120, blank=True)
    facebook = models.CharField('Facebook', max_length=120, blank=True)
    outra_rede_social = models.CharField(
        'outra rede social',
        max_length=200,
        blank=True,
    )
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'paciente'
        verbose_name_plural = 'pacientes'
        ordering = ['nome_completo']

    def __str__(self):
        return self.nome_completo

class Evolucao(ModeloClinicoProtegido):
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
        CONFIRMADA = 'confirmada', 'confirmada'
        PRESENTE = 'presente', 'Paciente chegou'
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
    def valor_autorizacoes(self):
        total = ItemAutorizacaoCusto.objects.filter(
            ficha__consulta_id=self.pk,
            ficha__status=FichaAutorizacaoCusto.Status.CONCLUIDA,
        ).aggregate(soma=Sum('valor'))['soma']
        if total is None:
            return Decimal('0.00')
        return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def valor_a_cobrar(self):
        return (
            self.valor_convenio
            + self.valor_lancamentos
            + self.valor_materiais
            + self.valor_autorizacoes
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
                condition=Q(convenio__isnull=False),
                name='preco_unico_procedimento_convenio',
            ),
            models.UniqueConstraint(
                fields=['procedimento'],
                condition=Q(convenio__isnull=True),
                name='preco_unico_procedimento_particular',
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
    procedimento_uniodonto = models.ForeignKey(
        'ProcedimentoUniodonto',
        verbose_name='procedimento Uniodonto',
        on_delete=models.SET_NULL,
        related_name='lancamentos',
        null=True,
        blank=True,
    )
    nome_procedimento = models.CharField('procedimento', max_length=300)
    codigo_tuss = models.CharField('código TUSS', max_length=20, blank=True)
    valor_us = models.DecimalField(
        'valor US',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fator_us = models.DecimalField(
        'fator US',
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
    )
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

    def rotulo_procedimento(self):
        if self.codigo_tuss:
            return f'{self.codigo_tuss} — {self.nome_procedimento}'
        return self.nome_procedimento

    def save(self, *args, **kwargs):
        for campo in ('valor_tabela', 'percentual_desconto', 'valor_final'):
            valor = getattr(self, campo)
            if valor is not None:
                setattr(
                    self,
                    campo,
                    Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                )
        if self.valor_us is not None:
            self.valor_us = Decimal(self.valor_us).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        if self.fator_us is not None:
            self.fator_us = Decimal(self.fator_us).quantize(
                Decimal('0.0001'), rounding=ROUND_HALF_UP
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


def soma_producao_uniodonto(dentista, competencia):
    if dentista is None or competencia is None:
        return Decimal('0.00')
    competencia = primeiro_dia_mes(competencia)
    do_mes = LancamentoAtendimento.objects.filter(
        Q(dentista=dentista) | Q(consulta__dentista=dentista),
        consulta__data__year=competencia.year,
        consulta__data__month=competencia.month,
    )
    uniodonto = (
        do_mes.filter(procedimento_uniodonto__isnull=False)
        | do_mes.filter(codigo_tuss__gt='')
        | do_mes.filter(convenio__usa_tabela_oficial=True)
    ).distinct()
    total = uniodonto.aggregate(soma=Sum('valor_tabela'))['soma']
    if total is None:
        return Decimal('0.00')
    return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class RepasseUniodonto(models.Model):
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='repasses_uniodonto',
    )
    competencia = models.DateField(
        'competência',
        help_text='Primeiro dia do mês.',
    )
    producao_bruta = models.DecimalField(
        'produção bruta',
        max_digits=10,
        decimal_places=2,
    )
    glosa = models.DecimalField(
        'glosa',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    estorno = models.DecimalField(
        'estorno',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    inss_retido = models.DecimalField(
        'INSS retido',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    irrf_retido = models.DecimalField(
        'IRRF retido',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    liquido_recebido = models.DecimalField(
        'líquido recebido',
        max_digits=10,
        decimal_places=2,
    )
    liquido_calculado = models.DecimalField(
        'líquido calculado',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='cadastrado por',
        on_delete=models.PROTECT,
        related_name='repasses_uniodonto',
    )

    class Meta:
        verbose_name = 'repasse Uniodonto'
        verbose_name_plural = 'repasses Uniodonto'
        ordering = ['-competencia', 'dentista']
        constraints = [
            models.UniqueConstraint(
                fields=['dentista', 'competencia'],
                name='repasse_uniodonto_dentista_competencia_unico',
            ),
        ]

    def __str__(self):
        return f'{self.dentista} — {self.competencia:%m/%Y}'

    def calcular_liquido(self):
        return (
            self.producao_bruta
            - self.glosa
            - self.estorno
            - self.inss_retido
            - self.irrf_retido
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def diferenca(self):
        return (self.liquido_calculado - self.liquido_recebido).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def save(self, *args, **kwargs):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        for campo in (
            'producao_bruta',
            'glosa',
            'estorno',
            'inss_retido',
            'irrf_retido',
            'liquido_recebido',
        ):
            valor = getattr(self, campo)
            if valor is not None:
                setattr(
                    self,
                    campo,
                    Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                )
        self.liquido_calculado = self.calcular_liquido()
        super().save(*args, **kwargs)


class ContaReceber(models.Model):
    """Título financeiro administrativo de um paciente.

    Esta entidade não substitui o indicador legado ``Consulta.pago``. O valor
    de origem é a soma imutável das parcelas criadas junto ao título.
    """

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.PROTECT,
        related_name='contas_a_receber',
    )
    consulta = models.ForeignKey(
        Consulta,
        verbose_name='consulta de origem',
        on_delete=models.PROTECT,
        related_name='contas_a_receber',
        null=True,
        blank=True,
    )
    descricao = models.CharField('descrição', max_length=200)
    data_emissao = models.DateField('data de emissão', default=timezone.localdate)
    valor_original = models.DecimalField(
        'valor original', max_digits=12, decimal_places=2
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='criado por',
        on_delete=models.PROTECT,
        related_name='contas_a_receber_criadas',
    )

    class Meta:
        verbose_name = 'conta a receber'
        verbose_name_plural = 'contas a receber'
        ordering = ['data_emissao', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_original__gt=0),
                name='conta_receber_valor_original_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.paciente.nome_completo} — {self.descricao}'

    def clean(self):
        if (
            self.consulta_id
            and self.paciente_id
            and self.consulta.paciente_id != self.paciente_id
        ):
            raise ValidationError(
                {'consulta': 'A consulta deve pertencer ao paciente informado.'}
            )
        if self.valor_original is not None and self.valor_original <= 0:
            raise ValidationError(
                {'valor_original': 'Informe um valor original maior que zero.'}
            )

    @property
    def saldo(self):
        total = sum((parcela.saldo for parcela in self.parcelas.all()), Decimal('0.00'))
        return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def situacao(self):
        parcelas = list(self.parcelas.all())
        if not parcelas:
            return 'aberta'
        if all(parcela.saldo == Decimal('0.00') for parcela in parcelas):
            return 'liquidada'
        if any(parcela.saldo < parcela.valor_original for parcela in parcelas):
            return 'parcial'
        return 'aberta'


class ParcelaContaReceber(models.Model):
    conta = models.ForeignKey(
        ContaReceber,
        verbose_name='conta a receber',
        on_delete=models.PROTECT,
        related_name='parcelas',
    )
    numero = models.PositiveIntegerField('número da parcela')
    vencimento = models.DateField('vencimento')
    valor_original = models.DecimalField(
        'valor original', max_digits=12, decimal_places=2
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'parcela de conta a receber'
        verbose_name_plural = 'parcelas de contas a receber'
        ordering = ['vencimento', 'numero']
        constraints = [
            models.UniqueConstraint(
                fields=['conta', 'numero'],
                name='parcela_conta_receber_numero_unico',
            ),
            models.CheckConstraint(
                condition=Q(numero__gt=0),
                name='parcela_conta_receber_numero_positivo',
            ),
            models.CheckConstraint(
                condition=Q(valor_original__gt=0),
                name='parcela_conta_receber_valor_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.conta} — parcela {self.numero}'

    def clean(self):
        if self.valor_original is not None and self.valor_original <= 0:
            raise ValidationError(
                {'valor_original': 'Informe um valor de parcela maior que zero.'}
            )

    @property
    def total_recebido(self):
        total = self.recebimentos.filter(
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO
        ).aggregate(soma=Sum('valor'))['soma']
        return Decimal(total or '0.00').quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def total_descontos(self):
        total = self.recebimentos.filter(
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO
        ).aggregate(soma=Sum('desconto'))['soma']
        return Decimal(total or '0.00').quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def total_estornado(self):
        total = self.recebimentos.filter(
            tipo=RecebimentoPaciente.Tipo.ESTORNO
        ).aggregate(soma=Sum('valor'))['soma']
        return Decimal(total or '0.00').quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def saldo(self):
        return (
            Decimal(self.valor_original)
            - self.total_recebido
            - self.total_descontos
            + self.total_estornado
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def situacao(self):
        if self.saldo == Decimal('0.00'):
            return 'liquidada'
        if self.saldo < self.valor_original:
            return 'parcial'
        return 'aberta'


def gerar_numero_recibo():
    return f'RCB-{uuid4().hex.upper()}'


class FormaPagamentoConfiguravel(models.Model):
    """Cadastro administrativo para novos recebimentos.

    Não substitui nem converte o campo legado de texto em Consulta ou
    RecebimentoPaciente. A forma configurada é um vínculo adicional e
    auditável para operações novas.
    """

    class TipoTaxa(models.TextChoices):
        NENHUMA = 'nenhuma', 'sem taxa'
        PERCENTUAL = 'percentual', 'percentual'
        VALOR_FIXO = 'valor_fixo', 'valor fixo'

    nome = models.CharField('nome', max_length=100, unique=True)
    codigo = models.SlugField('código', max_length=30, unique=True)
    ativo = models.BooleanField('ativo', default=True)
    tipo_taxa = models.CharField(
        'tipo de taxa', max_length=15, choices=TipoTaxa.choices,
        default=TipoTaxa.NENHUMA,
    )
    valor_taxa = models.DecimalField(
        'valor da taxa', max_digits=8, decimal_places=2, default=0
    )
    prazo_recebimento_dias = models.PositiveIntegerField(
        'prazo de recebimento (dias)', null=True, blank=True
    )
    conta_destino = models.CharField('conta/destino', max_length=160, blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'forma de pagamento configurável'
        verbose_name_plural = 'formas de pagamento configuráveis'
        ordering = ['nome']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_taxa__gte=0),
                name='forma_pagamento_taxa_nao_negativa',
            ),
        ]

    def clean(self):
        erros = {}
        if self.tipo_taxa == self.TipoTaxa.NENHUMA and self.valor_taxa:
            erros['valor_taxa'] = 'Forma sem taxa deve ter valor de taxa igual a zero.'
        if self.tipo_taxa == self.TipoTaxa.PERCENTUAL and self.valor_taxa > 100:
            erros['valor_taxa'] = 'Taxa percentual não pode exceder 100%.'
        if erros:
            raise ValidationError(erros)

    @property
    def codigo_legado(self):
        codigos_legados = {item[0] for item in Consulta.FormaPagamento.choices}
        if self.codigo in codigos_legados:
            return self.codigo
        return Consulta.FormaPagamento.OUTROS

    def __str__(self):
        return self.nome


class AuditoriaFormaPagamento(models.Model):
    forma_pagamento = models.ForeignKey(
        FormaPagamentoConfiguravel, on_delete=models.PROTECT,
        related_name='auditorias',
    )
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    acao = models.CharField('ação', max_length=40)
    descricao = models.CharField('descrição', max_length=300)
    dados = models.JSONField('dados da operação', default=dict, blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'auditoria de forma de pagamento'
        verbose_name_plural = 'auditorias de formas de pagamento'
        ordering = ['-criado_em']


class RecebimentoPaciente(models.Model):
    class Tipo(models.TextChoices):
        RECEBIMENTO = 'recebimento', 'recebimento'
        ESTORNO = 'estorno', 'estorno'

    parcela = models.ForeignKey(
        ParcelaContaReceber,
        verbose_name='parcela',
        on_delete=models.PROTECT,
        related_name='recebimentos',
    )
    tipo = models.CharField('tipo', max_length=20, choices=Tipo.choices)
    valor = models.DecimalField('valor', max_digits=12, decimal_places=2)
    desconto = models.DecimalField(
        'desconto aplicado', max_digits=12, decimal_places=2, default=0
    )
    forma_pagamento = models.CharField(
        'forma de pagamento',
        max_length=20,
        choices=Consulta.FormaPagamento.choices,
        blank=True,
        default='',
    )
    forma_pagamento_configurada = models.ForeignKey(
        FormaPagamentoConfiguravel,
        verbose_name='forma de pagamento configurada',
        on_delete=models.PROTECT,
        related_name='recebimentos',
        null=True,
        blank=True,
    )
    observacoes = models.TextField('observações', blank=True)
    recebido_em = models.DateTimeField('recebido em', default=timezone.now)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='operador',
        on_delete=models.PROTECT,
        related_name='recebimentos_paciente_registrados',
    )
    recebimento_original = models.ForeignKey(
        'self',
        verbose_name='recebimento original',
        on_delete=models.PROTECT,
        related_name='estornos',
        null=True,
        blank=True,
    )
    numero_recibo = models.CharField(
        'número do recibo', max_length=40, unique=True, null=True, blank=True
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'recebimento de paciente'
        verbose_name_plural = 'recebimentos de pacientes'
        ordering = ['recebido_em', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name='recebimento_paciente_valor_positivo',
            ),
            models.CheckConstraint(
                condition=Q(desconto__gte=0),
                name='recebimento_paciente_desconto_nao_negativo',
            ),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.parcela}'

    def clean(self):
        erros = {}
        if self.valor is not None and self.valor <= 0:
            erros['valor'] = 'Informe um valor maior que zero.'
        if self.desconto is not None and self.desconto < 0:
            erros['desconto'] = 'O desconto não pode ser negativo.'
        if self.tipo == self.Tipo.RECEBIMENTO:
            if self.recebimento_original_id:
                erros['recebimento_original'] = (
                    'Um recebimento não pode apontar para outro recebimento.'
                )
            if not self.forma_pagamento:
                erros['forma_pagamento'] = 'Informe a forma de pagamento.'
            if (
                self.forma_pagamento_configurada_id
                and not self.forma_pagamento_configurada.ativo
                and not self.pk
            ):
                erros['forma_pagamento_configurada'] = (
                    'Forma de pagamento inativa não pode ser usada em novo recebimento.'
                )
        elif self.tipo == self.Tipo.ESTORNO:
            original = self.recebimento_original
            if original is None:
                erros['recebimento_original'] = (
                    'Todo estorno deve apontar para o recebimento original.'
                )
            else:
                if original.tipo != self.Tipo.RECEBIMENTO:
                    erros['recebimento_original'] = (
                        'O estorno deve apontar para um recebimento válido.'
                    )
                elif original.parcela_id != self.parcela_id:
                    erros['recebimento_original'] = (
                        'O recebimento original deve pertencer à mesma parcela.'
                    )
            if self.desconto:
                erros['desconto'] = 'Estorno não pode alterar desconto aplicado.'
            if self.forma_pagamento:
                erros['forma_pagamento'] = (
                    'Estorno não deve registrar nova forma de pagamento.'
                )
        else:
            erros['tipo'] = 'Tipo de operação inválido.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        if self.tipo == self.Tipo.RECEBIMENTO and not self.numero_recibo:
            self.numero_recibo = gerar_numero_recibo()
        if self.valor is not None:
            self.valor = Decimal(self.valor).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        if self.desconto is not None:
            self.desconto = Decimal(self.desconto).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        super().save(*args, **kwargs)


class AuditoriaFinanceira(models.Model):
    class Acao(models.TextChoices):
        CONTA_CRIADA = 'conta_criada', 'conta criada'
        RECEBIMENTO_REGISTRADO = 'recebimento_registrado', 'recebimento registrado'
        ESTORNO_REGISTRADO = 'estorno_registrado', 'estorno registrado'

    conta = models.ForeignKey(
        ContaReceber,
        verbose_name='conta a receber',
        on_delete=models.PROTECT,
        related_name='auditorias_financeiras',
    )
    parcela = models.ForeignKey(
        ParcelaContaReceber,
        verbose_name='parcela',
        on_delete=models.PROTECT,
        related_name='auditorias_financeiras',
        null=True,
        blank=True,
    )
    recebimento = models.ForeignKey(
        RecebimentoPaciente,
        verbose_name='recebimento',
        on_delete=models.PROTECT,
        related_name='auditorias_financeiras',
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='usuário',
        on_delete=models.PROTECT,
        related_name='auditorias_financeiras',
    )
    acao = models.CharField('ação', max_length=40, choices=Acao.choices)
    descricao = models.CharField('descrição', max_length=300)
    dados = models.JSONField('dados da operação', default=dict, blank=True)
    criado_em = models.DateTimeField('data e hora', auto_now_add=True)

    class Meta:
        verbose_name = 'auditoria financeira'
        verbose_name_plural = 'auditorias financeiras'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.get_acao_display()} — {self.conta_id}'


class Fornecedor(models.Model):
    nome = models.CharField('nome', max_length=160, unique=True)
    documento = models.CharField('CPF/CNPJ', max_length=20, blank=True)
    contato = models.CharField('contato', max_length=200, blank=True)
    ativo = models.BooleanField('ativo', default=True)
    cadastrado_em = models.DateTimeField('cadastrado em', auto_now_add=True)

    class Meta:
        verbose_name = 'fornecedor'
        verbose_name_plural = 'fornecedores'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class CategoriaContaPagar(models.Model):
    nome = models.CharField('nome', max_length=100, unique=True)
    ativa = models.BooleanField('ativa', default=True)
    cadastrada_em = models.DateTimeField('cadastrada em', auto_now_add=True)

    class Meta:
        verbose_name = 'categoria de conta a pagar'
        verbose_name_plural = 'categorias de contas a pagar'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ContaPagar(models.Model):
    class Recorrencia(models.TextChoices):
        UNICA = 'unica', 'única'
        MENSAL = 'mensal', 'mensal'
        ANUAL = 'anual', 'anual'

    class Situacao(models.TextChoices):
        PENDENTE_APROVACAO = 'pendente_aprovacao', 'pendente de aprovação'
        APROVADA = 'aprovada', 'aprovada'
        PAGA = 'paga', 'paga'

    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name='fornecedor',
        on_delete=models.PROTECT,
        related_name='contas_a_pagar',
    )
    categoria = models.ForeignKey(
        CategoriaContaPagar,
        verbose_name='categoria',
        on_delete=models.PROTECT,
        related_name='contas_a_pagar',
    )
    descricao = models.CharField('descrição', max_length=200)
    competencia = models.DateField('competência')
    vencimento = models.DateField('vencimento')
    valor_original = models.DecimalField('valor original', max_digits=12, decimal_places=2)
    recorrencia = models.CharField(
        'recorrência', max_length=20, choices=Recorrencia.choices,
        default=Recorrencia.UNICA,
    )
    situacao = models.CharField(
        'situação', max_length=30, choices=Situacao.choices,
        default=Situacao.PENDENTE_APROVACAO,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='responsável pelo lançamento',
        on_delete=models.PROTECT,
        related_name='contas_a_pagar_criadas',
    )
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='aprovado por',
        on_delete=models.PROTECT,
        related_name='contas_a_pagar_aprovadas',
        null=True,
        blank=True,
    )
    aprovado_em = models.DateTimeField('aprovado em', null=True, blank=True)
    observacoes = models.TextField('observações', blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'conta a pagar'
        verbose_name_plural = 'contas a pagar'
        ordering = ['vencimento', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_original__gt=0),
                name='conta_pagar_valor_original_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.fornecedor} — {self.descricao}'

    def clean(self):
        erros = {}
        if self.valor_original is not None and self.valor_original <= 0:
            erros['valor_original'] = 'Informe um valor original maior que zero.'
        if self.situacao in (self.Situacao.APROVADA, self.Situacao.PAGA):
            if not self.aprovado_por_id or not self.aprovado_em:
                erros['situacao'] = 'Conta aprovada deve registrar aprovador e data.'
        if erros:
            raise ValidationError(erros)

    @property
    def total_baixado(self):
        total = self.baixas.aggregate(soma=Sum('valor'))['soma']
        return Decimal(total or '0.00').quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def saldo(self):
        return (Decimal(self.valor_original) - self.total_baixado).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )


class BaixaContaPagar(models.Model):
    conta = models.ForeignKey(
        ContaPagar,
        verbose_name='conta a pagar',
        on_delete=models.PROTECT,
        related_name='baixas',
    )
    valor = models.DecimalField('valor baixado', max_digits=12, decimal_places=2)
    baixado_em = models.DateTimeField('baixado em', default=timezone.now)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='operador',
        on_delete=models.PROTECT,
        related_name='baixas_contas_pagar_registradas',
    )
    chave_operacao = models.UUIDField('chave da operação', unique=True, default=uuid4)
    observacoes = models.TextField('observações', blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'baixa de conta a pagar'
        verbose_name_plural = 'baixas de contas a pagar'
        ordering = ['baixado_em', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0), name='baixa_conta_pagar_valor_positivo'
            ),
        ]

    def __str__(self):
        return f'Baixa de {self.conta_id}: R$ {self.valor}'

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'Informe um valor maior que zero.'})


class AuditoriaContaPagar(models.Model):
    class Acao(models.TextChoices):
        CONTA_CRIADA = 'conta_criada', 'conta criada'
        CONTA_APROVADA = 'conta_aprovada', 'conta aprovada'
        BAIXA_REGISTRADA = 'baixa_registrada', 'baixa registrada'

    conta = models.ForeignKey(
        ContaPagar,
        verbose_name='conta a pagar',
        on_delete=models.PROTECT,
        related_name='auditorias',
    )
    baixa = models.ForeignKey(
        BaixaContaPagar,
        verbose_name='baixa',
        on_delete=models.PROTECT,
        related_name='auditorias',
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='usuário',
        on_delete=models.PROTECT,
        related_name='auditorias_contas_pagar',
    )
    acao = models.CharField('ação', max_length=40, choices=Acao.choices)
    descricao = models.CharField('descrição', max_length=300)
    dados = models.JSONField('dados da operação', default=dict, blank=True)
    criado_em = models.DateTimeField('data e hora', auto_now_add=True)

    class Meta:
        verbose_name = 'auditoria de conta a pagar'
        verbose_name_plural = 'auditorias de contas a pagar'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.get_acao_display()} — {self.conta_id}'


class CaixaDiario(models.Model):
    class Situacao(models.TextChoices):
        ABERTO = 'aberto', 'aberto'
        FECHADO = 'fechado', 'fechado'

    data = models.DateField(unique=True)
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.ABERTO)
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_contado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    justificativa_diferenca = models.TextField(blank=True)
    aberto_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='caixas_abertos')
    aberto_em = models.DateTimeField(auto_now_add=True)
    fechado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='caixas_fechados', null=True, blank=True)
    fechado_em = models.DateTimeField(null=True, blank=True)

    @property
    def saldo_esperado(self):
        entradas = self.movimentos.filter(tipo__in=['entrada_automatica', 'ajuste_entrada', 'compensacao_entrada']).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        saidas = self.movimentos.filter(tipo__in=['saida_automatica', 'ajuste_saida', 'compensacao_saida']).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        return (self.saldo_inicial + entradas - saidas).quantize(Decimal('0.01'))

    @property
    def diferenca(self):
        return None if self.saldo_contado is None else (self.saldo_contado - self.saldo_esperado).quantize(Decimal('0.01'))


class MovimentoCaixa(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA_AUTOMATICA = 'entrada_automatica', 'entrada automática'
        SAIDA_AUTOMATICA = 'saida_automatica', 'saída automática'
        AJUSTE_ENTRADA = 'ajuste_entrada', 'ajuste de entrada'
        AJUSTE_SAIDA = 'ajuste_saida', 'ajuste de saída'
        COMPENSACAO_ENTRADA = 'compensacao_entrada', 'compensação de entrada'
        COMPENSACAO_SAIDA = 'compensacao_saida', 'compensação de saída'
    caixa = models.ForeignKey(CaixaDiario, on_delete=models.PROTECT, related_name='movimentos')
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recebido = models.OneToOneField(RecebimentoPaciente, on_delete=models.PROTECT, null=True, blank=True, related_name='movimento_caixa')
    baixa = models.OneToOneField(BaixaContaPagar, on_delete=models.PROTECT, null=True, blank=True, related_name='movimento_caixa')
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(valor__gt=0), name='movimento_caixa_valor_positivo')]


class AuditoriaCaixa(models.Model):
    caixa=models.ForeignKey(CaixaDiario,on_delete=models.PROTECT,related_name='auditorias')
    movimento=models.ForeignKey(MovimentoCaixa,on_delete=models.PROTECT,null=True,blank=True)
    usuario=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    descricao=models.CharField(max_length=300)
    criado_em=models.DateTimeField(auto_now_add=True)


class ImportacaoExtrato(models.Model):
    """Metadados imutáveis da origem manual ou de um futuro arquivo de extrato.

    O conteúdo bruto não é persistido: CSV/OFX será normalizado antes de criar
    os lançamentos, evitando armazenar um segundo arquivo financeiro sensível.
    """

    class Formato(models.TextChoices):
        MANUAL = 'manual', 'manual'
        CSV = 'csv', 'CSV'
        OFX = 'ofx', 'OFX'

    class Situacao(models.TextChoices):
        IMPORTADA = 'importada', 'importada'
        CANCELADA = 'cancelada', 'cancelada logicamente'

    instituicao = models.CharField('instituição financeira', max_length=120)
    conta_referencia = models.CharField('conta de referência', max_length=80)
    formato = models.CharField(
        'formato de origem', max_length=10, choices=Formato.choices,
        default=Formato.MANUAL,
    )
    hash_arquivo = models.CharField(
        'hash do arquivo importado', max_length=64, unique=True,
        null=True, blank=True,
    )
    periodo_inicial = models.DateField('período inicial', null=True, blank=True)
    periodo_final = models.DateField('período final', null=True, blank=True)
    situacao = models.CharField(
        'situação', max_length=20, choices=Situacao.choices,
        default=Situacao.IMPORTADA,
    )
    motivo_cancelamento = models.TextField('motivo do cancelamento', blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='importacoes_extrato_criadas',
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='importacoes_extrato_canceladas', null=True, blank=True,
    )
    cancelado_em = models.DateTimeField('cancelado em', null=True, blank=True)

    class Meta:
        verbose_name = 'importação de extrato'
        verbose_name_plural = 'importações de extrato'
        ordering = ['-criado_em']

    def clean(self):
        erros = {}
        if self.formato != self.Formato.MANUAL and not self.hash_arquivo:
            erros['hash_arquivo'] = 'CSV e OFX exigem hash do arquivo.'
        if self.periodo_inicial and self.periodo_final and self.periodo_final < self.periodo_inicial:
            erros['periodo_final'] = 'O período final não pode ser anterior ao inicial.'
        if self.situacao == self.Situacao.CANCELADA and not self.motivo_cancelamento.strip():
            erros['motivo_cancelamento'] = 'Informe o motivo do cancelamento.'
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f'{self.instituicao} — {self.conta_referencia} ({self.get_formato_display()})'


class LancamentoExtrato(models.Model):
    class Natureza(models.TextChoices):
        ENTRADA = 'entrada', 'entrada'
        SAIDA = 'saida', 'saída'

    importacao = models.ForeignKey(
        ImportacaoExtrato, on_delete=models.PROTECT, related_name='lancamentos'
    )
    indice_origem = models.PositiveIntegerField('índice na origem')
    referencia_externa = models.CharField('referência externa', max_length=160, blank=True)
    data = models.DateField('data do lançamento')
    descricao = models.CharField('descrição', max_length=300)
    natureza = models.CharField('natureza', max_length=10, choices=Natureza.choices)
    valor = models.DecimalField('valor', max_digits=12, decimal_places=2)
    saldo_informado = models.DecimalField(
        'saldo informado', max_digits=12, decimal_places=2, null=True, blank=True
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'lançamento de extrato'
        verbose_name_plural = 'lançamentos de extrato'
        ordering = ['-data', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['importacao', 'indice_origem'],
                name='lancamento_extrato_indice_unico_por_importacao',
            ),
            models.CheckConstraint(
                condition=Q(valor__gt=0), name='lancamento_extrato_valor_positivo'
            ),
        ]

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'Informe um valor maior que zero.'})

    def __str__(self):
        return f'{self.data:%d/%m/%Y} — {self.descricao} — R$ {self.valor}'


class Conciliacao(models.Model):
    class Situacao(models.TextChoices):
        PENDENTE = 'pendente', 'pendente'
        CONCILIADA = 'conciliada', 'conciliada'
        PARCIAL = 'parcial', 'parcial'
        DIVERGENTE = 'divergente', 'divergente'
        CANCELADA = 'cancelada', 'cancelada logicamente'

    lancamento_extrato = models.OneToOneField(
        LancamentoExtrato, on_delete=models.PROTECT, related_name='conciliacao'
    )
    situacao = models.CharField(
        'situação', max_length=20, choices=Situacao.choices,
        default=Situacao.PENDENTE,
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='conciliacoes_criadas',
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='conciliacoes_confirmadas', null=True, blank=True,
    )
    confirmado_em = models.DateTimeField('confirmado em', null=True, blank=True)
    motivo_cancelamento = models.TextField('motivo do cancelamento', blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='conciliacoes_canceladas', null=True, blank=True,
    )
    cancelado_em = models.DateTimeField('cancelado em', null=True, blank=True)

    class Meta:
        verbose_name = 'conciliação'
        verbose_name_plural = 'conciliações'
        ordering = ['-criado_em']

    @property
    def valor_conciliado(self):
        total = self.itens.filter(ativo=True).aggregate(soma=Sum('valor_conciliado'))['soma']
        return Decimal(total or '0.00').quantize(Decimal('0.01'))

    def __str__(self):
        return f'Conciliação #{self.pk} — {self.get_situacao_display()}'


class ItemConciliacao(models.Model):
    conciliacao = models.ForeignKey(
        Conciliacao, on_delete=models.PROTECT, related_name='itens'
    )
    recebimento = models.ForeignKey(
        RecebimentoPaciente, on_delete=models.PROTECT, null=True, blank=True,
        related_name='itens_conciliacao',
    )
    baixa = models.ForeignKey(
        BaixaContaPagar, on_delete=models.PROTECT, null=True, blank=True,
        related_name='itens_conciliacao',
    )
    movimento_caixa = models.ForeignKey(
        MovimentoCaixa, on_delete=models.PROTECT, null=True, blank=True,
        related_name='itens_conciliacao',
    )
    repasse_uniodonto = models.ForeignKey(
        RepasseUniodonto, on_delete=models.PROTECT, null=True, blank=True,
        related_name='itens_conciliacao',
    )
    valor_origem = models.DecimalField('valor da origem', max_digits=12, decimal_places=2)
    valor_conciliado = models.DecimalField('valor conciliado', max_digits=12, decimal_places=2)
    ativo = models.BooleanField('ativo', default=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'item de conciliação'
        verbose_name_plural = 'itens de conciliação'
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_origem__gt=0),
                name='item_conciliacao_valor_origem_positivo',
            ),
            models.CheckConstraint(
                condition=Q(valor_conciliado__gt=0),
                name='item_conciliacao_valor_conciliado_positivo',
            ),
            models.CheckConstraint(
                condition=(
                    (Q(recebimento__isnull=False) & Q(baixa__isnull=True) & Q(movimento_caixa__isnull=True) & Q(repasse_uniodonto__isnull=True))
                    | (Q(recebimento__isnull=True) & Q(baixa__isnull=False) & Q(movimento_caixa__isnull=True) & Q(repasse_uniodonto__isnull=True))
                    | (Q(recebimento__isnull=True) & Q(baixa__isnull=True) & Q(movimento_caixa__isnull=False) & Q(repasse_uniodonto__isnull=True))
                    | (Q(recebimento__isnull=True) & Q(baixa__isnull=True) & Q(movimento_caixa__isnull=True) & Q(repasse_uniodonto__isnull=False))
                ),
                name='item_conciliacao_uma_origem',
            ),
        ]

    def clean(self):
        origens = [
            self.recebimento_id, self.baixa_id, self.movimento_caixa_id,
            self.repasse_uniodonto_id,
        ]
        if sum(origem is not None for origem in origens) != 1:
            raise ValidationError('Cada item deve ter exatamente uma origem financeira.')
        if self.valor_conciliado is not None and self.valor_origem is not None:
            if self.valor_conciliado > self.valor_origem:
                raise ValidationError({'valor_conciliado': 'Não pode exceder o valor da origem.'})


class AjusteConciliacao(models.Model):
    class Tipo(models.TextChoices):
        TAXA_CARTAO = 'taxa_cartao', 'taxa de cartão'
        TAXA_PIX = 'taxa_pix', 'taxa de Pix'
        OUTRA_TAXA = 'outra_taxa', 'outra taxa'
        DIVERGENCIA = 'divergencia', 'divergência'

    conciliacao = models.ForeignKey(
        Conciliacao, on_delete=models.PROTECT, related_name='ajustes'
    )
    tipo = models.CharField('tipo', max_length=20, choices=Tipo.choices)
    valor = models.DecimalField('valor', max_digits=12, decimal_places=2)
    motivo = models.TextField('motivo')
    ativo = models.BooleanField('ativo', default=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'ajuste de conciliação'
        verbose_name_plural = 'ajustes de conciliação'
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0), name='ajuste_conciliacao_valor_positivo'
            ),
        ]

    def clean(self):
        if not self.motivo or not self.motivo.strip():
            raise ValidationError({'motivo': 'Informe o motivo do ajuste.'})


class AuditoriaConciliacao(models.Model):
    conciliacao = models.ForeignKey(
        Conciliacao, on_delete=models.PROTECT, related_name='auditorias',
        null=True, blank=True,
    )
    importacao = models.ForeignKey(
        ImportacaoExtrato, on_delete=models.PROTECT, related_name='auditorias',
        null=True, blank=True,
    )
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    acao = models.CharField('ação', max_length=40)
    descricao = models.CharField('descrição', max_length=300)
    dados = models.JSONField('dados da operação', default=dict, blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'auditoria de conciliação'
        verbose_name_plural = 'auditorias de conciliação'
        ordering = ['-criado_em']
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(conciliacao__isnull=False) & Q(importacao__isnull=True))
                    | (Q(conciliacao__isnull=True) & Q(importacao__isnull=False))
                ),
                name='auditoria_conciliacao_um_alvo',
            ),
        ]

    def clean(self):
        if bool(self.conciliacao_id) == bool(self.importacao_id):
            raise ValidationError('A auditoria deve referenciar uma conciliação ou uma importação.')


class Prescricao(ModeloClinicoProtegido):
    class Status(models.TextChoices):
        RASCUNHO = 'rascunho', 'rascunho'
        ASSINADA = 'assinada', 'assinada'

    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='prescricoes')
    dentista = models.ForeignKey('locacao.Dentista', on_delete=models.PROTECT, related_name='prescricoes')
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prescricoes_criadas')
    nome_paciente = models.CharField('nome do paciente', max_length=200)
    cpf_paciente = models.CharField('CPF do paciente', max_length=18, blank=True)
    data_nascimento_paciente = models.DateField('nascimento do paciente', null=True, blank=True)
    nome_profissional = models.CharField('profissional responsável', max_length=200)
    cro = models.CharField('CRO / UF', max_length=30, blank=True)
    texto_livre = models.TextField('texto livre da prescrição', blank=True)
    orientacoes = models.TextField('orientações gerais', blank=True)
    status = models.CharField('situação', max_length=20, choices=Status, default=Status.RASCUNHO)
    versao = models.PositiveIntegerField('versão do rascunho', default=1)
    criado_em = models.DateTimeField('criada em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizada em', auto_now=True)
    emitida_em = models.DateTimeField('emitida em', null=True, blank=True)

    class Meta:
        verbose_name = 'prescrição'
        verbose_name_plural = 'prescrições'
        ordering = ['-criado_em', '-pk']

    def __str__(self):
        return f'Prescrição {self.pk} — {self.nome_paciente}'


class ItemPrescricao(ModeloClinicoProtegido):
    ficha = models.ForeignKey(Prescricao, on_delete=models.CASCADE, related_name='itens', verbose_name='prescrição')
    ordem = models.PositiveIntegerField('ordem', default=0)
    medicamento = models.CharField('medicamento', max_length=200, blank=True)
    concentracao_apresentacao = models.CharField('concentração / apresentação', max_length=200, blank=True)
    quantidade = models.CharField('quantidade', max_length=100, blank=True)
    posologia = models.TextField('posologia', blank=True)
    via = models.CharField('via', max_length=100, blank=True)
    duracao = models.CharField('duração', max_length=100, blank=True)
    orientacoes = models.TextField('orientações do medicamento', blank=True)

    class Meta:
        verbose_name = 'medicamento da prescrição'
        verbose_name_plural = 'medicamentos da prescrição'
        ordering = ['ordem', 'pk']


class RetificacaoDocumento(ModeloClinicoProtegido):
    evolucao = models.ForeignKey('RegistroEvolucaoClinica', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    anamnese = models.ForeignKey('FichaCadastroAnamnese', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    plano = models.ForeignKey('FichaPlanoTratamento', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    autorizacao = models.ForeignKey('FichaAutorizacaoCusto', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    prescricao = models.ForeignKey('Prescricao', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='retificacoes_documentos')
    nome_profissional = models.CharField('profissional', max_length=200)
    cro = models.CharField('CRO', max_length=30)
    criado_em = models.DateTimeField('registrada em', auto_now_add=True)
    justificativa = models.TextField('justificativa')
    conteudo = models.TextField('conteúdo da retificação')

    class Meta:
        verbose_name = 'retificação de documento'
        verbose_name_plural = 'retificações de documentos'
        ordering = ['criado_em', 'pk']
        constraints = [models.CheckConstraint(
            condition=(
                (Q(evolucao__isnull=False, anamnese__isnull=True, plano__isnull=True, autorizacao__isnull=True)
                | Q(evolucao__isnull=True, anamnese__isnull=False, plano__isnull=True, autorizacao__isnull=True)
                | Q(evolucao__isnull=True, anamnese__isnull=True, plano__isnull=False, autorizacao__isnull=True)
                | Q(evolucao__isnull=True, anamnese__isnull=True, plano__isnull=True, autorizacao__isnull=False)) & Q(prescricao__isnull=True)
                | Q(prescricao__isnull=False, evolucao__isnull=True, anamnese__isnull=True, plano__isnull=True, autorizacao__isnull=True)
            ), name='retificacao_exatamente_um_original',
        )]

    @property
    def original(self):
        return next(getattr(self, campo) for campo in ('evolucao', 'anamnese', 'plano', 'autorizacao', 'prescricao') if getattr(self, campo + '_id'))

    @property
    def original_tipo(self):
        from .integridade_documentos import tipo_documento
        return tipo_documento(self.original)

    @property
    def paciente(self):
        return self.original.paciente

    @property
    def paciente_id(self):
        return self.original.paciente_id

    def clean(self):
        if sum(bool(getattr(self, campo + '_id')) for campo in ('evolucao', 'anamnese', 'plano', 'autorizacao', 'prescricao')) != 1:
            raise ValidationError('Informe exatamente um documento original.')
        if not self.justificativa.strip() or not self.conteudo.strip():
            raise ValidationError('Justificativa e conteúdo são obrigatórios.')

    def __str__(self):
        return f'Retificação {self.pk} — {self.nome_profissional}'


class AssinaturaEletronica(ModeloClinicoProtegido):
    class TipoDocumento(models.TextChoices):
        COMPONENTE_TESTE = 'componente_teste', 'componente de teste'
        RETIFICACAO = 'retificacao', 'retificação de documento'
        PRESCRICAO = 'prescricao', 'prescrição'
        EVOLUCAO = 'evolucao', 'evolução'
        PLANO_TRATAMENTO = 'plano_tratamento', 'plano de tratamento / consentimento'
        PLANO_PROCEDIMENTO = 'plano_procedimento', 'consentimento por procedimento'
        PLANO_PROFISSIONAL = 'plano_profissional', 'assinatura profissional do plano'
        ANAMNESE = 'anamnese', 'cadastro / anamnese'
        AUTORIZACAO_CUSTO = 'autorizacao_custo', 'autorização de itens com custo'

    class Papel(models.TextChoices):
        PACIENTE = 'paciente', 'paciente'
        DENTISTA = 'dentista', 'dentista'
        RESPONSAVEL = 'responsavel', 'responsável'
        TESTEMUNHA = 'testemunha', 'testemunha'

    class TipoAssinatura(models.TextChoices):
        MANUSCRITA = 'manuscrita', 'manuscrita'
        ICP_BRASIL = 'icp_brasil', 'ICP-Brasil'

    class StatusVerificacao(models.TextChoices):
        NAO_APLICAVEL = 'nao_aplicavel', 'não aplicável'
        VALIDA = 'valida', 'válida'
        INVALIDA = 'invalida', 'inválida'
        EXPIRADA = 'expirada', 'expirada'

    tipo_documento = models.CharField(
        'tipo do documento',
        max_length=40,
        choices=TipoDocumento.choices,
    )
    documento_id = models.PositiveIntegerField('id do documento', default=0)
    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assinaturas',
    )
    papel = models.CharField('papel', max_length=20, choices=Papel.choices)
    tipo_assinatura = models.CharField(
        'tipo de assinatura',
        max_length=20,
        choices=TipoAssinatura.choices,
        default=TipoAssinatura.MANUSCRITA,
    )
    imagem = models.FileField(
        'imagem da assinatura',
        upload_to='assinaturas/%Y/%m/',
        blank=True,
    )
    nome_assinante = models.CharField('nome de quem assinou', max_length=200)
    cpf_assinante = models.CharField('CPF de quem assinou', max_length=18, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='usuário logado',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assinaturas_coletadas',
    )
    assinado_em = models.DateTimeField('assinado em', auto_now_add=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)
    user_agent = models.CharField('user agent', max_length=400, blank=True)
    hash_conteudo = models.CharField('hash do conteúdo', max_length=64, blank=True)
    hash_imagem = models.CharField('hash da imagem', max_length=64, blank=True)
    certificado_id = models.CharField('id do certificado', max_length=120, blank=True)
    certificado_serial = models.CharField(
        'serial do certificado', max_length=120, blank=True
    )
    certificado_emissor = models.CharField(
        'emissor do certificado', max_length=200, blank=True
    )
    validade_certificado_inicio = models.DateTimeField(
        'início da validade do certificado',
        null=True,
        blank=True,
    )
    validade_certificado_fim = models.DateTimeField(
        'fim da validade do certificado',
        null=True,
        blank=True,
    )
    politica = models.CharField('política (CAdES/PAdES)', max_length=40, blank=True)
    pacote_assinatura = models.BinaryField(
        'pacote CMS/PAdES',
        null=True,
        blank=True,
    )
    carimbo_tempo = models.DateTimeField('carimbo de tempo', null=True, blank=True)
    status_verificacao = models.CharField(
        'status da verificação',
        max_length=20,
        choices=StatusVerificacao.choices,
        default=StatusVerificacao.NAO_APLICAVEL,
    )

    class Meta:
        verbose_name = 'assinatura eletrônica'
        verbose_name_plural = 'assinaturas eletrônicas'
        ordering = ['-assinado_em']

    def __str__(self):
        return f'{self.get_papel_display()} — {self.nome_assinante}'


class FichaCadastroAnamnese(ModeloClinicoProtegido):
    class Status(models.TextChoices):
        RASCUNHO = 'rascunho', 'rascunho'
        AGUARDANDO_DENTISTA = 'aguardando_dentista', 'aguardando dentista'
        CONCLUIDA = 'concluida', 'concluída'

    class PreenchidaPor(models.TextChoices):
        PACIENTE = 'paciente', 'paciente'
        EQUIPE = 'equipe', 'equipe'

    class SimNao(models.TextChoices):
        SIM = 'sim', 'sim'
        NAO = 'nao', 'não'

    class SimNaoNaoSei(models.TextChoices):
        SIM = 'sim', 'sim'
        NAO = 'nao', 'não'
        NAO_SEI = 'nao_sei', 'não sei'

    class Gravidez(models.TextChoices):
        SIM = 'sim', 'sim'
        NAO = 'nao', 'não'
        NAO_SE_APLICA = 'nao_se_aplica', 'não se aplica'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.CASCADE,
        related_name='fichas_anamnese',
    )
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_anamnese',
    )
    status = models.CharField(
        'status',
        max_length=30,
        choices=Status.choices,
        default=Status.RASCUNHO,
    )
    preenchida_por = models.CharField(
        'preenchida por',
        max_length=20,
        choices=PreenchidaPor.choices,
        default=PreenchidaPor.EQUIPE,
    )
    token = models.UUIDField('token do link', default=uuid4, unique=True, editable=False)
    token_expira_em = models.DateTimeField('link expira em')
    nome_completo = models.CharField('nome completo', max_length=200)
    data_nascimento = models.DateField('data de nascimento')
    cpf = models.CharField('CPF', max_length=18)
    telefone = models.CharField('telefone', max_length=20)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True)
    email = models.EmailField('e-mail', blank=True)
    endereco = models.TextField('endereço', blank=True)
    cidade = models.CharField('cidade', max_length=120, blank=True)
    uf = models.CharField('UF', max_length=2, blank=True)
    profissao = models.CharField('profissão', max_length=120, blank=True)
    nome_responsavel = models.CharField(
        'responsável legal',
        max_length=200,
        blank=True,
    )
    saude_condicoes = models.JSONField('sua saúde', default=list, blank=True)
    saude_outra_texto = models.CharField(
        'outra condição de saúde',
        max_length=200,
        blank=True,
    )
    alergia = models.CharField(
        'alergia a medicamentos, alimentos ou látex',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    alergia_qual = models.CharField('qual alergia', max_length=200, blank=True)
    usa_medicamento = models.CharField(
        'usa medicamento',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    medicamento_nome = models.CharField(
        'nome do medicamento',
        max_length=200,
        blank=True,
    )
    cirurgia_recente = models.CharField(
        'cirurgia ou internação recente',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    cirurgia_qual = models.CharField(
        'qual cirurgia ou internação / quando',
        max_length=200,
        blank=True,
    )
    saude_bucal = models.JSONField('sua saúde bucal', default=list, blank=True)
    data_ultima_consulta = models.DateField(
        'data da última consulta odontológica',
        null=True,
        blank=True,
    )
    experiencia_anterior = models.CharField(
        'experiência odontológica anterior',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    experiencia_relato = models.TextField(
        'relato da experiência anterior',
        blank=True,
    )
    o_que_incomoda = models.TextField('o que mais incomoda', blank=True)
    o_que_espera = models.TextField('o que espera do tratamento', blank=True)
    fuma = models.CharField(
        'fuma / nicotina',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    bebida_alcoolica = models.CharField(
        'bebida alcoólica',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    range_dentes = models.CharField(
        'range ou aperta os dentes',
        max_length=20,
        choices=SimNaoNaoSei.choices,
        blank=True,
        default='',
    )
    gravidez = models.CharField(
        'grávida ou possibilidade de gravidez',
        max_length=20,
        choices=Gravidez.choices,
        blank=True,
        default='',
    )
    outra_info_saude = models.CharField(
        'outra informação de saúde relevante',
        max_length=20,
        choices=SimNao.choices,
        blank=True,
        default='',
    )
    outra_info_relato = models.TextField(
        'relato de outra informação de saúde',
        blank=True,
    )
    aceitou_declaracao = models.BooleanField(
        'aceitou a declaração',
        default=False,
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='criado por',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_anamnese_criadas',
    )

    class Meta:
        verbose_name = 'ficha de cadastro e anamnese'
        verbose_name_plural = 'fichas de cadastro e anamnese'
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['paciente'],
                condition=Q(
                    status__in=['rascunho', 'aguardando_dentista']
                ),
                name='uma_ficha_anamnese_aberta_por_paciente',
            ),
        ]

    def __str__(self):
        return f'{self.paciente.nome_completo} — {self.get_status_display()}'

    def save(self, *args, **kwargs):
        if not self.token_expira_em:
            self.token_expira_em = timezone.now() + timedelta(days=14)
        super().save(*args, **kwargs)

    @property
    def esta_aberta(self):
        return self.status in (self.Status.RASCUNHO, self.Status.AGUARDANDO_DENTISTA)

    @property
    def link_publico_ativo(self):
        return (
            self.status == self.Status.RASCUNHO
            and timezone.now() <= self.token_expira_em
        )


class DigitalizacaoFicha(models.Model):
    class Tipo(models.TextChoices):
        CADASTRO = 'cadastro', 'Cadastro'
        ANAMNESE = 'anamnese', 'Anamnese'
        EVOLUCAO = 'evolucao', 'Evolução'
        OUTRO = 'outro', 'Outro'

    class Status(models.TextChoices):
        PENDENTE_REVISAO = 'pendente_revisao', 'Pendente de revisão'
        CONFIRMADA = 'confirmada', 'Confirmada'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='digitalizacoes',
    )
    imagem = models.FileField(
        'imagem',
        upload_to='fichas_legado/%Y/%m/',
    )
    tipo = models.CharField(
        'tipo',
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.OUTRO,
    )
    texto_bruto_ia = models.JSONField(
        'texto bruto da IA',
        default=dict,
        blank=True,
    )
    status = models.CharField(
        'status',
        max_length=30,
        choices=Status.choices,
        default=Status.PENDENTE_REVISAO,
    )
    digitalizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='digitalizado por',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_digitalizadas',
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'digitalização de ficha'
        verbose_name_plural = 'digitalizações de ficha'
        ordering = ['-criado_em']

    def __str__(self):
        paciente = (
            self.paciente.nome_completo if self.paciente_id else 'sem paciente'
        )
        return f'{paciente} — {self.get_tipo_display()}'


class RegistroEvolucaoClinica(ModeloClinicoProtegido):
    class Origem(models.TextChoices):
        NATIVO = 'nativo', 'Nativo'
        LEGADO_FICHA_FISICA = 'legado_ficha_fisica', 'Legado - ficha física'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.CASCADE,
        related_name='registros_evolucao_clinica',
    )
    data = models.DateField('data')
    procedimento_etapa = models.CharField(
        'procedimento / etapa realizada',
        max_length=200,
    )
    descricao_clinica = models.TextField('descrição clínica / conduta')
    orientacoes = models.TextField('orientações fornecidas', blank=True)
    nome_profissional = models.CharField(
        'profissional',
        max_length=200,
    )
    cro = models.CharField('CRO', max_length=30)
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registros_evolucao_clinica',
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='criado por',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registros_evolucao_clinica_criados',
    )
    origem = models.CharField(
        'origem',
        max_length=30,
        choices=Origem.choices,
        default=Origem.NATIVO,
    )
    digitalizado_de = models.ForeignKey(
        DigitalizacaoFicha,
        verbose_name='digitalizado de',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evolucoes_geradas',
    )

    class Meta:
        verbose_name = 'registro de evolução clínica'
        verbose_name_plural = 'registros de evolução clínica'
        ordering = ['data', 'criado_em', 'pk']

    def __str__(self):
        return f'{self.paciente.nome_completo} — {self.data}'


class FichaPlanoTratamento(ModeloClinicoProtegido):
    class Status(models.TextChoices):
        RASCUNHO = 'rascunho', 'rascunho'
        CONCLUIDA = 'concluida', 'concluída'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.CASCADE,
        related_name='fichas_plano',
    )
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.RASCUNHO,
    )
    nome_completo = models.CharField('nome completo', max_length=200)
    data_nascimento = models.DateField('data de nascimento')
    cpf = models.CharField('CPF', max_length=18)
    telefone = models.CharField('telefone', max_length=20)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True)
    email = models.EmailField('e-mail', blank=True)
    endereco = models.TextField('endereço', blank=True)
    cidade = models.CharField('cidade', max_length=120, blank=True)
    uf = models.CharField('UF', max_length=2, blank=True)
    profissao = models.CharField('profissão', max_length=120, blank=True)
    nome_responsavel = models.CharField(
        'responsável legal',
        max_length=200,
        blank=True,
    )
    plano_tratamento = models.TextField('plano de tratamento', blank=True)
    ciencia_itens = models.JSONField(
        'itens de ciência informados',
        default=list,
        blank=True,
    )
    aceitou_declaracao = models.BooleanField(
        'aceitou a declaração',
        default=False,
    )
    local_assinatura = models.CharField('local', max_length=120, blank=True)
    data_consentimento = models.DateField(
        'data do consentimento',
        null=True,
        blank=True,
    )
    complexidade_itens = models.JSONField(
        'procedimentos de maior complexidade',
        default=list,
        blank=True,
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='criado por',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_plano_criadas',
    )

    class Meta:
        verbose_name = 'ficha de plano e consentimento'
        verbose_name_plural = 'fichas de plano e consentimento'
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['paciente'],
                condition=Q(status='rascunho'),
                name='uma_ficha_plano_rascunho_por_paciente',
            ),
        ]

    def __str__(self):
        return f'{self.paciente.nome_completo} — {self.get_status_display()}'


class ItemConsentimentoProcedimento(ModeloClinicoProtegido):
    ficha = models.ForeignKey(
        FichaPlanoTratamento,
        verbose_name='ficha',
        on_delete=models.CASCADE,
        related_name='itens',
    )
    ordem = models.PositiveIntegerField('ordem', default=0)
    procedimento = models.CharField('procedimento', max_length=200)
    descricao = models.TextField('descrição', blank=True)
    dentistas = models.ManyToManyField(
        'locacao.Dentista',
        verbose_name='dentistas responsáveis',
        blank=True,
        related_name='itens_consentimento_plano',
    )
    cro = models.CharField('CRO', max_length=80, blank=True)

    class Meta:
        verbose_name = 'item de consentimento de procedimento'
        verbose_name_plural = 'itens de consentimento de procedimento'
        ordering = ['ordem', 'pk']

    def __str__(self):
        return self.procedimento


class ResponsavelPlanoTratamento(ModeloClinicoProtegido):
    ficha = models.ForeignKey(
        FichaPlanoTratamento,
        verbose_name='ficha',
        on_delete=models.CASCADE,
        related_name='profissionais',
    )
    ordem = models.PositiveIntegerField('ordem', default=0)
    nome = models.CharField('profissional', max_length=200)
    cro = models.CharField('CRO', max_length=80)
    dentista = models.ForeignKey(
        'locacao.Dentista',
        verbose_name='dentista',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assinaturas_plano',
    )

    class Meta:
        verbose_name = 'profissional do plano'
        verbose_name_plural = 'profissionais do plano'
        ordering = ['ordem', 'pk']

    def __str__(self):
        return self.nome


class FichaAutorizacaoCusto(ModeloClinicoProtegido):
    class Status(models.TextChoices):
        RASCUNHO = 'rascunho', 'rascunho'
        CONCLUIDA = 'concluida', 'concluída'

    paciente = models.ForeignKey(
        Paciente,
        verbose_name='paciente',
        on_delete=models.CASCADE,
        related_name='fichas_autorizacao_custo',
    )
    consulta = models.ForeignKey(
        Consulta,
        verbose_name='consulta',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorizacoes_custo',
    )
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.RASCUNHO,
    )
    nome_completo = models.CharField('nome completo', max_length=200)
    data_nascimento = models.DateField('data de nascimento')
    cpf = models.CharField('CPF', max_length=18)
    nome_responsavel = models.CharField(
        'responsável legal',
        max_length=200,
        blank=True,
    )
    aceitou_declaracao = models.BooleanField(
        'aceitou a declaração',
        default=False,
    )
    arquivo = models.FileField(
        upload_to='autorizacoes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Arquivo anexado (Raio-X, exame, laudo etc.)',
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='solicitado por',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_autorizacao_custo_solicitadas',
    )

    class Meta:
        verbose_name = 'autorização de itens com custo'
        verbose_name_plural = 'autorizações de itens com custo'
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['paciente'],
                condition=Q(status='rascunho'),
                name='uma_autorizacao_custo_rascunho_por_paciente',
            ),
        ]

    def __str__(self):
        return f'{self.nome_completo} — {self.get_status_display()}'

    @property
    def valor_total(self):
        total = self.itens.aggregate(soma=Sum('valor'))['soma']
        if total is None:
            return Decimal('0.00')
        return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ItemAutorizacaoCusto(ModeloClinicoProtegido):
    class Tipo(models.TextChoices):
        RECEITUARIO_IMPRESSO = 'receituario_impresso', 'receituário impresso'
        RECEITUARIO_DIGITAL = 'receituario_digital', 'receituário digital/online'
        RADIOGRAFIA = 'radiografia', 'radiografia (filme ou digital)'
        FOTOGRAFIAS = 'fotografias', 'fotografias clínicas'
        TOMOGRAFIA = 'tomografia', 'tomografia'
        RESSONANCIA = 'ressonancia', 'ressonância magnética'
        OUTROS_EXAMES = 'outros_exames', 'outros exames'
        MATERIAIS = 'materiais', 'materiais utilizados'
        LABORATORIO = 'laboratorio', 'laboratório / prótese'
        OUTROS = 'outros', 'outros itens com custo'

    ficha = models.ForeignKey(
        FichaAutorizacaoCusto,
        verbose_name='autorização',
        on_delete=models.CASCADE,
        related_name='itens',
    )
    ordem = models.PositiveIntegerField('ordem', default=0)
    tipo = models.CharField('tipo', max_length=40, choices=Tipo.choices, blank=True)
    descricao = models.CharField('descrição / detalhe', max_length=200, blank=True)
    quantidade = models.PositiveIntegerField('quantidade', default=1)
    valor = models.DecimalField(
        'valor a cobrar',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'item autorizado com custo'
        verbose_name_plural = 'itens autorizados com custo'
        ordering = ['ordem', 'pk']

    def __str__(self):
        return self.get_tipo_display() or 'item'

    def save(self, *args, **kwargs):
        if self.valor is not None:
            self.valor = Decimal(self.valor).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
        super().save(*args, **kwargs)


