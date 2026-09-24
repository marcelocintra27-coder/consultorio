"""Carga fictícia só no PostgreSQL consultorio_homolog_externa.

Não chama a carga local e não cria os logins reais da clínica.
"""
import os
import tempfile
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from consultorio.settings import (
    _flag_ambiente,
    nome_banco_homolog_externa_valido,
    resolver_disco_homolog_externa,
)
from core.management.commands.carregar_homolog_local import gerar_senha_homolog
from core.models import (
    CategoriaContaPagar,
    ContaPagar,
    ContaReceber,
    Convenio,
    Fornecedor,
    Paciente,
    ParcelaContaReceber,
    PrecoProcedimento,
    Procedimento,
    Consulta,
)
from ia_seguranca.models import ConsentimentoIA
from locacao.models import Dentista, Despesa, PerfilUsuario, Sala

PREFIXO = 'HOMOLOG-'
ARQUIVO_SENHAS = 'SENHAS.txt'
USUARIOS_ESPERADOS = (
    'homolog.admin',
    'homolog.secretaria',
    'homolog.dentista.a',
    'homolog.dentista.b',
    'homolog.inativo',
    'homolog.auxiliar',
)


def _nome_banco_configurado():
    return Path(str(settings.DATABASES['default'].get('NAME') or '')).name


def _current_database():
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        return cursor.fetchone()[0]


def exigir_ambiente_homolog_externa():
    """Recusa antes de qualquer escrita. Devolve o disco privado validado."""
    if getattr(settings, 'EM_PRODUCAO', False):
        raise CommandError('Carga recusada: EM_PRODUCAO está ativo.')
    if getattr(settings, 'AMBIENTE', '') != 'homologacao':
        raise CommandError('Carga recusada: ambiente não é homologacao.')
    if _flag_ambiente(os.environ, 'HOMOLOG_LOCAL'):
        raise CommandError('Carga recusada: HOMOLOG_LOCAL está ativo.')
    engine = str(settings.DATABASES['default'].get('ENGINE') or '').lower()
    if 'postgres' not in engine:
        raise CommandError('Carga recusada: engine não é PostgreSQL.')
    if not nome_banco_homolog_externa_valido(_nome_banco_configurado()):
        raise CommandError(
            'Carga recusada: banco não é consultorio_homolog_externa.'
        )
    atual = _current_database()
    if atual != _nome_banco_configurado():
        raise CommandError(
            'Carga recusada: current_database() diferente do banco configurado.'
        )
    if not nome_banco_homolog_externa_valido(atual):
        raise CommandError(
            'Carga recusada: current_database() diferente de '
            'consultorio_homolog_externa.'
        )
    try:
        return resolver_disco_homolog_externa(os.environ, settings.BASE_DIR)
    except ImproperlyConfigured as exc:
        raise CommandError(f'Carga recusada: {exc}') from exc


def recusar_dados_incompativeis():
    """Recusa qualquer linha operacional fora do namespace fictício.

    Convênio Particular, formas de pagamento e demais seeds de migration
    não entram nesta varredura.
    """
    if User.objects.exclude(username__startswith='homolog.').exists():
        raise CommandError('Carga recusada: usuário fora do namespace homolog.')
    if Paciente.objects.exclude(nome_completo__startswith=PREFIXO).exists():
        raise CommandError('Carga recusada: paciente fora do prefixo HOMOLOG-.')
    if Dentista.objects.exclude(nome_completo__startswith=PREFIXO).exists():
        raise CommandError('Carga recusada: dentista fora do prefixo HOMOLOG-.')
    if Sala.objects.exclude(nome__startswith=PREFIXO).exists():
        raise CommandError('Carga recusada: sala fora do prefixo HOMOLOG-.')


def caminho_arquivo_senhas(disco):
    return Path(disco).resolve() / 'private' / ARQUIVO_SENHAS


def ler_senhas(destino):
    if not destino.is_file():
        return {}
    senhas = {}
    for linha in destino.read_text(encoding='utf-8').splitlines():
        if '=' not in linha or linha.startswith('Usuários'):
            continue
        username, _, senha = linha.partition('=')
        username = username.strip()
        if username:
            senhas[username] = senha
    return senhas


