"""Tela inicial da recepção: consultas de hoje com botões de um clique."""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala
from .models import AuditoriaConsulta, Consulta, Paciente


class InicioRecepcaoTests(TestCase):
    def setUp(self):
        self.dentista = Dentista.objects.create(
            nome_completo='Dra. Inicio', sala=Sala.objects.create(nome='Sala Inicio'),
        )
        self.secretaria = User.objects.create_user('sec_inicio')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.client.force_login(self.secretaria)
        self.hoje = timezone.localdate()
        self.ana = self.consulta('Ana Inicio', 8)
        self.bia = self.consulta('Bia Inicio', 9, status=Consulta.Status.PRESENTE)

    def consulta(self, nome, hora, **extra):
        paciente = Paciente.objects.create(
            nome_completo=nome, data_nascimento=date(1990, 1, 1), telefone='62900000000',
        )
        return Consulta.objects.create(
            paciente=paciente, dentista=self.dentista, data=extra.pop('data', self.hoje),
            hora_inicio=time(hora), hora_fim=time(hora, 30), **extra,
        )

    def test_lista_de_hoje_no_topo_com_botoes_permitidos(self):
        html = self.client.get(reverse('core:inicio')).content.decode()
        self.assertLess(html.index('Consultas de hoje'), html.index('Fichas antigas'))
        self.assertIn('2 marcadas', html)
        self.assertIn('1 chegou', html)
        linha_ana = html.split('Ana Inicio', 1)[1].split('</tr>', 1)[0]
        self.assertIn('>Confirmou<', linha_ana)
        self.assertIn('>Chegou<', linha_ana)
        self.assertIn('>Faltou<', linha_ana)
        linha_bia = html.split('Bia Inicio', 1)[1].split('</tr>', 1)[0]
        self.assertNotIn('>Chegou<', linha_bia)
        self.assertNotIn('>Confirmou<', linha_bia)

    def test_um_clique_marca_chegou_volta_ao_inicio_e_audita(self):
        resposta = self.client.post(
            reverse('core:alterar_status_consulta', args=[self.ana.pk]),
            {'status': 'presente', 'voltar': 'inicio'}, follow=True,
        )
        self.assertRedirects(resposta, reverse('core:inicio'))
        self.assertContains(resposta, 'Ana Inicio: Paciente chegou.')
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.status, Consulta.Status.PRESENTE)
        self.assertTrue(AuditoriaConsulta.objects.filter(consulta=self.ana).exists())

    def test_secretaria_nao_marca_realizada_nem_volta_status_final(self):
        resposta = self.client.post(
            reverse('core:alterar_status_consulta', args=[self.bia.pk]),
            {'status': 'realizada', 'voltar': 'inicio'},
        )
        self.assertEqual(resposta.status_code, 403)
        self.bia.refresh_from_db()
        self.assertEqual(self.bia.status, Consulta.Status.PRESENTE)

    def test_consulta_de_outro_dia_nao_aparece(self):
        self.consulta('Caio Amanha', 10, data=self.hoje + timedelta(days=1))
        self.assertNotContains(self.client.get(reverse('core:inicio')), 'Caio Amanha')

    def test_sem_voltar_continua_indo_para_a_consulta(self):
        resposta = self.client.post(
            reverse('core:alterar_status_consulta', args=[self.ana.pk]), {'status': 'confirmada'},
        )
        self.assertRedirects(resposta, reverse('core:ficha_consulta', args=[self.ana.pk]), fetch_redirect_response=False)
