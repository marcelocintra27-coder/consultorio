import tempfile
from pathlib import Path

import dj_database_url
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from consultorio.settings import (
    BANCO_HOMOLOG_EXTERNA,
    configuracao_https_publica,
    debug_habilitado,
    exigir_database_url,
    exige_smtp,
    recusar_homolog_local_na_externa,
    resolver_ambiente,
    resolver_csrf_homolog_externa,
    resolver_disco_homolog_externa,
    resolver_hosts_homolog_externa,
    ssl_banco_exigido,
    validar_banco_homolog_externa,
    validar_secret_key_publica,
)


CHAVE_SEGURA = 'h' * 50
HOST_EXTERNO = 'homolog.example.com'
ORIGEM_EXTERNA = 'https://homolog.example.com'


def _banco(url):
    return dj_database_url.parse(url, conn_max_age=0, ssl_require=False)


class AmbienteExplicitoTests(SimpleTestCase):
    def test_development_e_o_padrao_sem_render(self):
        self.assertEqual(resolver_ambiente({}), 'development')
        self.assertEqual(
            resolver_ambiente({'DJANGO_ENV': 'development'}),
            'development',
        )

    def test_production_e_homologacao_explicitos(self):
        self.assertEqual(resolver_ambiente({'DJANGO_ENV': 'production'}), 'production')
        self.assertEqual(resolver_ambiente({'DJANGO_ENV': 'homologacao'}), 'homologacao')

    def test_render_sem_ambiente_valido_falha_fechado(self):
        for environ in (
            {'RENDER': 'true'},
            {'RENDER': 'true', 'DJANGO_ENV': 'development'},
            {'RENDER': 'true', 'DJANGO_ENV': 'staging'},
        ):
            with self.assertRaises(ImproperlyConfigured) as contexto:
                resolver_ambiente(environ)
            self.assertIn('DJANGO_ENV explícito', str(contexto.exception))

    def test_render_aceita_somente_homologacao_ou_production(self):
        self.assertEqual(
            resolver_ambiente({'RENDER': 'true', 'DJANGO_ENV': 'production'}),
            'production',
        )
        self.assertEqual(
            resolver_ambiente({'RENDER': 'true', 'DJANGO_ENV': 'homologacao'}),
            'homologacao',
        )

    def test_valor_desconhecido_fora_do_render_falha(self):
        with self.assertRaises(ImproperlyConfigured):
            resolver_ambiente({'DJANGO_ENV': 'staging'})


