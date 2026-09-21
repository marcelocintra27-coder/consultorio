"""Carga determinística de dados fictícios só no PostgreSQL consultorio_homolog."""
import os
import secrets
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

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
from consultorio.settings import (
    _flag_ambiente,
    _pastas_homolog_local,
    _resolver_exames_root_ambiente,
)
from ia_seguranca.models import ConsentimentoIA
from locacao.models import Dentista, Despesa, PerfilUsuario, Sala

PREFIXO = 'HOMOLOG-'
ARQUIVO_SENHAS = 'SENHAS.txt'


def gerar_senha_homolog():
    return secrets.token_urlsafe(24)


def exigir_ambiente_homolog():
    if getattr(settings, 'EM_PRODUCAO', False):
        raise CommandError('Carga recusada: EM_PRODUCAO está ativo.')
    if not _flag_ambiente(os.environ, 'HOMOLOG_LOCAL'):
        raise CommandError('Carga recusada: HOMOLOG_LOCAL não está ativo.')
    engine = str(settings.DATABASES['default'].get('ENGINE') or '')
    if 'postgres' not in engine.lower():
        raise CommandError('Carga recusada: engine não é PostgreSQL.')
    nome = Path(str(settings.DATABASES['default'].get('NAME') or '')).name
    if nome != 'consultorio_homolog':
        raise CommandError('Carga recusada: banco não é consultorio_homolog.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        atual = cursor.fetchone()[0]
    if atual != 'consultorio_homolog':
        raise CommandError(
            'Carga recusada: current_database() diferente de consultorio_homolog.'
        )
    pastas = _pastas_homolog_local(settings.BASE_DIR)
    if Path(settings.MEDIA_ROOT).resolve() != pastas['media']:
        raise CommandError('Carga recusada: MEDIA_ROOT fora de homolog_local/media.')
    exames = _resolver_exames_root_ambiente(os.environ, settings.BASE_DIR)
    if exames.resolve() != pastas['exames']:
        raise CommandError(
            'Carga recusada: EXAMES_ROOT fora de homolog_local/private_exames.'
        )
    temp = getattr(settings, 'FILE_UPLOAD_TEMP_DIR', None)
    if not temp or Path(temp).resolve() != pastas['tmp']:
        raise CommandError(
            'Carga recusada: FILE_UPLOAD_TEMP_DIR fora de homolog_local/tmp.'
        )


def gravar_senhas_homolog(senhas, base_dir=None):
    """Grava senhas só em homolog_local/; nunca envia ao stdout."""
    pasta = Path(base_dir or settings.BASE_DIR) / 'homolog_local'
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / ARQUIVO_SENHAS
    linhas = [
        'Usuários homolog.* — senhas locais geradas (não versionar):',
    ]
    for username in sorted(senhas):
        linhas.append(f'{username}={senhas[username]}')
    destino.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
    return destino


class Command(BaseCommand):
    help = (
        'Cria dados fictícios HOMOLOG- apenas em consultorio_homolog com '
        'HOMOLOG_LOCAL=1. Recusa SQLite, produção e outros bancos.'
    )

    def handle(self, *args, **options):
        exigir_ambiente_homolog()
        with transaction.atomic():
            criado, senhas = self._carregar()
        gravar_senhas_homolog(senhas)
        self.stdout.write(self.style.SUCCESS(
            'Carga fictícia concluída. Senhas gravadas em homolog_local/ '
            '(arquivo ignorado pelo Git).'
        ))
        for chave, valor in criado.items():
            self.stdout.write(f'{chave}: {valor}')

    def _carregar(self):
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

        usuarios = {}
        specs = (
            ('homolog.admin', 'Homolog', 'Admin', True, None, None),
            ('homolog.secretaria', 'Homolog', 'Secretaria', False, PerfilUsuario.Papel.SECRETARIA, None),
            ('homolog.dentista.a', 'Homolog', 'DentistaA', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista A'),
            ('homolog.dentista.b', 'Homolog', 'DentistaB', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista B'),
            ('homolog.inativo', 'Homolog', 'Inativo', False, PerfilUsuario.Papel.DENTISTA, 'HOMOLOG-Dentista C'),
            ('homolog.auxiliar', 'Homolog', 'Auxiliar', False, PerfilUsuario.Papel.AUXILIAR, 'HOMOLOG-Dentista A'),
        )
        for username, first, last, admin, papel, dentista_nome in specs:
            user, _criado = User.objects.get_or_create(
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
            usuarios[username] = user

        admin = usuarios['homolog.admin']
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
                    'observacoes': 'Dado fictício de homologação local.',
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
