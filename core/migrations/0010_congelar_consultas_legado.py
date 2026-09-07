from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def congelar_consultas_legado(apps, schema_editor):
    Consulta = apps.get_model('core', 'Consulta')
    for consulta in Consulta.objects.select_related('paciente__convenio').all():
        convenio = consulta.paciente.convenio if consulta.paciente_id else None
        valor = Decimal('0.00')
        if convenio is not None:
            inicio = datetime.combine(consulta.data, consulta.hora_inicio)
            fim = datetime.combine(consulta.data, consulta.hora_fim)
            minutos = 0
            if fim > inicio:
                minutos = int((fim - inicio).total_seconds() // 60)
            horas = Decimal(minutos) / Decimal(60)
            valor_bruto = horas * convenio.valor_hora
            valor_com_desconto = valor_bruto * (
                Decimal('1') - convenio.percentual_desconto / Decimal(100)
            )
            valor = (
                valor_com_desconto
                * (Decimal('1') + convenio.percentual_imposto / Decimal(100))
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        consulta.eh_legado = True
        consulta.valor_historico = valor
        consulta.save(update_fields=['eh_legado', 'valor_historico'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_procedimentos_lancamentos_legado'),
    ]

    operations = [
        migrations.RunPython(congelar_consultas_legado, noop),
    ]
