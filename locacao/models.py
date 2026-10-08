from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


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


class DentistaQuerySet(models.QuerySet):
    def titulares_ativas(self):
        """Dentistas que entram no rateio e no acerto mensal.

        A locatária paga a sala direto à titular e fica fora da divisão
        das despesas da clínica.
        """
        return self.filter(ativo=True, tipo=Dentista.Tipo.TITULAR)


class Dentista(models.Model):
    class Tipo(models.TextChoices):
        TITULAR = 'titular', 'Titular'
        LOCATARIA = 'locataria', 'Locatária de turnos'

    nome_completo = models.CharField('nome completo', max_length=200)
    tipo = models.CharField(
        'tipo',
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.TITULAR,
    )
    sala = models.OneToOneField(
        Sala,
        verbose_name='sala',
        on_delete=models.PROTECT,
        related_name='dentista',
        null=True,
        blank=True,
        help_text='Sala própria da titular. A locatária deixa este campo vazio.',
    )
    ativo = models.BooleanField('ativo', default=True)
    valor_hora = models.DecimalField(
        'valor-hora',
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Usado só para sugerir preço de procedimento (valor-hora × duração estimada).',
    )
    cadastrado_em = models.DateTimeField('data de cadastro', auto_now_add=True)

    objects = DentistaQuerySet.as_manager()

    class Meta:
        verbose_name = 'dentista'
        verbose_name_plural = 'dentistas'
        ordering = ['nome_completo']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tipo='titular', sala__isnull=False)
                    | models.Q(tipo='locataria', sala__isnull=True)
                ),
                name='dentista_sala_conforme_tipo',
            ),
        ]

    def __str__(self):
        return self.nome_completo

    @property
    def eh_locataria(self):
        return self.tipo == self.Tipo.LOCATARIA

    @property
    def eh_titular(self):
        return self.tipo == self.Tipo.TITULAR

    def clean(self):
        super().clean()
        if self.tipo == self.Tipo.LOCATARIA:
            if self.sala_id:
                raise ValidationError({
                    'sala': 'A locatária não tem sala própria. A sala é definida nos turnos.',
                })
        elif not self.sala_id:
            raise ValidationError({
                'sala': 'A dentista titular precisa de uma sala própria.',
            })

    def resumo_turnos(self):
        """Texto dos turnos ativos, agrupados pela sala.

        Ex.: ``Sala Adriana — seg 08:00–12:00; qui 08:00–12:00``.
        """
        turnos = [turno for turno in self.turnos.all() if turno.ativo]
        turnos.sort(key=lambda turno: (turno.sala.nome, turno.dia_semana, turno.hora_inicio))
        grupos = []
        sala_atual = None
        partes = []
        for turno in turnos:
            nome = turno.sala.nome
            if sala_atual is None:
                sala_atual = nome
            elif nome != sala_atual:
                grupos.append(f'{sala_atual} — ' + '; '.join(partes))
                sala_atual = nome
                partes = []
            partes.append(turno.rotulo_curto())
        if sala_atual is not None:
            grupos.append(f'{sala_atual} — ' + '; '.join(partes))
        return '; '.join(grupos)


DIAS_CURTOS = {
    0: 'seg',
    1: 'ter',
    2: 'qua',
    3: 'qui',
    4: 'sex',
    5: 'sáb',
    6: 'dom',
}


def dia_semana_para_lookup(dia_semana):
    """Converte date.weekday() (segunda=0) no lookup week_day do Django (domingo=1)."""
    return (int(dia_semana) + 1) % 7 + 1


def consultas_futuras_que_ocupam_turno(turno):
    """Consultas futuras de outra dentista na sala do turno, no mesmo dia e horário.

    Na prática são as consultas da titular, porque só ela tem ``dentista.sala``.
    """
    from core.models import Consulta

    consultas = Consulta.objects.filter(
        dentista__sala_id=turno.sala_id,
        data__gte=timezone.localdate(),
        data__week_day=dia_semana_para_lookup(turno.dia_semana),
        hora_inicio__lt=turno.hora_fim,
        hora_fim__gt=turno.hora_inicio,
    ).exclude(status=Consulta.Status.CANCELADA)
    if turno.dentista_id:
        consultas = consultas.exclude(dentista_id=turno.dentista_id)
    return consultas.select_related('dentista', 'paciente').order_by(
        'data', 'hora_inicio', 'pk',
    )


def texto_turno_com_consultas(total, consultas):
    if total == 1:
        introducao = (
            'Não é possível salvar o turno: a sala já tem 1 consulta marcada nesse horário. '
            'Remarque-a antes: '
        )
    else:
        introducao = (
            f'Não é possível salvar o turno: a sala já tem {total} consultas marcadas nesse horário. '
            'Remarque-as antes: '
        )
    partes = [
        (
            f'{consulta.data:%d/%m} {consulta.hora_inicio:%H:%M} '
            f'{consulta.dentista.nome_completo} — {consulta.paciente.nome_completo}'
        )
        for consulta in consultas
    ]
    return introducao + '; '.join(partes)


