from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from locacao.models import Dentista, TurnoLocacao

from .models import Consulta


def com_sala_de_agenda(queryset):
    """Inclui a sala própria e os turnos ativos usados na exibição da agenda."""
    return queryset.select_related('dentista__sala').prefetch_related(
        Prefetch(
            'dentista__turnos',
            queryset=TurnoLocacao.objects.filter(ativo=True).select_related('sala'),
        )
    )


def _consulta_no_horario(dentista_id, data, hora_inicio, hora_fim, consulta_pk=None):
    conflitos = Consulta.objects.filter(
        dentista_id=dentista_id,
        data=data,
        hora_inicio__lt=hora_fim,
        hora_fim__gt=hora_inicio,
    ).exclude(status=Consulta.Status.CANCELADA)
    if consulta_pk is not None:
        conflitos = conflitos.exclude(pk=consulta_pk)
    return conflitos.exists()


def validar_horario_consulta(dentista_id, data, hora_inicio, hora_fim, consulta_pk=None):
    """Uma única regra de intervalo para agendamento e remarcação."""
    if not all((data, hora_inicio, hora_fim)):
        return
    if hora_fim <= hora_inicio:
        raise ValidationError('A hora fim deve ser posterior à hora início.')
    if dentista_id is None:
        return  # Registros legados podem não possuir dentista.
    if _consulta_no_horario(dentista_id, data, hora_inicio, hora_fim, consulta_pk):
        raise ValidationError('O dentista já possui consulta neste horário.')

    dentista = Dentista.objects.select_related('sala').get(pk=dentista_id)
    if dentista.tipo == Dentista.Tipo.LOCATARIA:
        turno = (
            TurnoLocacao.objects.filter(
                dentista=dentista,
                ativo=True,
                dia_semana=data.weekday(),
                hora_inicio__lte=hora_inicio,
                hora_fim__gte=hora_fim,
            )
            .select_related('sala')
            .order_by('hora_inicio')
            .first()
        )
        if turno is None:
            raise ValidationError(
                'Este horário está fora dos turnos ativos da locatária.'
            )
        titular = Dentista.objects.filter(
            sala=turno.sala,
            tipo=Dentista.Tipo.TITULAR,
        ).first()
        if titular is not None and _consulta_no_horario(
            titular.pk, data, hora_inicio, hora_fim, consulta_pk,
        ):
            raise ValidationError(
                'A titular da sala já tem consulta neste horário.'
            )
        return

    if not dentista.sala_id:
        return
    ocupacao = (
        TurnoLocacao.objects.filter(
            sala_id=dentista.sala_id,
            ativo=True,
            dia_semana=data.weekday(),
            hora_inicio__lt=hora_fim,
            hora_fim__gt=hora_inicio,
        )
        .select_related('dentista')
        .order_by('hora_inicio')
        .first()
    )
    if ocupacao is not None:
        raise ValidationError(
            f'Esse horário da sala está alugado para {ocupacao.dentista.nome_completo}.'
        )
