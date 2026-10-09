"""Plano e autorização de custo abrem rascunho para paciente sem CPF (antes dava erro 500)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import FichaAutorizacaoCusto, FichaPlanoTratamento, Paciente


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DocumentosPacienteSemCPFTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin_sem_cpf', password='x'))
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Sem CPF', cpf=None,
            data_nascimento=date(1990, 1, 1), telefone='11900000000',
        )

    def test_plano_abre_rascunho_sem_cpf(self):
        resposta = self.client.post(f'/pacientes/{self.paciente.pk}/plano/novo/')
        self.assertEqual(resposta.status_code, 302)
        ficha = FichaPlanoTratamento.objects.get(paciente=self.paciente)
        self.assertEqual(ficha.cpf, '')
        self.paciente.refresh_from_db()
        self.assertIsNone(self.paciente.cpf)
        self.assertEqual(self.client.get(resposta['Location']).status_code, 200)

    def test_autorizacao_abre_rascunho_sem_cpf(self):
        resposta = self.client.post(f'/pacientes/{self.paciente.pk}/autorizacao/novo/')
        self.assertEqual(resposta.status_code, 302)
        ficha = FichaAutorizacaoCusto.objects.get(paciente=self.paciente)
        self.assertEqual(ficha.cpf, '')
        self.assertEqual(self.client.get(resposta['Location']).status_code, 200)
