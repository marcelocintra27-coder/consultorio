import time
from django.core.management.base import BaseCommand, CommandError
from exames.storage import pasta_privada
from exames.models import EventoExame


class Command(BaseCommand):
    help = 'Lista temporários abandonados (>24h); --executar remove apenas esses temporários.'

    def add_arguments(self, parser):
        parser.add_argument('--executar', action='store_true')

    def handle(self, **options):
        pasta = pasta_privada('temporarios').resolve()
        quantidade = 0
        for arquivo in pasta.glob('recebimento-*'):
            if arquivo.is_symlink() or not arquivo.is_file() or arquivo.resolve().parent != pasta:
                continue
            if arquivo.stat().st_mtime >= time.time() - 86400:
                continue
            quantidade += 1
            if options['executar']:
                # Registra a tentativa antes da remoção; não acessa originais/quarentena.
                EventoExame.objects.create(acao='limpeza_temporario', resultado='iniciada')
                try:
                    arquivo.unlink()
                except OSError as exc:
                    raise CommandError('Não foi possível limpar um temporário.') from exc
                EventoExame.objects.create(acao='limpeza_temporario', resultado='concluida')
        self.stdout.write(f'Temporários antigos: {quantidade}; execução: {options["executar"]}.')
