from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locacao', '0010_dentista_locataria_turnos'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilusuario',
            name='deve_trocar_senha',
            field=models.BooleanField(
                default=False,
                verbose_name='Obrigar a trocar a senha no próximo acesso',
            ),
        ),
    ]
