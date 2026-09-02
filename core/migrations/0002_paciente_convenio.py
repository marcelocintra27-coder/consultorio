# Generated manually for Convenio + fields on Paciente

from django.db import migrations, models
import django.db.models.deletion


def criar_convenios_iniciais(apps, schema_editor):
    Convenio = apps.get_model('core', 'Convenio')
    for nome in ('Uniodonto', 'Ipasgo'):
        Convenio.objects.get_or_create(nome=nome, defaults={'ativo': True})


def remover_convenios_iniciais(apps, schema_editor):
    Convenio = apps.get_model('core', 'Convenio')
    Convenio.objects.filter(nome__in=('Uniodonto', 'Ipasgo')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Convenio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True, verbose_name='nome')),
                ('ativo', models.BooleanField(default=True, verbose_name='ativo')),
            ],
            options={
                'verbose_name': 'convênio',
                'verbose_name_plural': 'convênios',
                'ordering': ['nome'],
            },
        ),
        migrations.AddField(
            model_name='paciente',
            name='carteirinha',
            field=models.CharField(blank=True, max_length=40, verbose_name='número da carteirinha'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='convenio',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='pacientes',
                to='core.convenio',
                verbose_name='convênio',
            ),
        ),
        migrations.RunPython(criar_convenios_iniciais, remover_convenios_iniciais),
    ]
