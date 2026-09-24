import os
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from core.management.commands.carregar_homolog_externa import (
    USUARIOS_ESPERADOS,
    Command,
    caminho_arquivo_senhas,
    exigir_ambiente_homolog_externa,
    exigir_arquivo_senhas_coerente,
    gravar_senhas_externas,
    recusar_dados_incompativeis,
)
from core.models import Consulta, Convenio, FormaPagamentoConfiguravel, Paciente
from locacao.management.commands.criar_usuarios_clinica import recusar_em_homologacao
from locacao.models import Dentista, Sala

EXIGIR = (
    'core.management.commands.carregar_homolog_externa.'
    'exigir_ambiente_homolog_externa'
)
CURSOR_EXTERNO = (
    'core.management.commands.carregar_homolog_externa.connection'
)
CURSOR_CLINICA = (
    'locacao.management.commands.criar_usuarios_clinica.connection'
)


def _banco(nome, engine='django.db.backends.postgresql'):
    return {'default': {'ENGINE': engine, 'NAME': nome}}


class _Cursor:
    def __init__(self, nome):
        self.nome = nome

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return (self.nome,)


def _conexao(nome):
    class Conexao:
        def cursor(self):
            return _Cursor(nome)
    return Conexao()


class GuardsCarregarHomologExternaTests(SimpleTestCase):
    def test_fonte_nao_tem_senha_fixa_nem_carga_real(self):
        fonte = (
            Path(__file__).resolve().parent
            / 'management'
            / 'commands'
            / 'carregar_homolog_externa.py'
        )
        texto = fonte.read_text(encoding='utf-8')
        self.assertIn('gerar_senha_homolog', texto)
        self.assertNotIn('criar_usuarios_clinica', texto)
        self.assertNotIn('SENHA_INICIAL', texto)
        self.assertNotRegex(texto, r"set_password\(['\"]")
        self.assertNotIn('exigir_ambiente_homolog(', texto)
        self.assertNotIn('_carregar()', texto)

    @override_settings(AMBIENTE='development', EM_PRODUCAO=False)
    def test_recusa_development(self):
        with self.assertRaises(CommandError) as contexto:
            exigir_ambiente_homolog_externa()
        self.assertIn('homologacao', str(contexto.exception))

    @override_settings(AMBIENTE='production', EM_PRODUCAO=True)
    def test_recusa_production(self):
        with self.assertRaises(CommandError) as contexto:
            exigir_ambiente_homolog_externa()
        self.assertIn('EM_PRODUCAO', str(contexto.exception))

    @override_settings(AMBIENTE='homologacao', EM_PRODUCAO=True)
    def test_production_nao_passa_mesmo_com_ambiente_homologacao(self):
        with self.assertRaises(CommandError) as contexto:
            exigir_ambiente_homolog_externa()
        self.assertIn('EM_PRODUCAO', str(contexto.exception))

    @override_settings(AMBIENTE='homologacao', EM_PRODUCAO=False)
    def test_recusa_homolog_local(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': '1'}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('HOMOLOG_LOCAL', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa', 'django.db.backends.sqlite3'),
    )
    def test_recusa_sqlite(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('PostgreSQL', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio'),
    )
    def test_recusa_consultorio(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('consultorio_homolog_externa', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog'),
    )
    def test_recusa_consultorio_homolog(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('consultorio_homolog_externa', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('outro_banco'),
    )
    def test_recusa_outro_postgresql(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('consultorio_homolog_externa', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa'),
    )
    def test_recusa_current_database_divergente(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with patch(CURSOR_EXTERNO, _conexao('consultorio_homolog')):
                with self.assertRaises(CommandError) as contexto:
                    exigir_ambiente_homolog_externa()
        self.assertIn('current_database()', str(contexto.exception))

    def _aceita(self, configurado, atual):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                'HOMOLOG_LOCAL': '',
                'HOMOLOG_EXTERNA_DISK_PATH': tmp,
            }):
                with patch(CURSOR_EXTERNO, _conexao(atual)):
                    with override_settings(
                        AMBIENTE='homologacao',
                        EM_PRODUCAO=False,
                        DATABASES=_banco(configurado),
                    ):
                        disco = exigir_ambiente_homolog_externa()
        self.assertEqual(disco, Path(tmp).resolve())

    def test_aceita_nome_exato(self):
        self._aceita('consultorio_homolog_externa', 'consultorio_homolog_externa')

    def test_aceita_sufixo_do_render(self):
        self._aceita(
            'consultorio_homolog_externa_183n',
            'consultorio_homolog_externa_183n',
        )

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa'),
    )
    def test_recusa_current_database_diferente_do_configurado(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with patch(CURSOR_EXTERNO, _conexao('consultorio_homolog_externa_183n')):
                with self.assertRaises(CommandError) as contexto:
                    exigir_ambiente_homolog_externa()
        self.assertIn(
            'current_database() diferente do banco configurado',
            str(contexto.exception),
        )

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa_x'),
    )
    def test_recusa_sufixo_invalido_configurado(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with self.assertRaises(CommandError) as contexto:
                exigir_ambiente_homolog_externa()
        self.assertIn('consultorio_homolog_externa', str(contexto.exception))
        self.assertNotIn('current_database()', str(contexto.exception))

    @override_settings(
        AMBIENTE='homologacao',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa_183n'),
    )
    def test_recusa_current_database_fora_do_padrao(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}):
            with patch(CURSOR_EXTERNO, _conexao('consultorio_homolog_externa_183n_extra')):
                with self.assertRaises(CommandError) as contexto:
                    exigir_ambiente_homolog_externa()
        self.assertIn('current_database()', str(contexto.exception))

    def test_call_command_e_regerar_recusam_o_banco_de_teste(self):
        with self.assertRaises(CommandError):
            call_command('carregar_homolog_externa')
        with self.assertRaises(CommandError):
            call_command('carregar_homolog_externa', '--regerar-senhas')


class DadosIncompativeisTests(TestCase):
    def test_seeds_legitimos_nao_recusam(self):
        recusar_dados_incompativeis()
        Convenio.objects.create(nome='Particular')
        FormaPagamentoConfiguravel.objects.create(nome='Dinheiro teste', codigo='dinheiro-teste')
        recusar_dados_incompativeis()

    def test_recusa_usuario_fora_do_namespace(self):
        User.objects.create_user('pessoa.real', password='x')
        with self.assertRaises(CommandError) as contexto:
            recusar_dados_incompativeis()
        self.assertIn('usuário', str(contexto.exception))

    def test_recusa_paciente_fora_do_prefixo(self):
        Paciente.objects.create(
            nome_completo='Ana Real',
            data_nascimento=date(1990, 1, 1),
            telefone='61900000000',
        )
        with self.assertRaises(CommandError) as contexto:
            recusar_dados_incompativeis()
        self.assertIn('paciente', str(contexto.exception))

    def test_recusa_dentista_fora_do_prefixo(self):
        sala = Sala.objects.create(nome='HOMOLOG-Sala Suporte')
        Dentista.objects.create(nome_completo='Dra Real', sala=sala)
        with self.assertRaises(CommandError) as contexto:
            recusar_dados_incompativeis()
        self.assertIn('dentista', str(contexto.exception))

    def test_recusa_sala_fora_do_prefixo(self):
        Sala.objects.create(nome='Sala Real')
        with self.assertRaises(CommandError) as contexto:
            recusar_dados_incompativeis()
        self.assertIn('sala', str(contexto.exception))


class CargaExternaTests(TestCase):
    def test_primeira_carga_e_rerun_sem_duplicar_nem_girar_senha(self):
        comando = Command()
        primeira, senhas_a = comando._carregar(regerar=False)
        self.assertEqual(primeira['usuarios'], 6)
        self.assertEqual(primeira['pacientes'], 5)
        self.assertEqual(primeira['consultas'], 8)
        self.assertEqual(primeira['salas'], 3)
        self.assertEqual(primeira['dentistas'], 3)
        self.assertEqual(set(senhas_a), set(USUARIOS_ESPERADOS))
        admin = User.objects.get(username='homolog.admin')
        self.assertTrue(admin.check_password(senhas_a['homolog.admin']))

        segunda, senhas_b = comando._carregar(regerar=False)
        self.assertEqual(primeira, segunda)
        self.assertEqual(senhas_b, {})
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(senhas_a['homolog.admin']))
        self.assertEqual(
            Consulta.objects.filter(
                observacoes__startswith='Consulta fictícia HOMOLOG'
            ).count(),
            8,
        )

    def test_conjunto_parcial_cria_somente_o_que_falta(self):
        User.objects.create_user('homolog.admin', password='senha-antiga-estavel')
        Sala.objects.create(nome='HOMOLOG-Sala A')
        _, senhas = Command()._carregar(regerar=False)
        self.assertNotIn('homolog.admin', senhas)
        self.assertEqual(len(senhas), 5)
        self.assertEqual(
            User.objects.filter(username__startswith='homolog.').count(),
            6,
        )
        self.assertEqual(Sala.objects.filter(nome__startswith='HOMOLOG-').count(), 3)
        admin = User.objects.get(username='homolog.admin')
        self.assertTrue(admin.check_password('senha-antiga-estavel'))

    def test_arquivo_ausente_recusa_e_preserva_senha(self):
        _, senhas = Command()._carregar(regerar=False)
        admin = User.objects.get(username='homolog.admin')
        with tempfile.TemporaryDirectory() as tmp:
            with patch(EXIGIR, return_value=Path(tmp)):
                with self.assertRaises(CommandError) as contexto:
                    call_command('carregar_homolog_externa', stdout=StringIO())
            self.assertIn('incoerente', str(contexto.exception))
            self.assertFalse(caminho_arquivo_senhas(tmp).exists())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(senhas['homolog.admin']))

    def test_arquivo_incompleto_recusa(self):
        Command()._carregar(regerar=False)
        with tempfile.TemporaryDirectory() as tmp:
            destino = caminho_arquivo_senhas(tmp)
            destino.parent.mkdir(parents=True)
            destino.write_text('homolog.admin=uma-senha-qualquer\n', encoding='utf-8')
            with self.assertRaises(CommandError):
                exigir_arquivo_senhas_coerente(Path(tmp), regerar=False)

    def test_stdout_nao_contem_senha_e_arquivo_e_privado(self):
        with tempfile.TemporaryDirectory() as tmp:
            saida = StringIO()
            with patch(EXIGIR, return_value=Path(tmp)):
                with patch('os.chmod') as chmod:
                    call_command('carregar_homolog_externa', stdout=saida)
                    self.assertTrue(chmod.called)
            destino = caminho_arquivo_senhas(tmp)
            self.assertEqual(destino.parent.name, 'private')
            self.assertNotIn('media', destino.parts)
            self.assertNotIn('homolog_local', destino.parts)
            texto = saida.getvalue()
            self.assertNotIn('SENHAS.txt', texto)
            for linha in destino.read_text(encoding='utf-8').splitlines():
                if '=' not in linha:
                    continue
                senha = linha.split('=', 1)[1]
                self.assertNotIn(senha, texto)
                self.assertGreaterEqual(len(senha), 20)

    def test_regerar_senhas_gira_somente_os_seis_e_respeita_extra(self):
        _, senhas = Command()._carregar(regerar=False)
        extra = User.objects.create_user('homolog.extra', password='senha-extra-estavel')
        with tempfile.TemporaryDirectory() as tmp:
            disco = Path(tmp)
            gravar_senhas_externas(disco, {**senhas, 'homolog.extra': 'senha-extra-estavel'}, modo='criar')
            saida = StringIO()
            with patch(EXIGIR, return_value=disco):
                call_command(
                    'carregar_homolog_externa',
                    '--regerar-senhas',
                    stdout=saida,
                )
            admin = User.objects.get(username='homolog.admin')
            extra.refresh_from_db()
            novas = ler_arquivo(disco)
            self.assertFalse(admin.check_password(senhas['homolog.admin']))
            self.assertTrue(admin.check_password(novas['homolog.admin']))
            self.assertTrue(extra.check_password('senha-extra-estavel'))
            self.assertEqual(novas['homolog.extra'], 'senha-extra-estavel')
            self.assertNotIn(novas['homolog.admin'], saida.getvalue())

    def test_regerar_senhas_recusa_extra_sem_arquivo(self):
        Command()._carregar(regerar=False)
        User.objects.create_user('homolog.extra', password='senha-extra-estavel')
        with tempfile.TemporaryDirectory() as tmp:
            with patch(EXIGIR, return_value=Path(tmp)):
                with self.assertRaises(CommandError):
                    call_command(
                        'carregar_homolog_externa',
                        '--regerar-senhas',
                        stdout=StringIO(),
                    )
        self.assertTrue(
            User.objects.get(username='homolog.extra').check_password(
                'senha-extra-estavel'
            )
        )

    def test_usuario_real_bloqueia_regerar_senhas(self):
        User.objects.create_user('pessoa.real', password='senha-real')
        with tempfile.TemporaryDirectory() as tmp:
            with patch(EXIGIR, return_value=Path(tmp)):
                with self.assertRaises(CommandError):
                    call_command(
                        'carregar_homolog_externa',
                        '--regerar-senhas',
                        stdout=StringIO(),
                    )
        self.assertTrue(
            User.objects.get(username='pessoa.real').check_password('senha-real')
        )


