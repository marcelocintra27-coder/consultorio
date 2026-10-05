import hashlib
import hmac
import json
import os
from datetime import date, time
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import AuditoriaConsulta, Consulta, MensagemWhatsApp, Paciente
from .whatsapp import ErroWhatsApp, preparar_lembretes, registrar_resposta, texto_lembrete


class LembreteWhatsAppTests(TestCase):
    HOJE = date(2026, 10, 5)
    AMANHA = date(2026, 10, 6)

    def setUp(self):
        self.ambiente = patch.dict(os.environ, {'WHATSAPP_MODO': 'simulado'})
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

        sala = Sala.objects.create(nome='Sala WhatsApp')
        self.dentista = Dentista.objects.create(
            nome_completo='Dra. Helena Costa', sala=sala,
        )
        self.paciente = self.criar_paciente(
            'Maria Silva', '11988887777', True, '801.000.000-01',
        )
        self.confirmada = self.criar_paciente(
            'João Pereira', '(11) 97777-6666', True, '801.000.000-02',
        )
        self.sem_autorizacao = self.criar_paciente(
            'Ana Lima', '11966665555', False, '801.000.000-03',
        )
        self.sem_whatsapp = self.criar_paciente(
            'Carlos Dias', '', True, '801.000.000-04',
        )
        self.telefone_invalido = self.criar_paciente(
            'Paula Nunes', '12345', True, '801.000.000-05',
        )
        self.consulta = self.criar_consulta(self.paciente, self.AMANHA)
        self.consulta_confirmada = self.criar_consulta(
            self.confirmada, self.AMANHA, status=Consulta.Status.CONFIRMADA,
            hora_inicio=time(9, 0), hora_fim=time(9, 30),
        )
        self.criar_consulta(self.paciente, self.HOJE, hora_inicio=time(10), hora_fim=time(11))
        self.criar_consulta(
            self.paciente, date(2026, 10, 7), hora_inicio=time(11), hora_fim=time(12),
        )
        self.criar_consulta(
            self.paciente, self.AMANHA, status=Consulta.Status.CANCELADA,
            hora_inicio=time(12), hora_fim=time(13),
        )
        self.criar_consulta(
            self.paciente, self.AMANHA, status=Consulta.Status.REALIZADA,
            hora_inicio=time(13), hora_fim=time(14),
        )
        self.criar_consulta(
            self.paciente, self.AMANHA, status=Consulta.Status.PRESENTE,
            hora_inicio=time(14), hora_fim=time(15),
        )
        self.criar_consulta(self.sem_autorizacao, self.AMANHA, hora_inicio=time(15), hora_fim=time(16))
        self.criar_consulta(self.sem_whatsapp, self.AMANHA, hora_inicio=time(16), hora_fim=time(17))
        self.criar_consulta(self.telefone_invalido, self.AMANHA, hora_inicio=time(17), hora_fim=time(18))

        self.secretaria = User.objects.create_user('secretaria_wa', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.dentista_user = User.objects.create_user('dentista_wa', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=self.dentista,
        )
        self.admin = User.objects.create_superuser('admin_wa', 'wa@example.com', 'x')

    def criar_paciente(self, nome, whatsapp, aceita, cpf):
        return Paciente.objects.create(
            nome_completo=nome,
            cpf=cpf,
            data_nascimento=date(1990, 5, 12),
            telefone='1133334444',
            whatsapp=whatsapp,
            aceita_lembretes_whatsapp=aceita,
            endereco='Rua das Flores 100',
            observacoes='restauração no valor de R$ 500',
        )

    def criar_consulta(self, paciente, dia, status=Consulta.Status.AGENDADA, **extra):
        dados = dict(
            paciente=paciente,
            dentista=self.dentista,
            data=dia,
            hora_inicio=time(8, 30),
            hora_fim=time(9, 0),
            status=status,
            observacoes='procedimento de canal e diagnóstico de cárie',
        )
        dados.update(extra)
        return Consulta.objects.create(**dados)

    def preparar_amanha(self):
        with patch('core.whatsapp.timezone.localdate', return_value=self.HOJE):
            return preparar_lembretes()

    def enviadas(self):
        return MensagemWhatsApp.objects.filter(direcao=MensagemWhatsApp.Direcao.ENVIADA)

    def test_autorizacao_comeca_desligada_e_grava_a_data(self):
        paciente = Paciente.objects.create(
            nome_completo='Sem escolha',
            cpf='801.000.000-09',
            data_nascimento=date(1991, 1, 1),
            telefone='11900000000',
        )
        self.assertFalse(paciente.aceita_lembretes_whatsapp)
        self.assertIsNone(paciente.aceita_lembretes_whatsapp_em)
        self.assertIsNotNone(self.paciente.aceita_lembretes_whatsapp_em)

    def test_so_gera_lembrete_elegivel_e_nao_duplica(self):
        self.assertEqual(self.preparar_amanha(), 2)
        self.assertEqual(self.enviadas().count(), 2)
        consultas = set(self.enviadas().values_list('consulta_id', flat=True))
        self.assertEqual(consultas, {self.consulta.pk, self.consulta_confirmada.pk})
        mensagem = self.enviadas().get(consulta=self.consulta)
        self.assertEqual(mensagem.status, MensagemWhatsApp.Status.SIMULADA)
        self.assertEqual(mensagem.telefone, '+5511988887777')
        self.assertEqual(mensagem.paciente, self.paciente)
        self.assertEqual(
            self.enviadas().get(consulta=self.consulta_confirmada).telefone,
            '+5511977776666',
        )
        self.assertEqual(self.preparar_amanha(), 0)
        self.assertEqual(self.enviadas().count(), 2)

    def test_texto_do_lembrete_nao_leva_conteudo_clinico(self):
        self.preparar_amanha()
        mensagem = self.enviadas().get(consulta=self.consulta)
        esperado = (
            'Olá, Maria! Lembramos da sua consulta na Clínica Odontológica 90 amanhã, '
            '06/10, às 08:30, com Dra. Helena Costa. '
            'Responda 1 para CONFIRMAR ou 2 para DESMARCAR. Esta é uma mensagem automática.'
        )
        self.assertEqual(mensagem.texto, esperado)
        self.assertEqual(texto_lembrete(self.consulta), esperado)
        proibido = (
            'canal', 'cárie', 'diagnóstico', 'restauração', 'R$', '500',
            'Rua das Flores', 'procedimento',
        )
        for termo in proibido:
            self.assertNotIn(termo, mensagem.texto)

    def test_resposta_1_confirma_2_cancela_e_outra_pede_atencao(self):
        self.preparar_amanha()
        registrar_resposta('+55 (11) 98888-7777', ' 1 ')
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.CONFIRMADA)
        auditoria = self.consulta.auditorias.get()
        self.assertIsNone(auditoria.usuario_id)
        self.assertIn('agendada -> confirmada', auditoria.descricao)
        self.assertIn('origem: resposta WhatsApp', auditoria.descricao)
        resposta = MensagemWhatsApp.objects.get(
            consulta=self.consulta, direcao=MensagemWhatsApp.Direcao.RECEBIDA,
        )
        self.assertEqual(resposta.acao, MensagemWhatsApp.Acao.CONFIRMOU)
        self.assertEqual(resposta.status, MensagemWhatsApp.Status.RECEBIDA)
        self.assertEqual(resposta.lembrete.consulta_id, self.consulta.pk)

        registrar_resposta('11977776666', '2')
        self.consulta_confirmada.refresh_from_db()
        self.assertEqual(self.consulta_confirmada.status, Consulta.Status.CANCELADA)
        self.assertIn(
            'origem: resposta WhatsApp',
            self.consulta_confirmada.auditorias.get().descricao,
        )
        self.assertEqual(
            MensagemWhatsApp.objects.get(consulta=self.consulta_confirmada, direcao='recebida').acao,
            MensagemWhatsApp.Acao.DESMARCOU,
        )

        outra = self.criar_consulta(
            self.criar_paciente('Lia Souza', '11955554444', True, '801.000.000-06'),
            self.AMANHA, hora_inicio=time(18), hora_fim=time(19),
        )
        with patch('core.whatsapp.timezone.localdate', return_value=self.HOJE):
            self.assertEqual(preparar_lembretes(), 1)
        antes = outra.status
        registrar_resposta('11955554444', '1.')
        outra.refresh_from_db()
        self.assertEqual(outra.status, antes)
        self.assertFalse(outra.auditorias.exists())
        self.assertEqual(
            MensagemWhatsApp.objects.get(consulta=outra, direcao='recebida').acao,
            MensagemWhatsApp.Acao.PRECISA_ATENCAO,
        )

    def test_resposta_vai_para_o_lembrete_mais_recente_do_telefone(self):
        self.preparar_amanha()
        recente = self.criar_consulta(
            self.paciente, self.AMANHA, hora_inicio=time(19), hora_fim=time(20),
        )
        with patch('core.whatsapp.timezone.localdate', return_value=self.HOJE):
            preparar_lembretes()
        registrar_resposta(self.paciente.whatsapp, '2')
        self.consulta.refresh_from_db()
        recente.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.AGENDADA)
        self.assertEqual(recente.status, Consulta.Status.CANCELADA)
        self.assertEqual(recente.auditorias.get().usuario_id, None)

    def _post_webhook(self, payload, secret='segredo-teste', assinatura=None):
        corpo = json.dumps(payload).encode('utf-8')
        if assinatura is None:
            digest = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
            assinatura = f'sha256={digest}'
        with patch.dict(os.environ, {'WHATSAPP_APP_SECRET': secret}):
            return self.client.post(
                reverse('core:whatsapp_webhook'),
                data=corpo,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=assinatura,
            )

    def test_webhook_recusa_assinatura_invalida_e_aceita_valida(self):
        self.preparar_amanha()
        payload = {
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '5511988887777',
                            'id': 'wamid.1',
                            'type': 'text',
                            'text': {'body': '1'},
                        }],
                    },
                }],
            }],
        }
        recusa = self._post_webhook(payload, assinatura='sha256=invalida')
        self.assertEqual(recusa.status_code, 403)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.AGENDADA)
        self.assertFalse(
            MensagemWhatsApp.objects.filter(direcao=MensagemWhatsApp.Direcao.RECEBIDA).exists()
        )

        sem_cabecalho = self.client.post(
            reverse('core:whatsapp_webhook'),
            data=b'{}',
            content_type='application/json',
        )
        self.assertEqual(sem_cabecalho.status_code, 403)

        aceita = self._post_webhook(payload)
        self.assertEqual(aceita.status_code, 200)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.CONFIRMADA)
        self.assertEqual(
            MensagemWhatsApp.objects.filter(id_externo='wamid.1').count(),
            1,
        )
        repetida = self._post_webhook(payload)
        self.assertEqual(repetida.status_code, 200)
        self.assertEqual(
            MensagemWhatsApp.objects.filter(id_externo='wamid.1').count(),
            1,
        )
        self.assertEqual(self.consulta.auditorias.count(), 1)

    def test_webhook_verifica_o_token_do_get(self):
        url = reverse('core:whatsapp_webhook')
        with patch.dict(os.environ, {'WHATSAPP_VERIFY_TOKEN': 'token-certo'}):
            certo = self.client.get(url, {
                'hub.mode': 'subscribe',
                'hub.verify_token': 'token-certo',
                'hub.challenge': 'desafio-99',
            })
            errado = self.client.get(url, {
                'hub.mode': 'subscribe',
                'hub.verify_token': 'token-errado',
                'hub.challenge': 'desafio-99',
            })
        self.assertEqual(certo.status_code, 200)
        self.assertEqual(certo.content, b'desafio-99')
        self.assertNotEqual(certo.status_code, 302)
        self.assertEqual(errado.status_code, 403)

    def test_modo_meta_sem_variaveis_nao_envia(self):
        with patch.dict(os.environ, {
            'WHATSAPP_MODO': 'meta',
            'WHATSAPP_TOKEN': '',
            'WHATSAPP_PHONE_NUMBER_ID': '',
        }):
            with self.assertRaises(CommandError) as erro:
                call_command('preparar_lembretes', '--data', '2026-10-06')
        self.assertIn('WHATSAPP_TOKEN', str(erro.exception))
        self.assertIn('WHATSAPP_PHONE_NUMBER_ID', str(erro.exception))
        self.assertIn('Nenhuma mensagem foi enviada', str(erro.exception))
        self.assertEqual(MensagemWhatsApp.objects.count(), 0)

        with patch.dict(os.environ, {
            'WHATSAPP_MODO': 'meta',
            'WHATSAPP_TOKEN': 'token-de-teste',
            'WHATSAPP_PHONE_NUMBER_ID': '123456',
        }):
            with patch('urllib.request.urlopen') as abrir:
                with self.assertRaises(ErroWhatsApp) as erro_api:
                    preparar_lembretes(self.AMANHA)
                abrir.assert_not_called()
        self.assertIn('Nenhuma mensagem foi enviada', str(erro_api.exception))
        self.assertEqual(MensagemWhatsApp.objects.count(), 0)

    def test_comando_prepara_a_data_informada(self):
        saida = StringIO()
        call_command('preparar_lembretes', '--data', '2026-10-06', stdout=saida)
        self.assertIn('Lembretes preparados: 2.', saida.getvalue())
        self.assertEqual(self.enviadas().count(), 2)

    def test_permissoes_da_tela_do_menu_e_da_simulacao(self):
        self.preparar_amanha()
        lista = reverse('core:listar_lembretes_whatsapp') + '?data=2026-10-06'
        agenda = reverse('core:listar_consultas')
        inicio = reverse('core:inicio')
        simular = reverse('core:simular_resposta_whatsapp', args=[self.enviadas().get(consulta=self.consulta).pk])

        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(lista).status_code, 403)
        self.assertNotContains(self.client.get(inicio), 'Lembretes WhatsApp')
        self.assertNotContains(self.client.get(agenda), 'Preparar lembretes de amanhã')
        self.assertEqual(self.client.post(simular, {'texto': '1'}).status_code, 403)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.AGENDADA)

        self.client.force_login(self.secretaria)
        tela = self.client.get(lista)
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, 'Maria Silva')
        self.assertContains(tela, 'simulada')
        self.assertNotContains(tela, 'Simular resposta do paciente')
        self.assertContains(self.client.get(inicio), 'Lembretes WhatsApp')
        self.assertContains(self.client.get(agenda), 'Preparar lembretes de amanhã')
        self.assertEqual(self.client.post(simular, {'texto': '1'}).status_code, 403)
        editar = self.client.get(reverse('core:editar_paciente', args=[self.paciente.pk]))
        self.assertContains(editar, 'Aceita lembretes por WhatsApp')

        self.client.force_login(self.dentista_user)
        editar_dentista = self.client.get(reverse('core:editar_paciente', args=[self.paciente.pk]))
        self.assertEqual(editar_dentista.status_code, 200)
        self.assertNotContains(editar_dentista, 'Aceita lembretes por WhatsApp')

        self.client.force_login(self.admin)
        tela_admin = self.client.get(lista)
        self.assertContains(tela_admin, 'Simular resposta do paciente')
        self.assertEqual(self.client.post(simular, {'texto': '2'}).status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.CANCELADA)
        destaque = self.client.get(lista)
        self.assertContains(destaque, 'Desmarcou')
        self.assertContains(destaque, 'A secretária precisa ver')
        self.assertContains(destaque, 'pill-atencao')

    def test_secretaria_prepara_lembretes_pela_agenda(self):
        self.client.force_login(self.secretaria)
        with patch('core.views_whatsapp.timezone.localdate', return_value=self.HOJE):
            resposta = self.client.post(reverse('core:preparar_lembretes_amanha'))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.enviadas().count(), 2)
        self.client.force_login(self.dentista_user)
        with patch('core.views_whatsapp.timezone.localdate', return_value=self.HOJE):
            self.assertEqual(
                self.client.post(reverse('core:preparar_lembretes_amanha')).status_code,
                403,
            )
        self.assertEqual(self.enviadas().count(), 2)
