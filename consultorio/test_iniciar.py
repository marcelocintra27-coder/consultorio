import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class IniciarClamavTests(SimpleTestCase):
    def _ambiente(self, pasta, path=None, **variaveis):
        registro = pasta / 'registro.txt'
        registro.write_text('', encoding='utf-8')
        binario = pasta / 'bin'
        binario.mkdir()
        ambiente = os.environ.copy()
        for chave in ('CLAMAV_ATIVO', 'RENDER_DISK_PATH', 'PORT', 'EXAMES_CLAMD_PORT'):
            ambiente.pop(chave, None)
        ambiente['PATH'] = path or f'{binario}:{ambiente.get("PATH", "")}'
        ambiente['REGISTRO'] = str(registro)
        ambiente.update(variaveis)
        return ambiente, registro, binario

    def _comando(self, binario, nome, corpo):
        caminho = binario / nome
        caminho.write_text(corpo, encoding='utf-8')
        caminho.chmod(0o755)

    def _stubs_aplicacao(self, binario):
        for nome in ('python', 'gunicorn'):
            self._comando(
                binario,
                nome,
                "#!/bin/sh\n"
                f"printf '%s %s\\n' '{nome}' \"$*\" >> \"$REGISTRO\"\n"
                "exit 0\n",
            )

    def _stub_runuser(self, binario):
        self._comando(
            binario,
            'runuser',
            "#!/bin/sh\n"
            "printf '%s %s\\n' runuser \"$*\" >> \"$REGISTRO\"\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = -- ]; then shift; exec \"$@\"; fi\n"
            "  shift\n"
            "done\n"
            "exit 99\n",
        )

    def _stub_setpriv(self, binario):
        self._comando(
            binario,
            'setpriv',
            "#!/bin/sh\n"
            "printf '%s %s\\n' setpriv \"$*\" >> \"$REGISTRO\"\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = -- ]; then shift; exec \"$@\"; fi\n"
            "  shift\n"
            "done\n"
            "exit 99\n",
        )

    def _stubs_antivirus(self, binario, corpo_freshclam, corpo_clamd, ferramenta='runuser'):
        self._comando(binario, 'freshclam', corpo_freshclam)
        self._comando(binario, 'clamd', corpo_clamd)
        self._comando(
            binario,
            'id',
            "#!/bin/sh\n"
            "if [ \"$1\" = clamav ]; then exit 0; fi\n"
            "exec /usr/bin/id \"$@\"\n",
        )
        self._comando(
            binario,
            'chown',
            "#!/bin/sh\n"
            "printf '%s %s\\n' chown \"$*\" >> \"$REGISTRO\"\n"
            "exit 0\n",
        )
        if ferramenta == 'runuser':
            self._stub_runuser(binario)
        elif ferramenta == 'setpriv':
            self._stub_setpriv(binario)

    def _abrir(self, ambiente):
        return subprocess.Popen(
            ['/bin/sh', str(Path(settings.BASE_DIR) / 'iniciar.sh')],
            cwd=settings.BASE_DIR,
            env=ambiente,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )

    def _matar_com_registro(self, registro):
        marca = f'REGISTRO={registro}'.encode()
        for entrada in Path('/proc').iterdir():
            if not entrada.name.isdigit():
                continue
            try:
                dados = (entrada / 'environ').read_bytes()
            except OSError:
                continue
            if marca in dados:
                try:
                    os.kill(int(entrada.name), signal.SIGKILL)
                except OSError:
                    pass

    def _encerrar(self, proc, registro=None):
        for sinal in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sinal)
            except ProcessLookupError:
                pass
        if registro is not None:
            self._matar_com_registro(registro)
        try:
            return proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if registro is not None:
                self._matar_com_registro(registro)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return proc.communicate(timeout=5)

    def _esperar_registro(self, registro, trecho, prazo=5):
        limite = time.monotonic() + prazo
        while time.monotonic() < limite:
            texto = registro.read_text(encoding='utf-8')
            if trecho in texto:
                return texto
            time.sleep(0.05)
        return registro.read_text(encoding='utf-8')

    def test_sem_clamav_ativo_nao_inicia_antivirus(self):
        script = (Path(settings.BASE_DIR) / 'iniciar.sh').read_text(encoding='utf-8')
        self.assertIn('timeout --kill-after=30 900 runuser -u clamav -- freshclam', script)
        self.assertIn('timeout --kill-after=30 900 setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- freshclam', script)
        self.assertIn('runuser -u clamav -- "$@"', script)
        self.assertIn('setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- "$@"', script)
        self.assertIn('sleep 60', script)
        self.assertIn('User clamav', script)
        self.assertIn('chmod 750', script)
        self.assertIn('chmod 640', script)
        self.assertNotIn('usuário atual', script)
        for variaveis in ({}, {'CLAMAV_ATIVO': ''}, {'CLAMAV_ATIVO': '0'}, {'CLAMAV_ATIVO': 'true'}):
            with tempfile.TemporaryDirectory() as tmp:
                ambiente, registro, binario = self._ambiente(Path(tmp), **variaveis)
                self._stubs_aplicacao(binario)
                self._stubs_antivirus(
                    binario,
                    "#!/bin/sh\nprintf '%s\\n' proibido-freshclam >> \"$REGISTRO\"\nexit 99\n",
                    "#!/bin/sh\nprintf '%s\\n' proibido-clamd >> \"$REGISTRO\"\nexit 99\n",
                )
                proc = self._abrir(ambiente)
                try:
                    proc.wait(timeout=8)
                finally:
                    saida, erro = self._encerrar(proc, registro)
                self.assertEqual(proc.returncode, 0, erro)
                texto = registro.read_text(encoding='utf-8')
                self.assertNotIn('freshclam', texto)
                self.assertNotIn('clamd', texto)
                self.assertNotIn('chown', texto)
                self.assertIn('python manage.py migrate --noinput', texto)
                self.assertIn('python manage.py collectstatic --noinput', texto)
                self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
                self.assertNotIn('ClamAV:', saida)

    def test_gunicorn_sobe_mesmo_se_freshclam_e_clamd_falham(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
                EXAMES_CLAMD_PORT='3310',
            )
            self._stubs_aplicacao(binario)
            self._stubs_antivirus(
                binario,
                "#!/bin/sh\nprintf '%s %s\\n' freshclam \"$*\" >> \"$REGISTRO\"\nexit 1\n",
                "#!/bin/sh\nprintf '%s %s\\n' clamd \"$*\" >> \"$REGISTRO\"\nexit 1\n",
            )
            inicio = time.monotonic()
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                self.assertLess(time.monotonic() - inicio, 8)
                self.assertEqual(proc.returncode, 0)
                texto = self._esperar_registro(registro, 'runuser -u clamav -- clamd ')
                self.assertGreaterEqual(texto.count('runuser -u clamav -- freshclam '), 2)
                self.assertIn('runuser -u clamav -- clamd ', texto)
                self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
                self.assertIn('chown clamav:clamav', texto)
            finally:
                saida, _erro = self._encerrar(proc, registro)
            self.assertIn('a atualização falhou e ainda não há assinaturas no disco', saida)

    def test_gunicorn_nao_espera_freshclam_lento(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
            )
            self._stubs_aplicacao(binario)
            self._stubs_antivirus(
                binario,
                "#!/bin/sh\nprintf '%s %s\\n' freshclam \"$*\" >> \"$REGISTRO\"\nsleep 30\nexit 1\n",
                "#!/bin/sh\nprintf '%s %s\\n' clamd \"$*\" >> \"$REGISTRO\"\nexit 1\n",
            )
            inicio = time.monotonic()
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                self.assertLess(time.monotonic() - inicio, 8)
                self.assertEqual(proc.returncode, 0)
                imediato = registro.read_text(encoding='utf-8')
                self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', imediato)
                texto = self._esperar_registro(registro, 'runuser -u clamav -- freshclam ')
                self.assertIn('runuser -u clamav -- freshclam ', texto)
            finally:
                self._encerrar(proc, registro)

    def test_sem_usuario_clamav_nao_inicia_antivirus(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
            )
            self._stubs_aplicacao(binario)
            self._comando(
                binario,
                'freshclam',
                "#!/bin/sh\nprintf '%s\\n' proibido-freshclam >> \"$REGISTRO\"\nexit 99\n",
            )
            self._comando(
                binario,
                'clamd',
                "#!/bin/sh\nprintf '%s\\n' proibido-clamd >> \"$REGISTRO\"\nexit 99\n",
            )
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                time.sleep(0.4)
            finally:
                saida, _erro = self._encerrar(proc, registro)
            texto = registro.read_text(encoding='utf-8')
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn('proibido-freshclam', texto)
            self.assertNotIn('proibido-clamd', texto)
            self.assertNotIn('chown', texto)
            self.assertNotIn('runuser', texto)
            self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
            self.assertIn('usuário clamav não encontrado', saida)
            self.assertFalse((disco / 'clamav').exists())

    def test_config_escuta_somente_loopback_e_permissoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
                EXAMES_CLAMD_PORT='3310',
            )
            self._stubs_aplicacao(binario)
            self._stubs_antivirus(
                binario,
                "#!/bin/sh\nprintf '%s %s\\n' freshclam \"$*\" >> \"$REGISTRO\"\nexit 0\n",
                "#!/bin/sh\nprintf '%s %s\\n' clamd \"$*\" >> \"$REGISTRO\"\nexit 0\n",
            )
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                self.assertEqual(proc.returncode, 0)
                self._esperar_registro(registro, 'runuser -u clamav -- clamd ')
                conf_path = disco / 'clamav' / 'clamd.conf'
                prazo = time.monotonic() + 5
                while time.monotonic() < prazo and not conf_path.exists():
                    time.sleep(0.05)
                conf = conf_path.read_text(encoding='utf-8')
                self.assertIn(f'DatabaseDirectory {disco / "clamav"}', conf)
                self.assertIn('TCPAddr 127.0.0.1', conf)
                self.assertIn('TCPSocket 3310', conf)
                self.assertIn('StreamMaxLength 25M', conf)
                self.assertIn('ConcurrentDatabaseReload no', conf)
                self.assertIn('User clamav', conf)
                self.assertNotIn('0.0.0.0', conf)
                self.assertNotIn('LocalSocket', conf)
                daemon = (disco / 'clamav' / 'freshclam.conf').read_text(encoding='utf-8')
                uma_vez = (disco / 'clamav' / 'freshclam-uma-vez.conf').read_text(encoding='utf-8')
                self.assertIn('Checks 12', daemon)
                self.assertIn('DatabaseOwner clamav', daemon)
                self.assertIn('NotifyClamd ', daemon)
                self.assertNotIn('NotifyClamd', uma_vez)
                self.assertEqual((disco / 'clamav').stat().st_mode & 0o777, 0o750)
                for arquivo in (conf_path, disco / 'clamav' / 'freshclam.conf', disco / 'clamav' / 'freshclam-uma-vez.conf'):
                    self.assertEqual(arquivo.stat().st_mode & 0o777, 0o640)
            finally:
                self._encerrar(proc, registro)

    def test_configuracao_incompleta_nao_inicia_clamd_e_gunicorn_sobe(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
            )
            self._stubs_aplicacao(binario)
            self._stubs_antivirus(
                binario,
                "#!/bin/sh\nprintf '%s\\n' proibido-freshclam >> \"$REGISTRO\"\nexit 99\n",
                "#!/bin/sh\nprintf '%s\\n' proibido-clamd >> \"$REGISTRO\"\nexit 99\n",
            )
            self._comando(
                binario,
                'mv',
                "#!/bin/sh\n"
                "case \"$2\" in\n"
                "  */clamd.conf)\n"
                "    /usr/bin/grep -v '^TCPAddr ' \"$1\" > \"$2\"\n"
                "    rm -f \"$1\"\n"
                "    exit 0\n"
                "    ;;\n"
                "esac\n"
                "exec /usr/bin/mv \"$@\"\n",
            )
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                self.assertEqual(proc.returncode, 0)
                time.sleep(0.3)
            finally:
                saida, _erro = self._encerrar(proc, registro)
            texto = registro.read_text(encoding='utf-8')
            self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
            self.assertNotIn('runuser', texto)
            self.assertNotIn('proibido-clamd', texto)
            self.assertNotIn('proibido-freshclam', texto)
            self.assertFalse((disco / 'clamav' / 'clamd.conf').exists())
            self.assertIn('configuração incompleta', saida)
            self.assertIn('TCPAddr 127.0.0.1', saida)

    def test_setpriv_quando_runuser_nao_existe(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            binario_previo = pasta / 'bin'
            ambiente, registro, binario = self._ambiente(
                pasta,
                path=f'{binario_previo}:/usr/bin:/bin',
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
            )
            self.assertEqual(binario, binario_previo)
            self._stubs_aplicacao(binario)
            self._stubs_antivirus(
                binario,
                "#!/bin/sh\nprintf '%s %s\\n' freshclam \"$*\" >> \"$REGISTRO\"\nexit 0\n",
                "#!/bin/sh\nprintf '%s %s\\n' clamd \"$*\" >> \"$REGISTRO\"\nexit 0\n",
                ferramenta='setpriv',
            )
            self.assertFalse((binario / 'runuser').exists())
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                self.assertEqual(proc.returncode, 0)
                texto = self._esperar_registro(
                    registro,
                    'setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- clamd ',
                )
                self.assertGreaterEqual(
                    texto.count('setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- freshclam '),
                    2,
                )
                self.assertNotIn('runuser', texto)
                self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
            finally:
                self._encerrar(proc, registro)

    def test_sem_runuser_nem_setpriv_nao_inicia_antivirus(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            disco = pasta / 'disco'
            disco.mkdir()
            ambiente, registro, binario = self._ambiente(
                pasta,
                path='PENDENTE',
                CLAMAV_ATIVO='1',
                RENDER_DISK_PATH=str(disco),
            )
            self._stubs_aplicacao(binario)
            self._comando(
                binario,
                'id',
                "#!/bin/sh\n"
                "if [ \"$1\" = clamav ]; then exit 0; fi\n"
                "exit 1\n",
            )
            self._comando(
                binario,
                'freshclam',
                "#!/bin/sh\nprintf '%s\\n' proibido-freshclam >> \"$REGISTRO\"\nexit 99\n",
            )
            self._comando(
                binario,
                'clamd',
                "#!/bin/sh\nprintf '%s\\n' proibido-clamd >> \"$REGISTRO\"\nexit 99\n",
            )
            for nome in ('timeout', 'chmod', 'chown', 'mkdir', 'mv', 'find', 'grep', 'sleep', 'cat', 'rm'):
                origem = shutil.which(nome)
                destino = binario / nome
                if origem and not destino.exists():
                    destino.symlink_to(origem)
            ambiente['PATH'] = str(binario)
            proc = self._abrir(ambiente)
            try:
                proc.wait(timeout=8)
                time.sleep(0.3)
            finally:
                saida, _erro = self._encerrar(proc, registro)
            texto = registro.read_text(encoding='utf-8')
            self.assertEqual(proc.returncode, 0)
            self.assertIn('gunicorn consultorio.wsgi:application --bind 0.0.0.0:8000', texto)
            self.assertNotIn('proibido-freshclam', texto)
            self.assertNotIn('proibido-clamd', texto)
            self.assertIn('nem runuser nem setpriv foram encontrados', saida)
            self.assertFalse((disco / 'clamav').exists())
