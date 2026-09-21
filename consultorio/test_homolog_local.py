import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from consultorio.settings import (
    resolver_media_root,
    resolver_upload_temp_local,
    validar_homolog_local,
    _pastas_homolog_local,
    _resolver_exames_root_ambiente,
)


class IsolamentoHomologLocalTests(SimpleTestCase):
    def setUp(self):
        self.base = Path(settings.BASE_DIR)
        self.pastas = _pastas_homolog_local(self.base)

    def _validar(self, environ, **kwargs):
        padrao = {
            'em_producao': False,
            'media_root': self.pastas['media'],
            'file_upload_temp_dir': str(self.pastas['tmp']),
            'database_name': 'consultorio_homolog',
            'database_engine': 'django.db.backends.postgresql',
            'base_dir': self.base,
        }
        padrao.update(kwargs)
        validar_homolog_local(environ, **padrao)

    def test_defaults_locais_inalterados_sem_variaveis(self):
        environ = {}
        self.assertEqual(
            resolver_media_root(False, environ, self.base),
            self.base / 'media',
        )
        self.assertIsNone(resolver_upload_temp_local(False, environ, self.base))
        self.assertEqual(
            _resolver_exames_root_ambiente(environ, self.base),
            self.base / 'private_exames',
        )
        self._validar({})

    def test_homolog_local_exige_pastas_e_banco(self):
        environ = {
            'HOMOLOG_LOCAL': '1',
            'EXAMES_ROOT': 'homolog_local/private_exames',
        }
        self._validar(environ)
        self.assertEqual(
            resolver_media_root(
                False,
                {'DJANGO_MEDIA_ROOT': 'homolog_local/media'},
                self.base,
            ).resolve(),
            self.pastas['media'],
        )
        self.assertEqual(
            Path(resolver_upload_temp_local(
                False,
                {'DJANGO_FILE_UPLOAD_TEMP_DIR': 'homolog_local/tmp'},
                self.base,
            )).resolve(),
            self.pastas['tmp'],
        )

    def test_homolog_local_incompleto_aborta(self):
        environ = {'HOMOLOG_LOCAL': '1', 'EXAMES_ROOT': 'homolog_local/private_exames'}
        with self.assertRaises(ImproperlyConfigured):
            self._validar(environ, database_name='outro')
        with self.assertRaises(ImproperlyConfigured):
            self._validar(
                environ,
                database_engine='django.db.backends.sqlite3',
                database_name='consultorio_homolog',
            )
        with self.assertRaises(ImproperlyConfigured):
            self._validar(environ, media_root=self.base / 'media')
        with self.assertRaises(ImproperlyConfigured):
            self._validar(
                {'HOMOLOG_LOCAL': '1'},
                file_upload_temp_dir=str(self.pastas['tmp']),
            )
        with self.assertRaises(ImproperlyConfigured):
            self._validar(environ, file_upload_temp_dir=None)
        with self.assertRaises(ImproperlyConfigured):
            self._validar(environ, em_producao=True)

    def test_producao_ignora_variaveis_locais_de_midia(self):
        environ = {
            'RENDER_DISK_PATH': '/var/data',
            'DJANGO_MEDIA_ROOT': 'homolog_local/media',
            'DJANGO_FILE_UPLOAD_TEMP_DIR': 'homolog_local/tmp',
        }
        self.assertEqual(
            resolver_media_root(True, environ, self.base),
            Path('/var/data') / 'media',
        )
        self.assertIsNone(resolver_upload_temp_local(True, environ, self.base))
        with self.assertRaises(ImproperlyConfigured) as contexto:
            resolver_media_root(True, {}, self.base)
        self.assertIn('RENDER_DISK_PATH é obrigatório', str(contexto.exception))

    def test_configuracao_ativa_usa_somente_homolog_local(self):
        self.assertTrue(
            str(os.environ.get('HOMOLOG_LOCAL', '')).strip().lower()
            in ('1', 'true', 'yes')
        )
        self.assertEqual(Path(settings.MEDIA_ROOT).resolve(), self.pastas['media'])
        self.assertEqual(
            Path(settings.FILE_UPLOAD_TEMP_DIR).resolve(),
            self.pastas['tmp'],
        )
        self.assertEqual(
            _resolver_exames_root_ambiente(os.environ, self.base).resolve(),
            self.pastas['exames'],
        )
        self.assertNotEqual(
            Path(settings.MEDIA_ROOT).resolve(),
            (self.base / 'media').resolve(),
        )
        self.assertNotEqual(
            _resolver_exames_root_ambiente(os.environ, self.base).resolve(),
            (self.base / 'private_exames').resolve(),
        )

    def test_gitignore_e_dockerignore_incluem_homolog_local(self):
        gitignore = (self.base / '.gitignore').read_text(encoding='utf-8')
        dockerignore = (self.base / '.dockerignore').read_text(encoding='utf-8')
        self.assertIn('homolog_local/', gitignore)
        self.assertIn('homolog_local/', dockerignore)
