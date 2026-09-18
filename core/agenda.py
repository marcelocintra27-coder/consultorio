from django.core.exceptions import ValidationError

from .models import Consulta


def validar_horario_consulta(dentista_id, data, hora_inicio, hora_fim, consulta_pk=None):
    """Uma única regra de intervalo para agendamento e remarcação."""
    if not all((data, hora_inicio, hora_fim)):
        return
    if hora_fim <= hora_inicio:
        raise ValidationError('A hora fim deve ser posterior à hora início.')
    if dentista_id is None:
        return  # Registros legados podem não possuir dentista.
    conflitos = Consulta.objects.filter(
        dentista_id=dentista_id, data=data,
        hora_inicio__lt=hora_fim, hora_fim__gt=hora_inicio,
    ).exclude(status=Consulta.Status.CANCELADA)
    if consulta_pk is not None:
        conflitos = conflitos.exclude(pk=consulta_pk)
    if conflitos.exists():
        raise ValidationError('O dentista já possui consulta neste horário.')
