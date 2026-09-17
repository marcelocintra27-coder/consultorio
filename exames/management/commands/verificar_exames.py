"""Inventário operacional sem exposição de dados clínicos ou remoção de arquivos."""
import json
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from exames.models import Exame
from exames.storage import abrir_verificado, pasta_privada


class Command(BaseCommand):
    help = 'Verifica integridade, quarentena e arquivos órfãos, sem alterar dados.'

    def handle(self, **options):
        dados = {'registros': 0, 'integros': 0, 'falhas': [], 'quarentena': [], 'bloqueados': [], 'orfaos': [], 'temporarios': 0}
        chaves = set()
        for exame in Exame.objects.iterator():
            dados['registros'] += 1
            chaves.add(str(exame.chave) + '.bin')
            try:
                with abrir_verificado(exame):
                    dados['integros'] += 1
            except (ValidationError, OSError):
                dados['falhas'].append(str(exame.pk))
            if exame.seguranca == 'quarentena':
                dados['quarentena'].append(str(exame.pk))
            elif exame.seguranca != 'liberado':
                dados['bloqueados'].append(str(exame.pk))
        dados['orfaos'] = [p.name for p in pasta_privada('originais').iterdir() if p.is_file() and p.name not in chaves]
        dados['temporarios'] = sum(1 for p in pasta_privada('temporarios').iterdir() if p.is_file())
        self.stdout.write(json.dumps(dados, indent=2))
