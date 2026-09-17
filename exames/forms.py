from django import forms
from core.models import Consulta
from core.permissoes import usuario_e_administrador, dentista_do_usuario
from .models import Exame


class ExameForm(forms.ModelForm):
    arquivo = forms.FileField(label='Arquivo JPEG, PNG ou PDF', widget=forms.ClearableFileInput(attrs={'accept': '.jpg,.jpeg,.png,.pdf'}))

    class Meta:
        model = Exame
        fields = ['categoria', 'titulo', 'data_exame', 'consulta', 'observacao', 'justificativa']
        labels = {'titulo': 'Título', 'data_exame': 'Data do exame (se conhecida)', 'observacao': 'Observação', 'justificativa': 'Justificativa da correção'}
        widgets = {'data_exame': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'observacao': forms.Textarea(attrs={'rows': 3}), 'justificativa': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, paciente, user, anterior=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.paciente = paciente
        consultas = Consulta.objects.filter(paciente=paciente)
        if not usuario_e_administrador(user):
            consultas = consultas.filter(dentista=dentista_do_usuario(user))
        self.fields['consulta'].queryset = consultas
        self.fields['consulta'].empty_label = 'Sem vínculo com consulta'
        self.fields['categoria'].choices = [('', 'Selecione a categoria'), *Exame.Categoria.choices]
        if anterior:
            self.fields['justificativa'].required = True
        else:
            del self.fields['justificativa']


class JustificativaForm(forms.Form):
    justificativa = forms.CharField(max_length=1000, strip=True, widget=forms.Textarea(attrs={'rows': 3}))
