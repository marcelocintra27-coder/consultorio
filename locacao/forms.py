from django import forms

from .models import Dentista, Sala


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
