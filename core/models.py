from django.db import models


class Convenio(models.Model):
    nome = models.CharField('nome', max_length=100, unique=True)
    ativo = models.BooleanField('ativo', default=True)

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
    observacoes = models.TextField('observações', blank=True)
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'consulta'
        verbose_name_plural = 'consultas'
        ordering = ['data', 'hora_inicio']

    def __str__(self):
        return f'{self.paciente.nome_completo} - {self.data} {self.hora_inicio}'