class RegrasHomologacaoExternaTests(SimpleTestCase):
    def test_debug_fica_desligado_mesmo_se_a_variavel_vier_verdadeira(self):
        self.assertFalse(debug_habilitado('homologacao', {'DEBUG': 'true'}))
        self.assertFalse(debug_habilitado('production', {'DEBUG': 'true'}))
        self.assertTrue(debug_habilitado('development', {}))

    def test_secret_key_publica_rejeita_chave_curta_ou_insegura(self):
        with self.assertRaises(ImproperlyConfigured) as contexto:
            validar_secret_key_publica('curta', 'homologacao')
        self.assertIn('homologação externa', str(contexto.exception))
        with self.assertRaises(ImproperlyConfigured) as contexto:
            validar_secret_key_publica('django-insecure-' + ('a' * 50), 'homologacao')
        self.assertIn('homologação externa', str(contexto.exception))
        with self.assertRaises(ImproperlyConfigured) as contexto:
            validar_secret_key_publica('curta', 'production')
        self.assertIn('SECRET_KEY de produção deve ser aleatória', str(contexto.exception))
        validar_secret_key_publica('curta', 'development')
        validar_secret_key_publica(CHAVE_SEGURA, 'homologacao')

    def test_banco_e_obrigatorio_postgres_e_nome_exclusivo(self):
        with self.assertRaises(ImproperlyConfigured) as contexto:
            exigir_database_url('homologacao', '')
        self.assertIn('DATABASE_URL é obrigatória na homologação externa', str(contexto.exception))
        with self.assertRaises(ImproperlyConfigured) as contexto:
            exigir_database_url('production', '')
        self.assertIn(
            'DATABASE_URL é obrigatória em produção. Use o PostgreSQL do Render.',
            str(contexto.exception),
        )
        exigir_database_url('development', '')

        with self.assertRaises(ImproperlyConfigured):
            validar_banco_homolog_externa(_banco('sqlite:///db.sqlite3'))
        with self.assertRaises(ImproperlyConfigured):
            validar_banco_homolog_externa(_banco(
                'postgres://usuario:segredo@db.example.com:5432/consultorio'
            ))
        with self.assertRaises(ImproperlyConfigured):
            validar_banco_homolog_externa(_banco(
                'postgres://usuario:segredo@db.example.com:5432/consultorio_homolog'
            ))
        externo = _banco(
            'postgres://usuario:segredo@db.example.com:5432/consultorio_homolog_externa'
        )
        validar_banco_homolog_externa(externo)
        self.assertEqual(externo['NAME'], BANCO_HOMOLOG_EXTERNA)
        self.assertTrue(ssl_banco_exigido('homologacao'))
        self.assertTrue(ssl_banco_exigido('production'))
        self.assertFalse(ssl_banco_exigido('development'))

    def test_homolog_local_e_smtp_nao_entram_na_homologacao_externa(self):
        with self.assertRaises(ImproperlyConfigured) as contexto:
            recusar_homolog_local_na_externa(
                {'HOMOLOG_LOCAL': '1'},
                'homologacao',
            )
        self.assertIn('HOMOLOG_LOCAL não pode estar ativo', str(contexto.exception))
        recusar_homolog_local_na_externa({'HOMOLOG_LOCAL': '1'}, 'development')
        self.assertFalse(exige_smtp('homologacao'))
        self.assertTrue(exige_smtp('production'))
        self.assertFalse(exige_smtp('development'))

    def test_https_proxy_e_cookies_seguros(self):
        https = configuracao_https_publica('homologacao', {})
        self.assertEqual(
            https['SECURE_PROXY_SSL_HEADER'],
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )
        self.assertTrue(https['SESSION_COOKIE_SECURE'])
        self.assertTrue(https['CSRF_COOKIE_SECURE'])
        self.assertTrue(https['SECURE_SSL_REDIRECT'])
        self.assertGreaterEqual(https['SECURE_HSTS_SECONDS'], 31_536_000)
        self.assertFalse(https['SECURE_HSTS_PRELOAD'])
        self.assertIsNone(configuracao_https_publica('development', {}))

    def test_hosts_e_csrf_proprios_sem_herdar_local_nem_producao(self):
        with self.assertRaises(ImproperlyConfigured):
            resolver_hosts_homolog_externa({})
        for host in (
            'localhost',
            '127.0.0.1',
            '192.168.1.103',
            'consultorio-a7um.onrender.com',
        ):
            with self.assertRaises(ImproperlyConfigured):
                resolver_hosts_homolog_externa({'DJANGO_ALLOWED_HOSTS': host})
        hosts = resolver_hosts_homolog_externa({
            'DJANGO_ALLOWED_HOSTS': HOST_EXTERNO,
            'RENDER_EXTERNAL_HOSTNAME': 'consultorio-homolog.onrender.com',
        })
        self.assertEqual(
            hosts,
            [HOST_EXTERNO, 'consultorio-homolog.onrender.com'],
        )
        self.assertNotIn('consultorio-a7um.onrender.com', hosts)
        self.assertNotIn('localhost', hosts)

        with self.assertRaises(ImproperlyConfigured):
            resolver_csrf_homolog_externa({})
        with self.assertRaises(ImproperlyConfigured):
            resolver_csrf_homolog_externa({'CSRF_TRUSTED_ORIGINS': 'http://homolog.example.com'})
        with self.assertRaises(ImproperlyConfigured):
            resolver_csrf_homolog_externa({
                'CSRF_TRUSTED_ORIGINS': 'https://consultorio-a7um.onrender.com',
            })
        self.assertEqual(
            resolver_csrf_homolog_externa({'CSRF_TRUSTED_ORIGINS': ORIGEM_EXTERNA}),
            [ORIGEM_EXTERNA],
        )

    def test_disco_externo_recusa_producao_e_homologacao_local(self):
        base = Path(settings.BASE_DIR)
        with self.assertRaises(ImproperlyConfigured) as contexto:
            resolver_disco_homolog_externa({}, base)
        self.assertIn('HOMOLOG_EXTERNA_DISK_PATH é obrigatório', str(contexto.exception))
        for caminho in ('/var/data', '/var/data/media', 'homolog_local', 'homolog_local/media'):
            with self.assertRaises(ImproperlyConfigured):
                resolver_disco_homolog_externa(
                    {'HOMOLOG_EXTERNA_DISK_PATH': caminho},
                    base,
                )
        with tempfile.TemporaryDirectory() as tmp:
            disco = resolver_disco_homolog_externa(
                {'HOMOLOG_EXTERNA_DISK_PATH': tmp},
                base,
            )
            self.assertEqual(disco, Path(tmp).resolve())
            self.assertFalse(str(disco).replace('\\', '/').startswith('/var/data'))
            self.assertNotEqual(disco, (base / 'homolog_local').resolve())
