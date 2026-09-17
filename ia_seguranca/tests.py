from datetime import date, datetime, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import AssinaturaEletronica, Consulta, Paciente, RegistroEvolucaoClinica
from ia_seguranca.models import ConsentimentoIA, RegistroAuditoriaIA
from locacao.models import Dentista, PerfilUsuario, Sala


PNG_1PX = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/'
    '9K3PAAAAAElFTkSuQmCC'
)


class SegurancaVozTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Segurança Voz')
        self.dentista = Dentista.objects.create(
            nome_completo='Dra. Segurança', sala=sala
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Voz', cpf='900.000.000-01',
            data_nascimento=date(1990, 1, 1), telefone='11900000000',
        )
        self.consulta = Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 10),
            hora_inicio=time(9), hora_fim=time(10),
        )
        self.dentista_user = User.objects.create_user('dentista_voz', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user, dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_voz', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )

    def _url(self, nome):
        return f'/ia_seguranca/consultas/{self.consulta.pk}/{nome}/'

    def _payload_evolucao(self, **extra):
        dados = {
            'texto': 'Paciente orientado após o procedimento.',
            'procedimento_etapa': 'Profilaxia',
            'nome_profissional': 'Dra. Segurança',
            'cro': 'CRO-GO 12345',
            'assinatura_base64': PNG_1PX,
        }
        dados.update(extra)
        return dados

    def test_a1_secretaria_nao_transcreve_nem_grava_evolucao(self):
        self.client.force_login(self.secretaria)
        audio = SimpleUploadedFile('audio.webm', b'audio', 'audio/webm')
        resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 403)
        resposta = self.client.post(self._url('salvar-evolucao'), self._payload_evolucao())
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(RegistroEvolucaoClinica.objects.exists())

    def test_a2_exige_consentimento_valido_e_permita_dentista_vinculado(self):
        self.client.force_login(self.dentista_user)
        audio = SimpleUploadedFile('audio.webm', b'audio', 'audio/webm')
        resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 403)

        consentimento = ConsentimentoIA.objects.create(
            paciente=self.paciente, finalidade='transcricao_voz', concedido=True,
            concedido_em=timezone.make_aware(datetime(2026, 9, 1)),
        )
        registro = RegistroAuditoriaIA.objects.create(
            usuario=self.dentista_user, paciente=self.paciente,
            consulta=self.consulta, recurso='transcricao_voz', saida_sugerida='texto',
        )
        with patch('ia_seguranca.views.transcrever_e_registrar', return_value=registro) as mock:
            audio = SimpleUploadedFile('audio.webm', b'audio', 'audio/webm')
            resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 200)
        mock.assert_called_once()
        consentimento.revogado_em = timezone.now()
        consentimento.save(update_fields=['revogado_em'])
        audio = SimpleUploadedFile('audio.webm', b'audio', 'audio/webm')
        resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 403)

    def test_audio_rejeita_tipo_nao_permitido_antes_de_processar(self):
        ConsentimentoIA.objects.create(
            paciente=self.paciente, finalidade='transcricao_voz', concedido=True,
            concedido_em=timezone.now(),
        )
        self.client.force_login(self.dentista_user)
        audio = SimpleUploadedFile('arquivo.txt', b'conteudo', 'text/plain')
        with patch('ia_seguranca.views.transcrever_e_registrar') as transcrever:
            resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 400)
        transcrever.assert_not_called()

    @override_settings(IA_AUDIO_MAX_BYTES=3)
    def test_audio_rejeita_tamanho_acima_do_limite_antes_de_processar(self):
        ConsentimentoIA.objects.create(
            paciente=self.paciente, finalidade='transcricao_voz', concedido=True,
            concedido_em=timezone.now(),
        )
        self.client.force_login(self.dentista_user)
        audio = SimpleUploadedFile('audio.webm', b'1234', 'audio/webm')
        with patch('ia_seguranca.views.transcrever_e_registrar') as transcrever:
            resposta = self.client.post(self._url('transcrever'), {'audio': audio})
        self.assertEqual(resposta.status_code, 400)
        transcrever.assert_not_called()

    def test_a6_rejeita_registro_de_auditoria_de_outro_usuario(self):
        outro = User.objects.create_user('outro_dentista', password='x')
        registro = RegistroAuditoriaIA.objects.create(
            usuario=outro, paciente=self.paciente, recurso='transcricao_voz',
            consulta=self.consulta, saida_sugerida='texto',
        )
        self.client.force_login(self.dentista_user)
        resposta = self.client.post(
            self._url('salvar-evolucao'), self._payload_evolucao(registro_id=registro.pk)
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(RegistroEvolucaoClinica.objects.exists())
        registro.refresh_from_db()
        self.assertEqual(registro.decisao, 'pendente')

    def test_a8_exige_registro_de_auditoria_para_evolucao_por_voz(self):
        self.client.force_login(self.dentista_user)
        resposta = self.client.post(
            self._url('salvar-evolucao'), self._payload_evolucao()
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(RegistroEvolucaoClinica.objects.exists())

    def test_a6_rejeita_registro_de_outra_consulta_do_mesmo_paciente(self):
        outra_consulta = Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 11),
            hora_inicio=time(9), hora_fim=time(10),
        )
        registro = RegistroAuditoriaIA.objects.create(
            usuario=self.dentista_user, paciente=self.paciente,
            consulta=outra_consulta, recurso='transcricao_voz', saida_sugerida='texto',
        )
        self.client.force_login(self.dentista_user)
        resposta = self.client.post(
            self._url('salvar-evolucao'), self._payload_evolucao(registro_id=registro.pk)
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(RegistroEvolucaoClinica.objects.exists())
        registro.refresh_from_db()
        self.assertEqual(registro.decisao, 'pendente')

    def test_a8_evolucao_por_voz_usa_assinatura_e_rastreabilidade_oficiais(self):
        registro_ia = RegistroAuditoriaIA.objects.create(
            usuario=self.dentista_user, paciente=self.paciente,
            consulta=self.consulta, recurso='transcricao_voz', saida_sugerida='texto',
        )
        self.client.force_login(self.dentista_user)
        resposta = self.client.post(
            self._url('salvar-evolucao'),
            self._payload_evolucao(registro_id=registro_ia.pk),
        )
        self.assertEqual(resposta.status_code, 302)
        evolucao = RegistroEvolucaoClinica.objects.get()
        self.assertEqual(evolucao.dentista, self.dentista)
        self.assertEqual(evolucao.criado_por, self.dentista_user)
        self.assertTrue(evolucao.nome_profissional)
        self.assertTrue(evolucao.cro)
        assinatura = AssinaturaEletronica.objects.get(documento_id=evolucao.pk)
        self.assertEqual(assinatura.tipo_documento, 'evolucao')
        self.assertTrue(assinatura.hash_conteudo)
