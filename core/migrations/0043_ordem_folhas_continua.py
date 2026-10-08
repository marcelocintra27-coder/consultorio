from django.db import migrations


def renumerar_folhas_por_paciente(apps, schema_editor):
    """Cada paciente fica 1, 2, 3… pelo lote (data de envio) e, dentro dele, pela ordem."""
    DigitalizacaoFicha = apps.get_model('core', 'DigitalizacaoFicha')
    pacientes = (
        DigitalizacaoFicha.objects.exclude(paciente_id=None)
        .order_by()
        .values_list('paciente_id', flat=True)
        .distinct()
    )
    for paciente_id in pacientes:
        fichas = list(DigitalizacaoFicha.objects.filter(paciente_id=paciente_id))
        inicio_lote = {}
        primeiro_pk = {}
        for ficha in fichas:
            if not ficha.lote:
                continue
            quando = inicio_lote.get(ficha.lote)
            if quando is None or ficha.criado_em < quando:
                inicio_lote[ficha.lote] = ficha.criado_em
            pk = primeiro_pk.get(ficha.lote)
            if pk is None or ficha.pk < pk:
                primeiro_pk[ficha.lote] = ficha.pk

        def chave(ficha):
            if ficha.lote:
                return (
                    inicio_lote[ficha.lote],
                    primeiro_pk[ficha.lote],
                    ficha.ordem,
                    ficha.pk,
                )
            return (ficha.criado_em, ficha.pk, ficha.ordem, ficha.pk)

        for numero, ficha in enumerate(sorted(fichas, key=chave), start=1):
            if ficha.ordem != numero:
                DigitalizacaoFicha.objects.filter(pk=ficha.pk).update(ordem=numero)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_registroacesso_fora_do_horario'),
    ]

    operations = [
        migrations.RunPython(renumerar_folhas_por_paciente, migrations.RunPython.noop),
    ]
