from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from exames.config import limite
from exames.management.commands import verificar_antivirus


def _socket(resposta):
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.recv.return_value = resposta
    return sock


class VerificarAntivirusTests(SimpleTestCase):
    def test_respondendo_informa_data_sem_enviar_arquivo(self):
        sock_ping = _socket(b'PONG\0')
        sock_versao = _socket(b'ClamAV 1.4.3/27000/Tue Sep 29 08:00:00 2026\0')
        saida = StringIO()
        with patch(
            'exames.management.commands.verificar_antivirus.socket.create_connection',
            side_effect=[sock_ping, sock_versao],
        ) as conn:
            call_command('verificar_antivirus', stdout=saida)
        texto = saida.getvalue()
        self.assertIn('Antivírus: respondendo.', texto)
        self.assertNotIn('Antivírus: não respondendo.', texto)
        self.assertIn('Data das assinaturas: 29/09/2026.', texto)
        self.assertEqual(conn.call_count, 2)
        endereco = ('127.0.0.1', limite('EXAMES_CLAMD_PORT', 3310))
        self.assertEqual(conn.call_args_list[0].args[0], endereco)
        self.assertEqual(conn.call_args_list[1].args[0], endereco)
        self.assertEqual([c.args[0] for c in sock_ping.sendall.call_args_list], [b'zPING\0'])
        self.assertEqual([c.args[0] for c in sock_versao.sendall.call_args_list], [b'zVERSION\0'])

    def test_pong_com_version_falhando_informa_data_ausente(self):
        sock_ping = _socket(b'PONG\0')
        saida = StringIO()
        with patch(
            'exames.management.commands.verificar_antivirus.socket.create_connection',
            side_effect=[sock_ping, OSError('version indisponível')],
        ) as conn:
            call_command('verificar_antivirus', stdout=saida)
        texto = saida.getvalue()
        self.assertEqual(conn.call_count, 2)
        self.assertIn('Antivírus: respondendo.', texto)
        self.assertNotIn('Antivírus: não respondendo.', texto)
        self.assertIn('Data das assinaturas: não informada.', texto)
        self.assertEqual([c.args[0] for c in sock_ping.sendall.call_args_list], [b'zPING\0'])

    def test_nao_respondendo(self):
        saida = StringIO()
        with patch(
            'exames.management.commands.verificar_antivirus.socket.create_connection',
            side_effect=OSError('recusado'),
        ) as conn:
            call_command('verificar_antivirus', stdout=saida)
        texto = saida.getvalue()
        self.assertEqual(conn.call_count, 1)
        self.assertIn('Antivírus: não respondendo.', texto)
        self.assertNotIn('Antivírus: respondendo.', texto)
        self.assertNotIn('Data das assinaturas', texto)

    def test_resposta_estranha_conta_como_nao_respondendo(self):
        sock = _socket(b'ERRO\0')
        saida = StringIO()
        with patch(
            'exames.management.commands.verificar_antivirus.socket.create_connection',
            side_effect=[sock],
        ) as conn:
            call_command('verificar_antivirus', stdout=saida)
        self.assertEqual(conn.call_count, 1)
        self.assertIn('Antivírus: não respondendo.', saida.getvalue())
        self.assertEqual(verificar_antivirus.data_das_assinaturas('sem data'), '')
