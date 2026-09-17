from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Exame, EventoExame


@receiver(pre_delete, sender=Exame)
@receiver(pre_delete, sender=EventoExame)
def impedir_exclusao(sender, **kwargs):
    raise ValidationError('Arquivos clínicos e auditoria não podem ser excluídos.')
