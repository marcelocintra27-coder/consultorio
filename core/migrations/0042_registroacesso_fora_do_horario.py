from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_tipos_folha_e_troca_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='registroacesso',
            name='fora_do_horario',
            field=models.BooleanField(default=False, verbose_name='fora do horário'),
        ),
    ]
