import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class DockerDeploySecurityTests(SimpleTestCase):
    def setUp(self):
        self.raiz = Path(settings.BASE_DIR)

    def test_a7_contexto_docker_exclui_segredos_e_dados_locais(self):
        ignorados = (self.raiz / '.dockerignore').read_text(encoding='utf-8')
        for padrao in ('.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', 'secrets/'):
            self.assertIn(padrao, ignorados)

    def test_producao_declara_postgres_disco_smtp_e_segredos_externos(self):
        configuracoes = (self.raiz / 'consultorio' / 'settings.py').read_text(
            encoding='utf-8'
        )
        for trecho in (
            "DATABASE_URL é obrigatória em produção",
            "RENDER_DISK_PATH é obrigatório",
            "Configuração SMTP ausente em produção",
            "SECRET_KEY de produção deve ser aleatória",
            "django.core.mail.backends.smtp.EmailBackend",
        ):
            self.assertIn(trecho, configuracoes)

        blueprint = (self.raiz / 'render.yaml').read_text(encoding='utf-8')
        for trecho in (
            'fromDatabase:',
            'name: consultorio-db',
            'mountPath: /var/data',
            'plan: starter',
            'plan: 0.5c-1g',
            'key: SECRET_KEY\n        sync: false',
            'key: SMTP_PASSWORD\n        sync: false',
        ):
            self.assertIn(trecho, blueprint)

    def test_a7_dependencias_e_ffmpeg_ficam_fixados(self):
        requisitos = (self.raiz / 'requirements.txt').read_text(encoding='utf-8')
        self.assertIn('Django==6.1', requisitos)
        self.assertIn('faster-whisper==1.2.1', requisitos)
        self.assertIn('gunicorn==26.2.0', requisitos)
        self.assertIn('whitenoise==6.12.0', requisitos)
        self.assertIn('dj-database-url==3.1.2', requisitos)
        self.assertIn('psycopg[binary]==3.3.5', requisitos)

        dockerfile = (self.raiz / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('python:3.12.14-slim-bookworm@sha256:', dockerfile)
        self.assertIn('ffmpeg=7:5.1.9-0+deb12u1', dockerfile)
        self.assertIn('python manage.py migrate --noinput', dockerfile)


class HomologacaoExternaBlueprintTests(SimpleTestCase):
    def setUp(self):
        self.raiz = Path(settings.BASE_DIR)
        self.blueprint = (self.raiz / 'render.homolog.yaml').read_text(
            encoding='utf-8'
        )

    def test_blueprint_homolog_free_sem_disco_e_isolado_da_producao(self):
        for trecho in (
            'name: consultorio-homolog\n    runtime: docker\n    plan: free',
            "autoDeployTrigger: 'off'",
            'key: DJANGO_ENV\n        value: homologacao',
            'name: consultorio-homolog-db',
            'databaseName: consultorio_homolog_externa',
            'key: HOMOLOG_EXTERNA_DISK_PATH\n        value: /tmp/consultorio-homolog',
            'key: SECRET_KEY\n        sync: false',
            'value: consultorio-homolog.onrender.com',
            'value: https://consultorio-homolog.onrender.com',
        ):
            self.assertIn(trecho, self.blueprint)
        linhas = [
            linha for linha in self.blueprint.splitlines()
            if not linha.lstrip().startswith('#')
        ]
        conteudo = '\n'.join(linhas)
        for proibido in (
            'disk:',
            'mountPath:',
            '/var/data',
            'RENDER_DISK_PATH',
            'consultorio-db',
            'consultorio-a7um',
            'plan: starter',
            'HOMOLOG_LOCAL',
            'carregar_homolog',
        ):
            self.assertNotIn(proibido, conteudo)
        self.assertEqual(conteudo.count('plan: free'), 2)


class ProducaoSemFallbackEfemeroTests(SimpleTestCase):
    def _importar_settings(self, **variaveis):
        ambiente = dict(os.environ)
        ambiente.update({
            'DJANGO_ENV': 'production',
            'RENDER': 'true',
            'SECRET_KEY': 'p' * 50,
            'DJANGO_ALLOWED_HOSTS': 'consultorio-a7um.onrender.com',
            'DATABASE_URL': 'postgres://usuario:segredo@db.example.com:5432/consultorio',
            'HOMOLOG_LOCAL': '',
            'PYTHONIOENCODING': 'utf-8',
        })
        ambiente.update(variaveis)
        return subprocess.run(
            [sys.executable, '-c', 'import consultorio.settings'],
            cwd=settings.BASE_DIR,
            env=ambiente,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=120,
        )

    def test_producao_ignora_disco_homolog_e_exige_render_disk_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            resultado = self._importar_settings(
                RENDER_DISK_PATH='',
                HOMOLOG_EXTERNA_DISK_PATH=tmp,
            )
            self.assertNotEqual(resultado.returncode, 0)
            self.assertIn('ImproperlyConfigured', resultado.stderr)
            self.assertIn('RENDER_DISK_PATH é obrigatório', resultado.stderr)
            for pasta in ('media', 'private_exames', 'tmp'):
                self.assertFalse((Path(tmp) / pasta).exists())
