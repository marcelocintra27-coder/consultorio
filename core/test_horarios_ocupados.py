"""Tela de agendar: caixa com os horários já ocupados do dia."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala, TurnoLocacao
from .models import Consulta, Paciente

SEGUNDA = date(2026, 10, 12)


class HorariosOcupadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sala = Sala.objects.create(nome='Sala HO')
        cls.titular = Dentista.objects.create(nome_completo='Dra Titular HO', sala=cls.sala)
        cls.locataria = Dentista.objects.create(
            nome_completo='Dra Locataria HO', tipo=Dentista.Tipo.LOCATARIA,
        )
        TurnoLocacao.objects.create(
            dentista=cls.locataria, sala=cls.sala, dia_semana=0,
            hora_inicio=time(8), hora_fim=time(12),
        )
        cls.paciente = Paciente.objects.create(
            nome_completo='Paciente Secreto HO', cpf='705.000.111-01',
            data_nascimento=date(1990, 1, 1), telefone='11900000000',
        )
        cls.secretaria = User.objects.create_user('secretaria_ho')
        PerfilUsuario.objects.create(usuario=cls.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        cls.dentista_user = User.objects.create_user('dentista_ho')
        PerfilUsuario.objects.create(
            usuario=cls.dentista_user, papel=PerfilUsuario.Papel.DENTISTA, dentista=cls.titular,
        )
        cls.auxiliar = User.objects.create_user('auxiliar_ho')
        PerfilUsuario.objects.create(
            usuario=cls.auxiliar, papel=PerfilUsuario.Papel.AUXILIAR, dentista=cls.titular,
        )
        cls.url = reverse('core:horarios_ocupados')

    def setUp(self):
        self.client.force_login(self.secretaria)

    def consulta(self, dentista, inicio, fim, **extra):
        return Consulta.objects.create(
            paciente=self.paciente, dentista=dentista, data=SEGUNDA,
            hora_inicio=time(*inicio), hora_fim=time(*fim), **extra,
        )

    def pedir(self, **params):
        return self.client.get(self.url, params)

    def test_sem_dentista_ou_data_pede_para_escolher(self):
        resposta = self.pedir(data='2026-10-12')
        self.assertContains(resposta, 'Escolha a dentista e a data')

    def test_mostra_consultas_sem_nome_do_paciente_e_ignora_cancelada(self):
        self.consulta(self.titular, (14, 0), (14, 30))
        self.consulta(self.titular, (16, 0), (17, 0), status=Consulta.Status.CANCELADA)
        resposta = self.pedir(dentista=self.titular.pk, data='2026-10-12')
        self.assertContains(resposta, '14:00 às 14:30')
        self.assertNotContains(resposta, '16:00 às 17:00')
        self.assertNotContains(resposta, 'Paciente Secreto')

    def test_titular_ve_turno_alugado_da_sala(self):
        resposta = self.pedir(dentista=self.titular.pk, data='2026-10-12')
        self.assertContains(resposta, '08:00 às 12:00')
        self.assertContains(resposta, 'Sala alugada para Dra Locataria HO')

    def test_locataria_ve_seu_turno_e_consulta_da_titular_dentro_dele(self):
        self.consulta(self.titular, (9, 0), (10, 0))
        self.consulta(self.titular, (15, 0), (16, 0))
        resposta = self.pedir(dentista=self.locataria.pk, data='2026-10-12')
        self.assertContains(resposta, 'Atende neste dia: 08:00 às 12:00')
        self.assertContains(resposta, '09:00 às 10:00')
        self.assertContains(resposta, 'Titular da sala atendendo')
        self.assertNotContains(resposta, '15:00 às 16:00')

    def test_locataria_sem_turno_no_dia_avisa(self):
        resposta = self.pedir(dentista=self.locataria.pk, data='2026-10-13')
        self.assertContains(resposta, 'não tem turno neste dia')

    def test_dia_livre(self):
        resposta = self.pedir(dentista=self.titular.pk, data='2026-10-13')
        self.assertContains(resposta, 'Nenhum horário ocupado')

    def test_dentista_so_consulta_a_propria_agenda(self):
        self.client.force_login(self.dentista_user)
        self.assertEqual(self.pedir(dentista=self.titular.pk, data='2026-10-12').status_code, 200)
        self.assertEqual(self.pedir(dentista=self.locataria.pk, data='2026-10-12').status_code, 403)

    def test_auxiliar_e_anonimo_nao_acessam(self):
        self.client.force_login(self.auxiliar)
        self.assertEqual(self.pedir(dentista=self.titular.pk, data='2026-10-12').status_code, 403)
        self.client.logout()
        self.assertNotEqual(self.pedir(dentista=self.titular.pk, data='2026-10-12').status_code, 200)

    def test_remarcar_nao_mostra_a_propria_consulta(self):
        propria = self.consulta(self.titular, (14, 0), (14, 30))
        self.consulta(self.titular, (15, 0), (15, 30))
        resposta = self.pedir(consulta=propria.pk, data='2026-10-12')
        self.assertNotContains(resposta, '14:00 às 14:30')
        self.assertContains(resposta, '15:00 às 15:30')

    def test_data_invalida_nao_quebra(self):
        resposta = self.pedir(dentista=self.titular.pk, data='abc')
        self.assertEqual(resposta.status_code, 200)

    def test_tela_de_agendar_tem_a_caixa_e_a_dentista_vem_primeiro(self):
        resposta = self.client.get(reverse('core:agendar_consulta'))
        self.assertContains(resposta, 'id="horarios-ocupados"')
        self.assertContains(resposta, 'agendar.js')
        html = resposta.content.decode()
        self.assertLess(html.index('name="dentista"'), html.index('name="paciente"'))
