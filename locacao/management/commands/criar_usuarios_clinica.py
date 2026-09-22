from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from locacao.models import Dentista, PerfilUsuario

BANCOS_HOMOLOG = frozenset({
    'consultorio_homolog',
    'consultorio_homolog_externa',
})


def recusar_em_homologacao():
    """Recusa a carga real nos bancos e no ambiente de homologação.

    Produção com outro nome de banco segue o fluxo normal. Não usa
    EM_PRODUCAO=False como critério.
    """
    if getattr(settings, 'AMBIENTE', '') == 'homologacao':
        raise CommandError('Comando recusado no ambiente de homologação externa.')
    nome = Path(str(settings.DATABASES['default'].get('NAME') or '')).name
    if nome in BANCOS_HOMOLOG:
        raise CommandError('Comando recusado: banco de homologação.')
    engine = str(settings.DATABASES['default'].get('ENGINE') or '').lower()
    if 'postgres' not in engine:
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        atual = cursor.fetchone()[0]
    if atual in BANCOS_HOMOLOG:
        raise CommandError('Comando recusado: current_database() é de homologação.')

USUARIOS = (
    {
        'username': 'dra.adriana',
        'first_name': 'Dra Adriana',
        'last_name': 'Nasser',
        'papel': PerfilUsuario.Papel.DENTISTA,
        'dentista': 'Adriana Nasser',
    },
    {
        'username': 'dra.claudia',
        'first_name': 'Dra Cláudia',
        'last_name': 'Daher',
        'papel': PerfilUsuario.Papel.DENTISTA,
        'dentista': 'Claudia',
    },
    {
        'username': 'dra.simone',
        'first_name': 'Dra Simone',
        'last_name': 'Simões',
        'papel': PerfilUsuario.Papel.DENTISTA,
        'dentista': 'Simone',
    },
    {
        'username': 'elly',
        'first_name': 'Emilly',
        'last_name': '',
        'papel': PerfilUsuario.Papel.AUXILIAR,
        'dentista': 'Adriana Nasser',
    },
    {
        'username': 'bruna',
        'first_name': 'Bruna',
        'last_name': '',
        'papel': PerfilUsuario.Papel.AUXILIAR,
        'dentista': 'Simone',
    },
    {
        'username': 'amanda',
        'first_name': 'Amanda',
        'last_name': '',
        'papel': PerfilUsuario.Papel.SECRETARIA,
        'dentista': None,
    },
)


class Command(BaseCommand):
    help = (
        'Cria os logins da clínica (dentistas, auxiliares e secretária) '
        'e liga cada um ao PerfilUsuario. Use --senha para a senha inicial.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--senha',
            required=True,
            help='Senha inicial igual para todos os usuários criados nesta execução.',
        )

    def handle(self, *args, **options):
        recusar_em_homologacao()
        senha = options['senha']
        with transaction.atomic():
            for dados in USUARIOS:
                dentista = None
                if dados['dentista']:
                    dentista = Dentista.objects.filter(
                        nome_completo=dados['dentista'],
                    ).first()
                    if dentista is None:
                        raise CommandError(
                            f"Dentista não encontrado: {dados['dentista']}"
                        )

                usuario, criado = User.objects.get_or_create(
                    username=dados['username'],
                    defaults={
                        'first_name': dados['first_name'],
                        'last_name': dados['last_name'],
                        'is_staff': False,
                        'is_superuser': False,
                        'is_active': True,
                    },
                )
                if criado:
                    usuario.set_password(senha)
                    usuario.save()
                    self.stdout.write(f"Usuário criado: {usuario.username}")
                else:
                    usuario.first_name = dados['first_name']
                    usuario.last_name = dados['last_name']
                    usuario.is_active = True
                    usuario.save(update_fields=['first_name', 'last_name', 'is_active'])
                    self.stdout.write(f"Usuário já existia: {usuario.username}")

                perfil, _ = PerfilUsuario.objects.update_or_create(
                    usuario=usuario,
                    defaults={
                        'dentista': dentista,
                        'papel': dados['papel'],
                    },
                )
                perfil.full_clean()
                perfil.save()
                self.stdout.write(
                    f"  perfil: {perfil.get_papel_display()} — {perfil.dentista or 'clínica'}"
                )
