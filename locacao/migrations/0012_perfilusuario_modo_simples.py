from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locacao', '0011_perfilusuario_deve_trocar_senha'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilusuario',
            name='modo_simples',
            field=models.BooleanField(
                default=False,
                verbose_name='Modo simples (letra e botões maiores)',
            ),
        ),
    ]