def ler_arquivo(disco):
    from core.management.commands.carregar_homolog_externa import ler_senhas
    return ler_senhas(caminho_arquivo_senhas(disco))


class CriarUsuariosClinicaTravaTests(SimpleTestCase):
    @override_settings(AMBIENTE='homologacao', EM_PRODUCAO=False)
    def test_recusa_ambiente_homologacao(self):
        with self.assertRaises(CommandError) as contexto:
            recusar_em_homologacao()
        self.assertIn('homologação externa', str(contexto.exception))

    @override_settings(
        AMBIENTE='development',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog_externa'),
    )
    def test_recusa_banco_externo_configurado(self):
        with self.assertRaises(CommandError):
            recusar_em_homologacao()

    @override_settings(
        AMBIENTE='development',
        EM_PRODUCAO=False,
        DATABASES=_banco('consultorio_homolog'),
    )
    def test_recusa_banco_local_configurado(self):
        with self.assertRaises(CommandError):
            recusar_em_homologacao()

    @override_settings(
        AMBIENTE='production',
        EM_PRODUCAO=True,
        DATABASES=_banco('consultorio'),
    )
    def test_recusa_current_database_de_homologacao(self):
        with patch(CURSOR_CLINICA, _conexao('consultorio_homolog_externa')):
            with self.assertRaises(CommandError) as contexto:
                recusar_em_homologacao()
        self.assertIn('current_database()', str(contexto.exception))
        with patch(CURSOR_CLINICA, _conexao('consultorio_homolog')):
            with self.assertRaises(CommandError):
                recusar_em_homologacao()

    @override_settings(
        AMBIENTE='production',
        EM_PRODUCAO=True,
        DATABASES=_banco('consultorio'),
    )
    def test_producao_com_banco_consultorio_segue(self):
        with patch(CURSOR_CLINICA, _conexao('consultorio')):
            recusar_em_homologacao()

    @override_settings(
        AMBIENTE='development',
        EM_PRODUCAO=False,
        DATABASES=_banco('db.sqlite3', 'django.db.backends.sqlite3'),
    )
    def test_sqlite_de_desenvolvimento_nao_consulta_current_database(self):
        with patch(CURSOR_CLINICA) as conexao:
            recusar_em_homologacao()
        conexao.cursor.assert_not_called()
