from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from exames.config import limite
from exames.management.commands import verificar_antivirus


class VerificarAntivirusTests(SimpleTestCase):
    def test_respondendo_informa_data_sem_enviar_arquivo(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.side_effect = [
            b'PONG\0',
            b'ClamAV 1.4.3/27000/Tue Sep 29 08:00:00 2026\0',
        ]
        saida = StringIO()
        with patch('exames.management.commands.verificar_antivirus.socket.create_connection', return_value=sock) as conn:
            call_command('verificar_antivirus', stdout=saida)
        texto = saida.getvalue()
        self.assertIn('Antivírus: respondendo.', texto)
        self.assertNotIn('Antivírus: não respondendo.', texto)
        self.assertIn('Data das assinaturas: 29/09/2026.', texto)
        self.assertEqual(conn.call_args.args[0], ('127.0.0.1', limite('EXAMES_CLAMD_PORT', 3310)))
        enviados = [chamada.args[0] for chamada in sock.sendall.call_args_list]
        self.assertEqual(enviados, [b'zPING\0', b'zVERSION\0'])
        self.assertNotIn(b'zINSTREAM\0', enviados)

    def test_nao_respondendo(self):
        saida = StringIO()
        with patch(
            'exames.management.commands.verificar_antivirus.socket.create_connection',
            side_effect=OSError('recusado'),
        ):
            call_command('verificar_antivirus', stdout=saida)
        texto = saida.getvalue()
        self.assertIn('Antivírus: não respondendo.', texto)
        self.assertNotIn('Antivírus: respondendo.', texto)
        self.assertNotIn('Data das assinaturas', texto)

    def test_resposta_estranha_conta_como_nao_respondendo(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.return_value = b'ERRO\0'
        saida = StringIO()
        with patch('exames.management.commands.verificar_antivirus.socket.create_connection', return_value=sock):
            call_command('verificar_antivirus', stdout=saida)
        self.assertIn('Antivírus: não respondendo.', saida.getvalue())
        self.assertEqual(verificar_antivirus.data_das_assinaturas('sem data'), '')
