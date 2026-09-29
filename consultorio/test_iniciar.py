import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class IniciarClamavTests(SimpleTestCase):
    def _executar(self, proibir_antivirus, **variaveis):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            registro = pasta / 'registro.txt'
            binario = pasta / 'bin'
            binario.mkdir()
            registro.write_text('', encoding='utf-8')
            for nome in ('python', 'gunicorn', 'freshclam', 'clamd'):
                proibido = proibir_antivirus and nome in ('freshclam', 'clamd')
                caminho = binario / nome
                caminho.write_text(
                    "#!/bin/sh\n"
                    f"printf '%s %s\\n' '{nome}' \"$*\" >> \"$REGISTRO\"\n"
                    + ("exit 99\n" if proibido else "exit 0\n"),
                    encoding='utf-8',
                )
                caminho.chmod(0o755)
            ambiente = os.environ.copy()
            for chave in ('CLAMAV_ATIVO', 'RENDER_DISK_PATH', 'PORT', 'EXAMES_CLAMD_PORT', 'CLAMAV_ESPERA_SEGUNDOS'):
                ambiente.pop(chave, None)
            ambiente['PATH'] = f'{binario}:{ambiente.get("PATH", "")}'
            ambiente['REGISTRO'] = str(registro)
            ambiente.update(variaveis)
            resultado = subprocess.run(
                ['/bin/sh', str(Path(settings.BASE_DIR) / 'iniciar.sh')],
                cwd=settings.BASE_DIR,
                env=ambiente,
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                timeout=20,
            )
            return resultado, registro.read_text(encoding='utf-8'), pasta

    def test_sem_clamav_ativo_nao_inicia_antivirus(self):
        for variaveis in ({}, {'CLAMAV_ATIVO': ''}, {'CLAMAV_ATIVO': '0'}, {'CLAMAV_ATIVO': 'true'}):
            resultado, registro, _pasta = self._executar(True, **variaveis)
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            self.assertNotIn('freshclam', registro)
            self.assertNotIn('clamd', registro)
            self.assertIn('python manage.py migrate --noinput', registro)
            self.assertIn('python manage.py collectstatic --noinput', registro)
            self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', registro)
            self.assertNotIn('ClamAV:', resultado.stdout)

    def test_clamav_ativo_ouve_somente_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            disco = Path(tmp) / 'disco'
            disco.mkdir()
            resultado, registro, _pasta = self._executar(
                False,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
                CLAMAV_ESPERA_SEGUNDOS='0',
                EXAMES_CLAMD_PORT='3310',
            )
            # O stub do freshclam desta chamada sai 0. A falha é o próximo caso.
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            conf = (disco / 'clamav' / 'clamd.conf').read_text(encoding='utf-8')
            self.assertIn(f'DatabaseDirectory {disco / "clamav"}', conf)
            self.assertIn('TCPAddr 127.0.0.1', conf)
            self.assertIn('TCPSocket 3310', conf)
            self.assertIn('StreamMaxLength 25M', conf)
            self.assertIn('ConcurrentDatabaseReload no', conf)
            self.assertNotIn('0.0.0.0', conf)
            self.assertNotIn('LocalSocket', conf)
            daemon = (disco / 'clamav' / 'freshclam.conf').read_text(encoding='utf-8')
            uma_vez = (disco / 'clamav' / 'freshclam-uma-vez.conf').read_text(encoding='utf-8')
            self.assertIn('Checks 12', daemon)
            self.assertIn(f'DatabaseDirectory {disco / "clamav"}', daemon)
            self.assertIn('NotifyClamd ', daemon)
            self.assertNotIn('NotifyClamd', uma_vez)
            self.assertLess(registro.index('freshclam '), registro.index('clamd '))
            self.assertLess(registro.index('clamd '), registro.rindex('freshclam '))
            self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', registro)
            self.assertIn('--config-file=', registro)
            self.assertIn('ClamAV: clamd pronto.', resultado.stdout)

    def test_freshclam_falha_com_e_sem_assinatura_e_o_sistema_sobe(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            registro = pasta / 'registro.txt'
            binario = pasta / 'bin'
            binario.mkdir()
            for nome, codigo in (('python', 0), ('gunicorn', 0), ('freshclam', 1), ('clamd', 0)):
                caminho = binario / nome
                caminho.write_text(
                    "#!/bin/sh\n"
                    f"printf '%s %s\\n' '{nome}' \"$*\" >> \"$REGISTRO\"\n"
                    f"exit {codigo}\n",
                    encoding='utf-8',
                )
                caminho.chmod(0o755)

            def rodar(disco):
                registro.write_text('', encoding='utf-8')
                ambiente = os.environ.copy()
                ambiente.pop('PORT', None)
                ambiente['PATH'] = f'{binario}:{ambiente.get("PATH", "")}'
                ambiente['REGISTRO'] = str(registro)
                ambiente['CLAMAV_ATIVO'] = '1'
                ambiente['RENDER_DISK_PATH'] = str(disco)
                ambiente['CLAMAV_ESPERA_SEGUNDOS'] = '0'
                return subprocess.run(
                    ['/bin/sh', str(Path(settings.BASE_DIR) / 'iniciar.sh')],
                    cwd=settings.BASE_DIR,
                    env=ambiente,
                    capture_output=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=20,
                )

            vazio = Path(tmp) / 'vazio'
            sem = rodar(vazio)
            self.assertEqual(sem.returncode, 0, sem.stderr)
            self.assertIn('ainda não há assinaturas no disco', sem.stdout)
            self.assertIn('gunicorn consultorio.wsgi:application', registro.read_text(encoding='utf-8'))

            com = Path(tmp) / 'com'
            (com / 'clamav').mkdir(parents=True)
            (com / 'clamav' / 'main.cld').write_bytes(b'x')
            com_resultado = rodar(com)
            self.assertEqual(com_resultado.returncode, 0, com_resultado.stderr)
            self.assertIn('já existem assinaturas no disco', com_resultado.stdout)
            self.assertIn('gunicorn consultorio.wsgi:application', registro.read_text(encoding='utf-8'))
