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
