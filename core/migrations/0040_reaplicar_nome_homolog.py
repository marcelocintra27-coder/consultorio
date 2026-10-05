# Reaplica a grafia do nome para quem já rodou a 0039 com o prefixo
# HOMOLOG- virando "Homolog-". Não apaga ficha nem paciente.

from django.db import migrations


def reaplicar_nomes(apps, schema_editor):
    from core.busca_paciente import formatar_nome, normalizar_nome

    Paciente = apps.get_model('core', 'Paciente')
    for paciente in Paciente.objects.all().iterator():
        nome = formatar_nome(paciente.nome_completo)
        busca = normalizar_nome(nome)
        if paciente.nome_completo == nome and paciente.nome_busca == busca:
            continue
        Paciente.objects.filter(pk=paciente.pk).update(
            nome_completo=nome,
            nome_busca=busca,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_nome_paciente_arrumado'),
    ]

    operations = [
        migrations.RunPython(reaplicar_nomes, migrations.RunPython.noop),
    ]