def _usuarios_homolog_existentes():
    return set(
        User.objects.filter(username__startswith='homolog.').values_list(
            'username', flat=True
        )
    )


def exigir_arquivo_senhas_coerente(disco, *, regerar):
    """Para se um usuário homolog.* já existe sem senha utilizável no arquivo.

    --regerar-senhas não dispensa essa regra para usuários fora dos seis
    esperados. Para os seis, a flag é a única forma de seguir sem o arquivo.
    """
    existentes = _usuarios_homolog_existentes()
    if not existentes:
        return
    destino = caminho_arquivo_senhas(disco)
    senhas = ler_senhas(destino)
    esperados = set(USUARIOS_ESPERADOS)
    if regerar:
        extras = sorted(existentes - esperados)
        faltando = [usuario for usuario in extras if not senhas.get(usuario)]
        if faltando:
            raise CommandError(
                'Carga recusada: arquivo de senhas ausente ou incoerente '
                'com usuários homolog existentes.'
            )
        return
    faltando = sorted(usuario for usuario in existentes if not senhas.get(usuario))
    if faltando:
        raise CommandError(
            'Carga recusada: arquivo de senhas ausente ou incoerente '
            'com usuários homolog existentes.'
        )


def gravar_senhas_externas(disco, senhas, *, modo):
    """Grava senhas só em private/SENHAS.txt, depois do commit, sem stdout."""
    destino = caminho_arquivo_senhas(disco)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if modo == 'acrescentar':
        atual = ler_senhas(destino)
        for username, senha in senhas.items():
            atual.setdefault(username, senha)
    elif modo == 'regerar':
        atual = ler_senhas(destino)
        atual.update(senhas)
    else:
        atual = dict(senhas)
    linhas = ['Usuários homolog.* — senhas da homologação externa (não versionar):']
    for username in sorted(atual):
        linhas.append(f'{username}={atual[username]}')
    conteudo = '\n'.join(linhas) + '\n'
    fd, temporario = tempfile.mkstemp(
        dir=destino.parent, prefix='.senhas-', suffix='.tmp'
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
            arquivo.write(conteudo)
        os.replace(temporario, destino)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return destino


class Command(BaseCommand):
    help = (
        'Cria dados fictícios HOMOLOG- apenas em consultorio_homolog_externa '
        'com DJANGO_ENV=homologacao. Recusa produção, desenvolvimento, '
        'HOMOLOG_LOCAL, SQLite e qualquer outro banco.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--regerar-senhas',
            action='store_true',
            help=(
                'Gira somente as senhas dos seis usuários fictícios esperados '
                'e reescreve o arquivo privado. Não dispensa as proteções.'
            ),
        )

    def handle(self, *args, **options):
        disco = exigir_ambiente_homolog_externa()
        regerar = bool(options['regerar_senhas'])
        with transaction.atomic():
            recusar_dados_incompativeis()
            exigir_arquivo_senhas_coerente(disco, regerar=regerar)
            criado, senhas = self._carregar(regerar=regerar)
        if senhas:
            if regerar:
                modo = 'regerar'
            elif _usuarios_homolog_existentes() == set(senhas):
                modo = 'criar'
            else:
                modo = 'acrescentar'
            gravar_senhas_externas(disco, senhas, modo=modo)
            self.stdout.write(
                'Senhas gravadas no disco privado da homologação externa.'
            )
        else:
            self.stdout.write('Senhas existentes preservadas.')
        self.stdout.write(self.style.SUCCESS(
            'Carga fictícia externa concluída.'
        ))
        for chave, valor in criado.items():
            self.stdout.write(f'{chave}: {valor}')

    def _carregar(self, *, regerar):
        hoje = timezone.localdate()
        competencia = hoje.replace(day=1)
        particular = Convenio.objects.filter(nome='Particular').first()
        senhas = {}

        salas = {}
        for nome, ativa in (
            ('HOMOLOG-Sala A', True),
            ('HOMOLOG-Sala B', True),
            ('HOMOLOG-Sala Inativa', True),
        ):
            sala, _ = Sala.objects.get_or_create(nome=nome, defaults={'ativa': ativa})
            salas[nome] = sala

        dentistas = {}
        for nome, sala_nome, ativo in (
            ('HOMOLOG-Dentista A', 'HOMOLOG-Sala A', True),
            ('HOMOLOG-Dentista B', 'HOMOLOG-Sala B', True),
            ('HOMOLOG-Dentista C', 'HOMOLOG-Sala Inativa', False),
        ):
            dentista, _ = Dentista.objects.get_or_create(
                nome_completo=nome,
                defaults={
                    'sala': salas[sala_nome],
                    'ativo': ativo,
                    'valor_hora': Decimal('200.00'),
                },
            )
            if dentista.ativo != ativo:
                dentista.ativo = ativo
                dentista.save(update_fields=['ativo'])
            dentistas[nome] = dentista

        specs = (
            ('homolog.admin', 'Homolog', 'Admin', True, None, None),
            ('homolog.secretaria', 'Homolog', 'Secretaria', False, PerfilUsuario.Papel.SECRETARIA, None),
            ('homolog.dentista.a', 'Homolog', 'DentistaA', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista A'),
            ('homolog.dentista.b', 'Homolog', 'DentistaB', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista B'),
            ('homolog.inativo', 'Homolog', 'Inativo', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista C'),
            ('homolog.auxiliar', 'Homolog', 'Auxiliar', False, PerfilUsuario.Papel.AUXILIAR, 'HOMOLOG-Dentista A'),
        )
        for username, first, last, admin, papel, dentista_nome in specs:
            user, criado = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'is_active': True,
                    'is_staff': admin,
                    'is_superuser': admin,
                    'email': f'{username}@homolog.local',
                },
            )
            if criado or regerar:
                senha = gerar_senha_homolog()
                user.set_password(senha)
                senhas[username] = senha
            user.first_name = first
            user.last_name = last
            user.is_active = True
            user.is_staff = admin
            user.is_superuser = admin
            user.save()
            if papel:
                perfil, _ = PerfilUsuario.objects.get_or_create(
                    usuario=user,
                    defaults={
                        'papel': papel,
                        'dentista': dentistas[dentista_nome] if dentista_nome else None,
                    },
                )
                perfil.papel = papel
                perfil.dentista = dentistas[dentista_nome] if dentista_nome else None
                perfil.full_clean()
                perfil.save()

        admin = User.objects.get(username='homolog.admin')
        nascimento = date(1990, 1, 15)
        pacientes = {}
        for nome in (
            'HOMOLOG-Ana',
            'HOMOLOG-Bruno',
            'HOMOLOG-Carla',
            'HOMOLOG-Diego',
            'HOMOLOG-Elena',
        ):
            paciente, _ = Paciente.objects.get_or_create(
                nome_completo=nome,
                defaults={
                    'data_nascimento': nascimento,
                    'telefone': '61900000000',
                    'convenio': particular,
                    'observacoes': 'Dado fictício de homologação externa.',
                },
            )
            pacientes[nome] = paciente

        dent_a = dentistas['HOMOLOG-Dentista A']
        dent_b = dentistas['HOMOLOG-Dentista B']
        consultas_spec = (
            (pacientes['HOMOLOG-Ana'], dent_a, time(8, 0), time(8, 30), Consulta.Status.AGENDADA),
            (pacientes['HOMOLOG-Ana'], dent_a, time(8, 30), time(9, 0), Consulta.Status.AGENDADA),
            (pacientes['HOMOLOG-Elena'], dent_a, time(9, 0), time(9, 30), Consulta.Status.PRESENTE),
            (pacientes['HOMOLOG-Carla'], dent_a, time(10, 0), time(10, 30), Consulta.Status.CONFIRMADA),
            (pacientes['HOMOLOG-Ana'], dent_a, time(14, 0), time(14, 30), Consulta.Status.FALTOU),
            (pacientes['HOMOLOG-Carla'], dent_a, time(15, 0), time(15, 30), Consulta.Status.CANCELADA),
            (pacientes['HOMOLOG-Bruno'], dent_b, time(8, 0), time(8, 30), Consulta.Status.AGENDADA),
            (pacientes['HOMOLOG-Carla'], dent_b, time(11, 0), time(11, 30), Consulta.Status.AGENDADA),
        )
        for paciente, dentista, inicio, fim, status in consultas_spec:
            consulta, _ = Consulta.objects.get_or_create(
                paciente=paciente,
                dentista=dentista,
                data=hoje,
                hora_inicio=inicio,
                hora_fim=fim,
                defaults={
                    'status': status,
                    'eh_legado': False,
                    'observacoes': 'Consulta fictícia HOMOLOG.',
                },
            )
            if consulta.status != status:
                consulta.status = status
                consulta.save(update_fields=['status'])

        ConsentimentoIA.objects.update_or_create(
            paciente=pacientes['HOMOLOG-Elena'],
            finalidade='transcricao_voz',
            defaults={
                'concedido': True,
                'concedido_em': timezone.now(),
                'revogado_em': None,
                'texto_versao': 'homolog-1',
                'registrado_por': admin,
                'observacoes': 'Consentimento fictício para teste de voz.',
            },
        )

        proc, _ = Procedimento.objects.get_or_create(
            dentista=dent_a,
            nome='HOMOLOG-Profilaxia',
            defaults={'duracao_estimada_minutos': 30, 'ativo': True},
        )
        PrecoProcedimento.objects.get_or_create(
            procedimento=proc,
            convenio=None,
            defaults={'valor': Decimal('120.00')},
        )

        fornecedor, _ = Fornecedor.objects.get_or_create(
            nome='HOMOLOG-Fornecedor Lab',
            defaults={'contato': 'homolog@ficticio.local'},
        )
        categoria, _ = CategoriaContaPagar.objects.get_or_create(
            nome='HOMOLOG-Categoria',
            defaults={'ativa': True},
        )
        ContaPagar.objects.get_or_create(
            descricao='HOMOLOG-Conta a pagar',
            defaults={
                'fornecedor': fornecedor,
                'categoria': categoria,
                'competencia': competencia,
                'vencimento': hoje,
                'valor_original': Decimal('80.00'),
                'recorrencia': ContaPagar.Recorrencia.UNICA,
                'situacao': ContaPagar.Situacao.PENDENTE_APROVACAO,
                'responsavel': admin,
                'observacoes': 'Título fictício de homologação.',
            },
        )
        conta_rec, _ = ContaReceber.objects.get_or_create(
            descricao='HOMOLOG-Conta a receber Ana',
            paciente=pacientes['HOMOLOG-Ana'],
            defaults={
                'consulta': Consulta.objects.filter(
                    paciente=pacientes['HOMOLOG-Ana'],
                    dentista=dent_a,
                    hora_inicio=time(8, 0),
                ).first(),
                'valor_original': Decimal('150.00'),
                'data_emissao': hoje,
                'criado_por': admin,
            },
        )
        ParcelaContaReceber.objects.get_or_create(
            conta=conta_rec,
            numero=1,
            defaults={
                'vencimento': hoje,
                'valor_original': conta_rec.valor_original,
            },
        )
        Despesa.objects.get_or_create(
            descricao='HOMOLOG-Despesa compartilhada',
            competencia=competencia,
            defaults={
                'valor': Decimal('200.00'),
                'tipo': Despesa.Tipo.COMPARTILHADA,
                'pago_por': dent_a,
                'observacoes': 'Despesa fictícia de homologação.',
            },
        )

        contagens = {
            'salas': Sala.objects.filter(nome__startswith=PREFIXO).count(),
            'dentistas': Dentista.objects.filter(nome_completo__startswith=PREFIXO).count(),
            'usuarios': User.objects.filter(username__startswith='homolog.').count(),
            'pacientes': Paciente.objects.filter(nome_completo__startswith=PREFIXO).count(),
            'consultas': Consulta.objects.filter(
                observacoes__startswith='Consulta fictícia HOMOLOG'
            ).count(),
        }
        return contagens, senhas
