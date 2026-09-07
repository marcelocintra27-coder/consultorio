from django import forms
from .models import (
    Convenio,
    Paciente,
    MaterialUsado,
    Consulta,
    Procedimento,
    LancamentoAtendimento,
)
from locacao.models import Dentista


class PacienteForm(forms.ModelForm):
    data_nascimento = forms.DateField(
        label='data de nascimento',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )

    class Meta:
        model = Paciente
        fields = [
            'nome_completo',
            'cpf',
            'data_nascimento',
            'telefone',
            'whatsapp',
            'email',
            'endereco',
            'convenio',
            'carteirinha',
            'observacoes',
        ]
        widgets = {
            'cpf': forms.TextInput(attrs={'autocomplete': 'off'}),
            'endereco': forms.Textarea(attrs={'rows': 2}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }


class ConvenioForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = [
            'nome',
            'valor_hora',
            'percentual_desconto',
            'percentual_imposto',
        ]
        widgets = {
            'valor_hora': forms.NumberInput(attrs={'step': '0.01'}),
            'percentual_desconto': forms.NumberInput(attrs={'step': '0.01'}),
            'percentual_imposto': forms.NumberInput(attrs={'step': '0.01'}),
        }


class MaterialUsadoForm(forms.ModelForm):
    class Meta:
        model = MaterialUsado
        fields = [
            'descricao',
            'valor',
        ]
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
        }


class ConsultaForm(forms.ModelForm):
    data = forms.DateField(
        label='data',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    hora_inicio = forms.TimeField(
        label='hora início',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
    )
    hora_fim = forms.TimeField(
        label='hora fim',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
    )
    dentista = forms.ModelChoiceField(
        label='dentista',
        queryset=Dentista.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )
    paciente = forms.ModelChoiceField(
        label='paciente',
        queryset=Paciente.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )

    class Meta:
        model = Consulta
        fields = [
            'paciente',
            'data',
            'hora_inicio',
            'hora_fim',
            'dentista',
            'observacoes',
        ]
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }


class StatusConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta
        fields = ['status']


class ProcedimentoForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        fields = ['nome', 'duracao_estimada_minutos', 'ativo']


class LancamentoForm(forms.Form):
    procedimento = forms.ModelChoiceField(
        label='procedimento',
        queryset=Procedimento.objects.none(),
    )
    convenio = forms.ModelChoiceField(
        label='tabela',
        queryset=Convenio.objects.catalogo_dentista(),
        required=False,
        empty_label='Particular',
    )
    valor_tabela = forms.DecimalField(
        label='valor de tabela',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    percentual_desconto = forms.DecimalField(
        label='desconto (%)',
        max_digits=5,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    valor_final = forms.DecimalField(
        label='valor final',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    tipo = forms.ChoiceField(
        label='tipo',
        choices=LancamentoAtendimento.Tipo.choices,
        initial=LancamentoAtendimento.Tipo.ATENDIMENTO,
    )

    def __init__(self, *args, dentista=None, **kwargs):
        super().__init__(*args, **kwargs)
        if dentista is not None:
            self.fields['procedimento'].queryset = Procedimento.objects.filter(
                dentista=dentista,
                ativo=True,
            ).order_by('nome')
        else:
            self.fields['procedimento'].queryset = Procedimento.objects.none()


class ComplementarDentistaForm(forms.Form):
    dentista = forms.ModelChoiceField(
        label='dentista',
        queryset=Dentista.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )

