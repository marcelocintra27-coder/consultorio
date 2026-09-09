from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from locacao.models import primeiro_dia_mes


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


class AssinaturaEletronica(models.Model):
    class TipoDocumento(models.TextChoices):
        COMPONENTE_TESTE = 'componente_teste', 'componente de teste'
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


class FichaCadastroAnamnese(models.Model):
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


class RegistroEvolucaoClinica(models.Model):
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

    class Meta:
        verbose_name = 'registro de evolução clínica'
        verbose_name_plural = 'registros de evolução clínica'
        ordering = ['data', 'criado_em', 'pk']

    def __str__(self):
        return f'{self.paciente.nome_completo} — {self.data}'


class FichaPlanoTratamento(models.Model):
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


class ItemConsentimentoProcedimento(models.Model):
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


class ResponsavelPlanoTratamento(models.Model):
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


class FichaAutorizacaoCusto(models.Model):
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


class ItemAutorizacaoCusto(models.Model):
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


