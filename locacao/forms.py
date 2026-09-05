from datetime import date

from django import forms
from django.utils import timezone

from .models import Dentista, Despesa, DividaAvulsa, Sala


def _queryset_dentistas(*ids_extras):
    dentistas = Dentista.objects.filter(ativo=True)
    extras = [pk for pk in ids_extras if pk]
    if extras:
        dentistas = Dentista.objects.filter(pk__in=extras) | dentistas
    return dentistas.distinct().order_by('nome_completo')


class DentistaForm(forms.ModelForm):
    class Meta:
        model = Dentista
        fields = [
            'nome_completo',
            'sala',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ocupadas = Dentista.objects.values_list('sala_id', flat=True)
        if self.instance.pk:
            ocupadas = Dentista.objects.exclude(
                pk=self.instance.pk,
            ).values_list('sala_id', flat=True)
        self.fields['sala'].queryset = Sala.objects.filter(
            ativa=True,
        ).exclude(pk__in=ocupadas)


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
