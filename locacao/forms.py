from datetime import date

from django import forms
from django.utils import timezone

from .models import Dentista, Despesa, DividaAvulsa, Sala, TurnoLocacao
from core.models import Consulta, ContaPagar


def _queryset_dentistas(*ids_extras):
    dentistas = Dentista.objects.titulares_ativas()
    extras = [pk for pk in ids_extras if pk]
    if extras:
        dentistas = Dentista.objects.filter(pk__in=extras) | dentistas
    return dentistas.distinct().order_by('nome_completo')


class DentistaForm(forms.ModelForm):
    class Meta:
        model = Dentista
        fields = [
            'nome_completo',
            'tipo',
            'sala',
            'valor_hora',
        ]
        widgets = {
            'valor_hora': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ocupadas = Dentista.objects.values_list('sala_id', flat=True)
        if self.instance.pk:
            ocupadas = Dentista.objects.exclude(
                pk=self.instance.pk,
            ).values_list('sala_id', flat=True)
        ocupadas = [pk for pk in ocupadas if pk]
        self.fields['tipo'].label = 'Como trabalha na clínica'
        self.fields['tipo'].help_text = (
            'Titular: tem sala própria. Locatária: aluga horários (turnos) '
            'na sala de outra dentista.'
        )
        self.fields['sala'].label = 'Sala própria'
        self.fields['valor_hora'].label = 'Valor da hora (opcional)'
        self.fields['valor_hora'].help_text = (
            'Só serve para sugerir o preço de procedimentos. Pode deixar 0.'
        )
        self.fields['sala'].required = False
        self.fields['sala'].queryset = Sala.objects.filter(
            ativa=True,
        ).exclude(pk__in=ocupadas)

    def clean(self):
        dados = super().clean()
        tipo = dados.get('tipo')
        if (
            tipo == Dentista.Tipo.LOCATARIA
            and self.instance.pk
            and self.instance.tipo == Dentista.Tipo.TITULAR
        ):
            self._recusar_titular_virar_locataria()
        if tipo == Dentista.Tipo.LOCATARIA:
            dados['sala'] = None
            self._errors.pop('sala', None)
        elif tipo == Dentista.Tipo.TITULAR and not dados.get('sala'):
            self.add_error('sala', 'A dentista titular precisa de uma sala própria.')
        if (
            tipo == Dentista.Tipo.TITULAR
            and self.instance.pk
            and self.instance.turnos.filter(ativo=True).exists()
        ):
            self.add_error(
                'tipo',
                'Desative os turnos antes de marcar a dentista como titular.',
            )
        return dados

    def _recusar_titular_virar_locataria(self):
        """Titular só vira locatária sem sala alugada e sem consulta futura.

        Sem esta trava, a sala ficaria sem dona, os turnos de quem aluga
        ficariam soltos e as consultas marcadas perderiam a sala.
        """
        dentista = self.instance
        if dentista.sala_id:
            alugueis = TurnoLocacao.objects.filter(
                sala_id=dentista.sala_id, ativo=True,
            ).select_related('dentista')
            nomes = sorted({turno.dentista.nome_completo for turno in alugueis})
            if nomes:
                self.add_error('tipo', (
                    f'A sala desta dentista está alugada para {", ".join(nomes)}. '
                    'Ela não pode virar locatária enquanto esses turnos estiverem ativos.'
                ))
        futuras = Consulta.objects.filter(
            dentista=dentista, data__gte=timezone.localdate(),
        ).exclude(status=Consulta.Status.CANCELADA).count()
        if futuras:
            self.add_error('tipo', (
                f'Esta dentista tem {futuras} consulta(s) marcada(s) a partir de hoje '
                'na sala própria. Remarque ou cancele antes de mudar para locatária.'
            ))


class TurnoLocacaoForm(forms.ModelForm):
    hora_inicio = forms.TimeField(
        label='hora início',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        input_formats=['%H:%M', '%H:%M:%S'],
    )
    hora_fim = forms.TimeField(
        label='hora fim',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        input_formats=['%H:%M', '%H:%M:%S'],
    )

    class Meta:
        model = TurnoLocacao
        fields = [
            'sala',
            'dia_semana',
            'hora_inicio',
            'hora_fim',
            'observacao',
        ]
        widgets = {
            'observacao': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        salas = Sala.objects.filter(ativa=True)
        if self.instance.pk and self.instance.sala_id:
            salas = salas | Sala.objects.filter(pk=self.instance.sala_id)
        self.fields['sala'].queryset = salas.distinct().order_by('nome')


class DespesaForm(forms.ModelForm):
    competencia = forms.CharField(
        label='competência',
        widget=forms.TextInput(attrs={'type': 'month'}),
    )

    class Meta:
        model = Despesa
        fields = [
            'descricao',
            'valor',
            'competencia',
            'tipo',
            'pago_por',
            'conta_pagar',
            'observacoes',
        ]
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        extras = []
        if self.instance.pk and self.instance.pago_por_id:
            extras.append(self.instance.pago_por_id)
        self.fields['pago_por'].queryset = _queryset_dentistas(*extras)
        contas = ContaPagar.objects.filter(
            situacao__in=[ContaPagar.Situacao.APROVADA, ContaPagar.Situacao.PAGA]
        ).order_by('vencimento')
        if self.instance.pk and self.instance.conta_pagar_id:
            contas = contas | ContaPagar.objects.filter(pk=self.instance.conta_pagar_id)
        self.fields['conta_pagar'].queryset = contas.distinct()
        if self.instance.pk and self.instance.competencia:
            self.initial['competencia'] = self.instance.competencia.strftime('%Y-%m')
        elif not self.instance.pk:
            hoje = timezone.localdate()
            self.initial.setdefault('competencia', f'{hoje.year:04d}-{hoje.month:02d}')

    def clean_competencia(self):
        bruto = (self.cleaned_data.get('competencia') or '').strip()
        try:
            ano, mes = bruto.split('-')
            return date(int(ano), int(mes), 1)
        except (TypeError, ValueError):
            raise forms.ValidationError('Informe um mês válido.')

    def clean(self):
        dados = super().clean()
        conta = dados.get('conta_pagar')
        valor = dados.get('valor')
        if conta and valor is not None and valor != conta.valor_original:
            self.add_error('conta_pagar', 'O valor deve coincidir com a conta a pagar vinculada.')
        return dados


class DividaAvulsaForm(forms.ModelForm):
    competencia = forms.CharField(
        label='competência',
        widget=forms.TextInput(attrs={'type': 'month'}),
    )

    class Meta:
        model = DividaAvulsa
        fields = [
            'descricao',
            'valor',
            'competencia',
            'de_dentista',
            'para_dentista',
            'observacoes',
        ]
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        extras = []
        if self.instance.pk:
            extras.extend([
                self.instance.de_dentista_id,
                self.instance.para_dentista_id,
            ])
        dentistas = _queryset_dentistas(*extras)
        self.fields['de_dentista'].queryset = dentistas
        self.fields['para_dentista'].queryset = dentistas
        if self.instance.pk and self.instance.competencia:
            self.initial['competencia'] = self.instance.competencia.strftime('%Y-%m')
        elif not self.instance.pk:
            hoje = timezone.localdate()
            self.initial.setdefault('competencia', f'{hoje.year:04d}-{hoje.month:02d}')

    def clean_competencia(self):
        bruto = (self.cleaned_data.get('competencia') or '').strip()
        try:
            ano, mes = bruto.split('-')
            return date(int(ano), int(mes), 1)
        except (TypeError, ValueError):
            raise forms.ValidationError('Informe um mês válido.')
