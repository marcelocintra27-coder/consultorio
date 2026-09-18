from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala
from .models import AuditoriaConsulta, Consulta, MaterialUsado, Paciente


class AgendaA005Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sala = Sala.objects.create(nome='A005')
        cls.dentista = Dentista.objects.create(nome_completo='Dentista A005', sala=sala)
        cls.outro = Dentista.objects.create(
            nome_completo='Outro A005', sala=Sala.objects.create(nome='Outra A005'),
        )
        cls.paciente = Paciente.objects.create(
            nome_completo='Paciente A005', cpf='705.000.000-01',
            data_nascimento=date(1990, 1, 1), telefone='11900000000',
        )
        cls.admin_user = User.objects.create_superuser('admin_a005', 'a@example.com', 'x')
        cls.usuarios = {}
        for nome, papel, dentista in (
            ('secretaria', PerfilUsuario.Papel.SECRETARIA, None),
            ('dentista', PerfilUsuario.Papel.DENTISTA, cls.dentista),
            ('outro', PerfilUsuario.Papel.DENTISTA, cls.outro),
            ('auxiliar', PerfilUsuario.Papel.AUXILIAR, cls.dentista),
        ):
            user = User.objects.create_user(nome + '_a005')
            PerfilUsuario.objects.create(usuario=user, papel=papel, dentista=dentista)
            cls.usuarios[nome] = user

    def setUp(self):
        self.consulta = self.criar_consulta()
        self.url = reverse('core:remarcar_consulta', args=[self.consulta.pk])
        self.dados = {'data': '2026-09-21', 'hora_inicio': '11:00', 'hora_fim': '12:00'}
        self.client.force_login(self.usuarios['secretaria'])

    def criar_consulta(self, **kwargs):
        dados = dict(paciente=self.paciente, dentista=self.dentista,
                     data=date(2026, 9, 20), hora_inicio=time(9), hora_fim=time(10))
        dados.update(kwargs)
        return Consulta.objects.create(**dados)

    def test_get_e_post_autorizados_preservam_pk_vinculos_e_auditam(self):
        material = MaterialUsado.objects.create(consulta=self.consulta, descricao='Teste', valor=10)
        for user in (self.usuarios['secretaria'], self.usuarios['dentista'], self.admin_user):
            with self.subTest(user=user.username):
                self.consulta.data = date(2026, 9, 20)
                self.consulta.save(update_fields=['data'])
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 200)
                dados = dict(self.dados, paciente=99999, dentista=self.outro.pk,
                             status='realizada', motivo='Pedido do paciente')
                self.assertEqual(self.client.post(self.url, dados).status_code, 302)
                self.consulta.refresh_from_db()
                self.assertEqual(Consulta.objects.count(), 1)
                self.assertEqual(self.consulta.data, date(2026, 9, 21))
                self.assertEqual(self.consulta.hora_inicio, time(11))
                self.assertEqual(self.consulta.hora_fim, time(12))
                self.assertEqual(self.consulta.paciente_id, self.paciente.pk)
                self.assertEqual(self.consulta.dentista_id, self.dentista.pk)
                self.assertEqual(self.consulta.status, 'agendada')
                material.refresh_from_db()
                self.assertEqual(material.consulta_id, self.consulta.pk)
                audit = self.consulta.auditorias.first()
                self.assertEqual(audit.usuario, user)
                self.assertIsNotNone(audit.cadastrado_em)
                self.assertIn('2026-09-20', audit.descricao)
                self.assertIn('2026-09-21 11:00:00–12:00:00', audit.descricao)
                self.assertIn('Pedido do paciente', audit.descricao)
                self.assertIn('->', audit.descricao)

    def test_confirmada_volta_agendada_sem_motivo(self):
        self.consulta.status = 'confirmada'
        self.consulta.save(update_fields=['status'])
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, 'agendada')
        descricao = self.consulta.auditorias.get().descricao
        self.assertIn('09:00:00–10:00:00', descricao)
        self.assertIn('confirmada -> agendada', descricao)
        self.assertNotIn('motivo:', descricao)

    def test_status_bloqueados(self):
        for status in ('presente', 'realizada', 'faltou', 'cancelada'):
            with self.subTest(status=status):
                self.consulta.status = status
                self.consulta.save(update_fields=['status'])
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
                self.consulta.refresh_from_db()
                self.assertEqual(self.consulta.data, date(2026, 9, 20))
                self.assertEqual(self.consulta.status, status)
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_perfis_negados_e_staff_sem_papel(self):
        staff = User.objects.create_user('staff_a005', is_staff=True)
        for user in (self.usuarios['auxiliar'], self.usuarios['outro'], staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_autenticacao_csrf_metodos_e_get_sem_mutacao(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuarios['secretaria'])
        self.assertEqual(client.post(self.url, self.dados).status_code, 403)
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.put(self.url, self.dados).status_code, 405)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(AuditoriaConsulta.objects.exists())
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.data, date(2026, 9, 20))

    def test_conflitos_criacao_e_remarcacao(self):
        for inicio, fim in (('09:30', '10:30'), ('08:30', '09:30'),
                            ('08:00', '11:00'), ('09:15', '09:45'), ('09:00', '10:00')):
            for criacao in (False, True):
                with self.subTest(inicio=inicio, fim=fim, criacao=criacao):
                    outra = self.criar_consulta(data=date(2026, 9, 22))
                    url = reverse('core:agendar_consulta') if criacao else reverse(
                        'core:remarcar_consulta', args=[outra.pk])
                    dados = dict(data='2026-09-20', hora_inicio=inicio, hora_fim=fim,
                                 paciente=self.paciente.pk, dentista=self.dentista.pk)
                    resposta = self.client.post(url, dados)
                    self.assertContains(resposta, 'já possui consulta neste horário')
                    outra.refresh_from_db()
                    self.assertEqual(outra.data, date(2026, 9, 22))
                    outra.delete()
        self.assertEqual(Consulta.objects.count(), 1)
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_cancelada_nao_bloqueia_e_outro_dentista_nao_conflita(self):
        self.criar_consulta(data=date(2026, 9, 21), hora_inicio=time(11),
                            hora_fim=time(12), status='cancelada')
        self.criar_consulta(data=date(2026, 9, 21), hora_inicio=time(11),
                            hora_fim=time(12), dentista=self.outro)
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 302)

    def test_todos_status_nao_cancelados_bloqueiam_horario(self):
        conflito = self.criar_consulta(
            data=date(2026, 9, 21), hora_inicio=time(11), hora_fim=time(12),
        )
        for status in ('agendada', 'confirmada', 'presente', 'realizada', 'faltou'):
            conflito.status = status
            conflito.save(update_fields=['status'])
            self.assertContains(self.client.post(self.url, self.dados), 'já possui consulta')
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_legado_sem_dentista_preserva_dados(self):
        self.consulta.dentista = None
        self.consulta.eh_legado = True
        self.consulta.valor_historico = 150
        self.consulta.save()
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 302)
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.dentista_id)
        self.assertTrue(self.consulta.eh_legado)
        self.assertEqual(self.consulta.valor_historico, 150)

    def test_consecutivos_aceitos_na_criacao(self):
        for inicio, fim in (('08:00', '09:00'), ('10:00', '11:00')):
            dados = dict(data='2026-09-20', hora_inicio=inicio, hora_fim=fim,
                         paciente=self.paciente.pk, dentista=self.dentista.pk)
            self.assertEqual(self.client.post(reverse('core:agendar_consulta'), dados).status_code, 302)

    def test_propria_consulta_excluida_e_consecutiva_na_remarcacao(self):
        self.criar_consulta(hora_inicio=time(10), hora_fim=time(11))
        dados = dict(data='2026-09-20', hora_inicio='09:30', hora_fim='10:00')
        self.assertEqual(self.client.post(self.url, dados).status_code, 302)

    def test_intervalos_invalidos_nos_dois_fluxos(self):
        for fim in ('11:00', '10:00'):
            for url in (self.url, reverse('core:agendar_consulta')):
                dados = dict(self.dados, hora_fim=fim, paciente=self.paciente.pk, dentista=self.dentista.pk)
                self.assertContains(self.client.post(url, dados), 'A hora fim deve ser posterior')
        self.assertEqual(Consulta.objects.count(), 1)
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_criacao_auditada_cancelada_nao_bloqueia(self):
        self.consulta.status = 'cancelada'
        self.consulta.save(update_fields=['status'])
        dados = dict(data='2026-09-20', hora_inicio='09:00', hora_fim='10:00',
                     paciente=self.paciente.pk, dentista=self.dentista.pk)
        self.assertEqual(self.client.post(reverse('core:agendar_consulta'), dados).status_code, 302)
        audit = AuditoriaConsulta.objects.get()
        self.assertEqual(audit.usuario, self.usuarios['secretaria'])
        self.assertIsNotNone(audit.cadastrado_em)
        for texto in ('agendar_consulta', f'paciente={self.paciente.pk}',
                      f'dentista={self.dentista.pk}', '2026-09-20', '09:00:00–10:00:00'):
            self.assertIn(texto, audit.descricao)

    def test_sem_alteracao_nao_audita_nem_desconfirma(self):
        self.consulta.status = 'confirmada'
        self.consulta.save(update_fields=['status'])
        dados = dict(data='2026-09-20', hora_inicio='09:00', hora_fim='10:00')
        self.assertContains(self.client.post(self.url, dados), 'Informe uma nova data')
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, 'confirmada')
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_motivo_limite_e_auditoria_cabem_sem_truncar(self):
        self.assertEqual(self.client.post(self.url, dict(self.dados, motivo='x' * 101)).status_code, 200)
        self.assertFalse(AuditoriaConsulta.objects.exists())
        self.assertEqual(self.client.post(self.url, dict(self.dados, motivo='x' * 100)).status_code, 302)
        descricao = AuditoriaConsulta.objects.get().descricao
        self.assertLessEqual(len(descricao), 300)
        self.assertIn('x' * 100, descricao)

    def test_falha_auditoria_reverte_criacao_e_remarcacao(self):
        with patch('core.views._registrar_auditoria', side_effect=RuntimeError('Falha simulada')):
            for url in (self.url, reverse('core:agendar_consulta')):
                with self.assertRaises(RuntimeError):
                    self.client.post(url, dict(self.dados, paciente=self.paciente.pk, dentista=self.dentista.pk))
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.data, date(2026, 9, 20))
        self.assertEqual(Consulta.objects.count(), 1)
        self.assertFalse(AuditoriaConsulta.objects.exists())

    def test_faltou_http_respeita_matriz(self):
        url = reverse('core:alterar_status_consulta', args=[self.consulta.pk])
        for user in (self.usuarios['auxiliar'], self.usuarios['outro']):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {'status': 'faltou'}).status_code, 403)
        for user in (self.usuarios['secretaria'], self.usuarios['dentista'], self.admin_user):
            self.consulta.status = 'agendada'
            self.consulta.save(update_fields=['status'])
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {'status': 'faltou'}).status_code, 302)
            self.consulta.refresh_from_db()
            self.assertEqual(self.consulta.status, 'faltou')
            self.assertEqual(self.consulta.auditorias.first().usuario, user)

    def test_admin_protecao_seletiva_http(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse('admin:core_consulta_add')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:core_consulta_add'), {}).status_code, 403)
        url = reverse('admin:core_consulta_change', args=[self.consulta.pk])
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context['adminform'].form
        for campo in ('data', 'hora_inicio', 'hora_fim', 'status', 'dentista'):
            self.assertNotIn(campo, form.fields)
        for campo in ('paciente', 'observacoes', 'pago', 'forma_pagamento', 'eh_legado'):
            self.assertIn(campo, form.fields)
        dados = dict(self.dados, paciente=self.paciente.pk, dentista=self.outro.pk,
                     status='realizada', observacoes='Edição administrativa preservada', _save='Salvar')
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.data, date(2026, 9, 20))
        self.assertEqual(self.consulta.hora_inicio, time(9))
        self.assertEqual(self.consulta.hora_fim, time(10))
        self.assertEqual(self.consulta.status, 'agendada')
        self.assertEqual(self.consulta.dentista_id, self.dentista.pk)
        self.assertEqual(self.consulta.observacoes, 'Edição administrativa preservada')
        self.assertFalse(AuditoriaConsulta.objects.exists())
