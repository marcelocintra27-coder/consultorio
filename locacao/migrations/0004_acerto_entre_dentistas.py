import django.db.models.deletion
from django.db import migrations, models


def preencher_pago_por(apps, schema_editor):
    Despesa = apps.get_model('locacao', 'Despesa')
    Dentista = apps.get_model('locacao', 'Dentista')
    primeiro = Dentista.objects.order_by('pk').first()
    for despesa in Despesa.objects.all():
        if despesa.tipo == 'geral':
            despesa.tipo = 'compartilhada'
        if despesa.dentista_id:
            despesa.pago_por_id = despesa.dentista_id
        elif primeiro:
            despesa.pago_por_id = primeiro.pk
        despesa.save()
    Despesa.objects.filter(pago_por__isnull=True).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('locacao', '0003_dentista_despesa_pagamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='despesa',
            name='pago_por',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='despesas_pagas',
                to='locacao.dentista',
                verbose_name='pago por',
            ),
        ),
        migrations.RunPython(preencher_pago_por, noop_reverse),
        migrations.RemoveField(
            model_name='despesa',
            name='dentista',
        ),
        migrations.AlterField(
            model_name='despesa',
            name='pago_por',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='despesas_pagas',
                to='locacao.dentista',
                verbose_name='pago por',
            ),
        ),
        migrations.AlterField(
            model_name='despesa',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('compartilhada', 'compartilhada'),
                    ('individual', 'individual'),
                ],
                default='compartilhada',
                max_length=20,
                verbose_name='tipo',
            ),
        ),
        migrations.DeleteModel(
            name='PagamentoMensal',
        ),
        migrations.CreateModel(
            name='DividaAvulsa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descricao', models.CharField(max_length=200, verbose_name='descrição')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='valor')),
                ('competencia', models.DateField(
                    help_text='Use o primeiro dia do mês (ex.: 01/09/2026 para setembro).',
                    verbose_name='competência',
                )),
                ('observacoes', models.TextField(blank=True, verbose_name='observações')),
                ('cadastrado_em', models.DateTimeField(auto_now_add=True, verbose_name='data de cadastro')),
                ('de_dentista', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='dividas_avulsas_devidas',
                    to='locacao.dentista',
                    verbose_name='de',
                )),
                ('para_dentista', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='dividas_avulsas_a_receber',
                    to='locacao.dentista',
                    verbose_name='para',
                )),
            ],
            options={
                'verbose_name': 'dívida avulsa',
                'verbose_name_plural': 'dívidas avulsas',
                'ordering': ['-competencia', 'descricao'],
            },
        ),
        migrations.CreateModel(
            name='PagamentoPar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('competencia', models.DateField(
                    help_text='Use o primeiro dia do mês (ex.: 01/09/2026 para setembro).',
                    verbose_name='competência',
                )),
                ('pago', models.BooleanField(default=False, verbose_name='pago')),
                ('cadastrado_em', models.DateTimeField(auto_now_add=True, verbose_name='data de cadastro')),
                ('de_dentista', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pagamentos_par_feitos',
                    to='locacao.dentista',
                    verbose_name='de',
                )),
                ('para_dentista', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pagamentos_par_recebidos',
                    to='locacao.dentista',
                    verbose_name='para',
                )),
            ],
            options={
                'verbose_name': 'pagamento entre dentistas',
                'verbose_name_plural': 'pagamentos entre dentistas',
                'ordering': ['-competencia', 'de_dentista'],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('de_dentista', 'para_dentista', 'competencia'),
                        name='pagamento_par_dentistas_competencia_unico',
                    ),
                ],
            },
        ),
    ]
