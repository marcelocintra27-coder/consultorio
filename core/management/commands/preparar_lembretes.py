from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from core.whatsapp import ErroWhatsApp, preparar_lembretes


class Command(BaseCommand):
    help = 'Prepara lembretes de WhatsApp das consultas de amanhã, ou da data informada.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data',
            help='Dia das consultas, no formato AAAA-MM-DD. Sem este argumento, usa amanhã.',
        )

    def handle(self, *args, **options):
        bruto = (options.get('data') or '').strip()
        if bruto:
            try:
                data = datetime.strptime(bruto, '%Y-%m-%d').date()
            except ValueError as erro:
                raise CommandError('Informe a data como AAAA-MM-DD.') from erro
        else:
            data = None
        try:
            quantidade = preparar_lembretes(data)
        except ErroWhatsApp as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(self.style.SUCCESS(f'Lembretes preparados: {quantidade}.'))
