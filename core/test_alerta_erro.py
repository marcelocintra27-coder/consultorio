import logging
import sys

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from consultorio.settings import lista_emails_alerta
from core.alerta_erro import AlertaErroEmailHandler, montar_alerta


def _registro(caminho='/pacientes/12/', metodo='POST', dados=None):
    request = RequestFactory().post(
        caminho + '?cpf=12345678900', data=dados or {'nome_completo': 'Maria Segredo'}
    )
    try:
        raise ValueError('CPF 12345678900 de Maria Segredo inválido')
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        'django.request', logging.ERROR, __file__, 1,
        'Internal Server Error: %s', (caminho,), exc_info,
    )
    record.request = request
    record.status_code = 500
    return record


@override_settings(
    ADMINS=['dono@exemplo.com'],
    MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}},
    ALERTA_ERRO_INTERVALO_MINUTOS=15,
)
class AlertaErroTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_envia_email_curto_sem_dados_pessoais(self):
        AlertaErroEmailHandler().emit(_registro())
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['dono@exemplo.com'])
        self.assertIn('Erro 500 em /pacientes/12/', email.subject)
        self.assertIn('ValueError', email.body)
        self.assertIn('POST /pacientes/12/', email.body)
        for dado in ('Maria Segredo', '12345678900', 'cpf='):
            self.assertNotIn(dado, email.subject)
            self.assertNotIn(dado, email.body)

    def test_mesmo_erro_nao_repete_dentro_do_intervalo(self):
        handler = AlertaErroEmailHandler()
        handler.emit(_registro())
        handler.emit(_registro())
        self.assertEqual(len(mail.outbox), 1)
        handler.emit(_registro(caminho='/agenda/'))
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(ADMINS=[])
    def test_sem_destinatario_nao_envia(self):
        AlertaErroEmailHandler().emit(_registro())
        self.assertEqual(len(mail.outbox), 0)

    def test_falha_no_aviso_nao_derruba(self):
        record = _registro()
        record.exc_info = None
        record.request = None
        AlertaErroEmailHandler().emit(record)
        assunto, corpo = montar_alerta(record)
        self.assertIn('(sem página)', assunto)

    def test_lista_emails(self):
        self.assertEqual(lista_emails_alerta(' a@x.com, b@y.com ,,'), ['a@x.com', 'b@y.com'])
        self.assertEqual(lista_emails_alerta(None), [])
