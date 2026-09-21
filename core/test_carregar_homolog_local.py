import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from core.management.commands.carregar_homolog_local import (
    Command,
    exigir_ambiente_homolog,
    gerar_senha_homolog,
    gravar_senhas_homolog,
)
from core.models import Consulta, Paciente
from locacao.models import Dentista, Sala


class GuardsCarregarHomologTests(SimpleTestCase):
    def test_fonte_nao_contem_senha_fixa(self):
        fonte = Path(__file__).resolve().parent / 'management' / 'commands' / 'carregar_homolog_local.py'
        texto = fonte.read_text(encoding='utf-8')
        self.assertIn('token_urlsafe', texto)
        self.assertNotIn('SENHA_INICIAL', texto)
        self.assertNotRegex(texto, r"set_password\(['\"]")

    def test_gerar_senha_e_aleatoria_e_longa(self):
        senha_a = gerar_senha_homolog()
        senha_b = gerar_senha_homolog()
        self.assertNotEqual(senha_a, senha_b)
        self.assertGreaterEqual(len(senha_a), 20)
        self.assertGreaterEqual(len(senha_b), 20)

    def test_senhas_txt_permanece_fora_do_git(self):
        raiz = Path(__file__).resolve().parents[1]
        gitignore = (raiz / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('homolog_local/', gitignore)

    def test_gravar_senhas_nao_usa_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = gravar_senhas_homolog(
                {'homolog.admin': gerar_senha_homolog()},
                base_dir=tmp,
            )
            self.assertEqual(destino.name, 'SENHAS.txt')
            self.assertTrue(destino.is_file())
            self.assertIn('homolog.admin=', destino.read_text(encoding='utf-8'))

    @override_settings(EM_PRODUCAO=True)
    def test_recusa_producao(self):
        with self.assertRaises(CommandError):
            exigir_ambiente_homolog()

    def test_recusa_sem_homolog_local(self):
        with patch.dict(os.environ, {'HOMOLOG_LOCAL': ''}, clear=False):
            with self.assertRaises(CommandError):
                exigir_ambiente_homolog()

    def test_recusa_banco_que_nao_e_consultorio_homolog(self):
        with self.assertRaises(CommandError) as contexto:
            exigir_ambiente_homolog()
        self.assertIn('consultorio_homolog', str(contexto.exception))


class IdempotenciaCarregarHomologTests(TestCase):
    def test_segunda_carga_nao_duplica_registros(self):
        comando = Command()
        primeira, senhas_a = comando._carregar()
        segunda, senhas_b = comando._carregar()
        self.assertEqual(primeira, segunda)
        self.assertEqual(primeira['usuarios'], 6)
        self.assertEqual(primeira['pacientes'], 5)
        self.assertEqual(primeira['consultas'], 8)
        self.assertEqual(primeira['salas'], 3)
        self.assertEqual(primeira['dentistas'], 3)
        self.assertEqual(User.objects.filter(username__startswith='homolog.').count(), 6)
        self.assertEqual(Paciente.objects.filter(nome_completo__startswith='HOMOLOG-').count(), 5)
        self.assertEqual(Consulta.objects.filter(observacoes__startswith='Consulta fictícia HOMOLOG').count(), 8)
        self.assertEqual(Sala.objects.filter(nome__startswith='HOMOLOG-').count(), 3)
        self.assertEqual(Dentista.objects.filter(nome_completo__startswith='HOMOLOG-').count(), 3)
        self.assertEqual(set(senhas_a), set(senhas_b))
        self.assertEqual(len(senhas_a), 6)

    def test_call_command_recusa_banco_de_teste(self):
        with self.assertRaises(CommandError):
            call_command('carregar_homolog_local')
