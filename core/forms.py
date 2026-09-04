from django import forms
from .models import Paciente


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