class TurnoLocacao(models.Model):
    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, 'segunda-feira'
        TERCA = 1, 'terça-feira'
        QUARTA = 2, 'quarta-feira'
        QUINTA = 3, 'quinta-feira'
        SEXTA = 4, 'sexta-feira'
        SABADO = 5, 'sábado'
        DOMINGO = 6, 'domingo'

    dentista = models.ForeignKey(
        Dentista,
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='turnos',
    )
    sala = models.ForeignKey(
        Sala,
        verbose_name='sala',
        on_delete=models.PROTECT,
        related_name='turnos_locacao',
    )
    dia_semana = models.PositiveSmallIntegerField(
        'dia da semana',
        choices=DiaSemana.choices,
    )
    hora_inicio = models.TimeField('hora início')
    hora_fim = models.TimeField('hora fim')
    ativo = models.BooleanField('ativo', default=True)
    observacao = models.TextField('observação', blank=True)
    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='criado por',
        on_delete=models.SET_NULL,
        related_name='turnos_locacao_criados',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'turno de locação'
        verbose_name_plural = 'turnos de locação'
        ordering = ['dia_semana', 'hora_inicio']
        indexes = [
            models.Index(
                fields=['sala', 'dia_semana', 'ativo'],
                name='turno_sala_dia_ativo',
            ),
        ]

    def __str__(self):
        return f'{self.dentista} — {self.rotulo_curto()} ({self.sala})'

    def rotulo_curto(self):
        return (
            f'{DIAS_CURTOS.get(self.dia_semana, "?")} '
            f'{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}'
        )

    def clean(self):
        super().clean()
        erros = {}
        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            erros['hora_fim'] = 'A hora fim deve ser posterior à hora início.'
        if self.dentista_id and self.dentista.tipo != Dentista.Tipo.LOCATARIA:
            erros['dentista'] = 'Turnos só podem ser cadastrados para dentista locatária.'
        if erros:
            raise ValidationError(erros)
        if not (
            self.ativo
            and self.sala_id
            and self.dia_semana is not None
            and self.hora_inicio
            and self.hora_fim
        ):
            return
        sobrepostos = TurnoLocacao.objects.filter(
            ativo=True,
            dia_semana=self.dia_semana,
            hora_inicio__lt=self.hora_fim,
            hora_fim__gt=self.hora_inicio,
        )
        if self.pk:
            sobrepostos = sobrepostos.exclude(pk=self.pk)
        if sobrepostos.filter(sala_id=self.sala_id).exists():
            raise ValidationError(
                'Já existe um turno ativo sobreposto nesta sala neste dia da semana.'
            )
        if self.dentista_id and sobrepostos.filter(dentista_id=self.dentista_id).exists():
            raise ValidationError(
                'A locatária já tem um turno ativo neste horário.'
            )
        conflitos = consultas_futuras_que_ocupam_turno(self)
        total = conflitos.count()
        if total:
            raise ValidationError(texto_turno_com_consultas(total, conflitos[:10]))

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.sala_id:
                Sala.objects.select_for_update().get(pk=self.sala_id)
            if self.dentista_id:
                Dentista.objects.select_for_update().get(pk=self.dentista_id)
            self.full_clean()
            return super().save(*args, **kwargs)


class PerfilUsuario(models.Model):
    class Papel(models.TextChoices):
        DENTISTA = 'dentista', 'dentista'
        AUXILIAR = 'auxiliar', 'auxiliar'
        SECRETARIA = 'secretaria', 'secretária'

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='usuário',
        on_delete=models.CASCADE,
        related_name='perfil',
    )
    dentista = models.ForeignKey(
        Dentista,
        verbose_name='dentista',
        on_delete=models.PROTECT,
        related_name='perfis',
        null=True,
        blank=True,
    )
    papel = models.CharField(
        'papel',
        max_length=20,
        choices=Papel.choices,
        default=Papel.DENTISTA,
    )
    deve_trocar_senha = models.BooleanField(
        'Obrigar a trocar a senha no próximo acesso',
        default=False,
    )
    modo_simples = models.BooleanField(
        'Modo simples (letra e botões maiores)',
        default=False,
    )

    class Meta:
        verbose_name = 'perfil de usuário'
        verbose_name_plural = 'perfis de usuário'
        ordering = ['usuario__username']

    def __str__(self):
        if self.dentista_id:
            return f'{self.usuario} — {self.dentista} ({self.get_papel_display()})'
        return f'{self.usuario} — clínica ({self.get_papel_display()})'

    def clean(self):
        if self.papel == self.Papel.SECRETARIA:
            if self.dentista_id:
                raise ValidationError(
                    'A secretária não deve estar vinculada a um consultório.'
                )
        elif not self.dentista_id:
            raise ValidationError(
                'Dentista e auxiliar precisam estar vinculados a um consultório.'
            )


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
    conta_pagar = models.OneToOneField(
        'core.ContaPagar', verbose_name='conta a pagar vinculada',
        on_delete=models.PROTECT, null=True, blank=True,
        related_name='despesa_rateio',
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
        if self.conta_pagar_id and self.valor != self.conta_pagar.valor_original:
            raise ValidationError(
                {'conta_pagar': 'O valor da conta a pagar deve ser igual ao valor da despesa.'}
            )

    def save(self, *args, **kwargs):
        if self.competencia:
            self.competencia = primeiro_dia_mes(self.competencia)
        if self.valor is not None:
            self.valor = arredondar_dinheiro(self.valor)
        super().save(*args, **kwargs)

    def valor_cota(self):
        if self.tipo != self.Tipo.COMPARTILHADA:
            return Decimal('0.00')
        ativas = Dentista.objects.titulares_ativas().count()
        if ativas < 1:
            return Decimal('0.00')
        return arredondar_dinheiro(self.valor / ativas)

    valor_cota.short_description = 'cota'

    @property
    def data_efetiva_pagamento(self):
        if not self.conta_pagar_id:
            return None
        baixa = self.conta_pagar.baixas.order_by('-baixado_em').first()
        return baixa.baixado_em if baixa else None


class AuditoriaDespesa(models.Model):
    despesa = models.ForeignKey(Despesa, on_delete=models.PROTECT, related_name='auditorias')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=300)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']


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
