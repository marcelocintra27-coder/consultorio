from datetime import date

from django import forms
from django.utils import timezone

from .models import Dentista, Despesa, Sala


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
        dentistas = Dentista.objects.filter(ativo=True)
        if self.instance.pk and self.instance.pago_por_id:
            dentistas = Dentista.objects.filter(
                pk=self.instance.pago_por_id,
            ) | dentistas
        self.fields['pago_por'].queryset = dentistas.distinct().order_by('nome_completo')
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
