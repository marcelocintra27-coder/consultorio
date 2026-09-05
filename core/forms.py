from django import forms
from .models import Convenio, Paciente


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
