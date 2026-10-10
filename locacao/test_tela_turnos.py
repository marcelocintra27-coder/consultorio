"""Tela da locatária: turnos da semana numa lista curta."""
from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, Sala, TurnoLocacao


class TelaTurnosTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Adriana T')
        self.outra = Sala.objects.create(nome='Sala Claudia T')
        Dentista.objects.create(nome_completo='Dra. Adriana T', sala=self.sala)
        self.locataria = Dentista.objects.create(
            nome_completo='Dra. Gabriela T', tipo=Dentista.Tipo.LOCATARIA,
        )
        self.client.force_login(User.objects.create_superuser('admin_tt', password='x'))
        self.url = reverse('locacao:editar_dentista', args=[self.locataria.pk])

    def turno(self, dia, inicio, fim, **extra):
        return TurnoLocacao.objects.create(
            dentista=self.locataria, sala=self.sala, dia_semana=dia,
            hora_inicio=time(inicio), hora_fim=time(fim), **extra,
        )

    def test_sem_turno_convida_a_adicionar(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Nenhum turno ainda')
        self.assertContains(resposta, 'Adicionar turno')

    def test_lista_curta_e_sala_sugerida(self):
        self.turno(0, 8, 12)
        self.turno(4, 14, 18)
        resposta = self.client.get(self.url)
        html = resposta.content.decode()
        self.assertContains(resposta, 'Segunda-feira')
        self.assertContains(resposta, '14:00 às 18:00')
        self.assertEqual(html.count('class="turno-linha"'), 2)
        self.assertNotContains(resposta, 'Nenhum turno ainda')
        self.assertIn(f'<option value="{self.sala.pk}" selected>', html.split('Adicionar turno</h3>')[1])

    def test_desativado_vai_para_o_historico(self):
        self.turno(0, 8, 12)
        self.turno(3, 8, 12, ativo=False)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.content.decode().count('class="turno-linha"'), 1)
        self.assertContains(resposta, 'Turnos desativados (histórico)')

    def test_erro_ao_editar_abre_o_turno_com_o_aviso(self):
        alvo = self.turno(0, 8, 12)
        self.turno(3, 8, 12)
        resposta = self.client.post(
            reverse('locacao:editar_turno', args=[self.locataria.pk, alvo.pk]),
            {'sala': self.sala.pk, 'dia_semana': 0, 'hora_inicio': '12:00', 'hora_fim': '08:00'},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, '<details class="turno-editar" open>')
        self.assertContains(resposta, 'A hora fim deve ser posterior')

    def test_nova_locataria_recebe_orientacao(self):
        resposta = self.client.post(reverse('locacao:cadastrar_dentista'), {
            'nome_completo': 'Dra. Nova Loc', 'tipo': 'locataria', 'valor_hora': '0',
        }, follow=True)
        self.assertContains(resposta, 'Agora adicione os turnos dela')
        self.assertContains(resposta, 'Como trabalha na clínica')


class TravaTitularViraLocatariaTests(TestCase):
    def setUp(self):
        from datetime import date, timedelta

        from django.utils import timezone

        from core.models import Consulta, Paciente

        self.sala = Sala.objects.create(nome='Sala Trava')
        self.titular = Dentista.objects.create(nome_completo='Dra. Titular Trava', sala=self.sala)
        self.locataria = Dentista.objects.create(
            nome_completo='Dra. Inquilina Trava', tipo=Dentista.Tipo.LOCATARIA,
        )
        self.client.force_login(User.objects.create_superuser('admin_trava', password='x'))
        self.url = reverse('locacao:editar_dentista', args=[self.titular.pk])
        self.dados = {'nome_completo': 'Dra. Titular Trava', 'tipo': 'locataria', 'valor_hora': '0'}
        self.Consulta = Consulta
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Trava', data_nascimento=date(1990, 1, 1), telefone='62900000000',
        )
        self.amanha = timezone.localdate() + timedelta(days=1)

    def test_recusa_se_a_sala_esta_alugada(self):
        TurnoLocacao.objects.create(
            dentista=self.locataria, sala=self.sala, dia_semana=0,
            hora_inicio=time(8), hora_fim=time(12),
        )
        resposta = self.client.post(self.url, self.dados)
        self.assertContains(resposta, 'está alugada para Dra. Inquilina Trava')
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.tipo, Dentista.Tipo.TITULAR)
        self.assertEqual(self.titular.sala, self.sala)

    def test_recusa_se_tem_consulta_futura(self):
        self.Consulta.objects.create(
            paciente=self.paciente, dentista=self.titular, data=self.amanha,
            hora_inicio=time(9), hora_fim=time(10),
        )
        resposta = self.client.post(self.url, self.dados)
        self.assertContains(resposta, '1 consulta(s) marcada(s)')
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.tipo, Dentista.Tipo.TITULAR)

    def test_permite_quando_nao_ha_nada_preso_a_sala(self):
        self.Consulta.objects.create(
            paciente=self.paciente, dentista=self.titular, data=self.amanha,
            hora_inicio=time(9), hora_fim=time(10), status=self.Consulta.Status.CANCELADA,
        )
        resposta = self.client.post(self.url, self.dados)
        self.assertEqual(resposta.status_code, 302)
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.tipo, Dentista.Tipo.LOCATARIA)
        self.assertIsNone(self.titular.sala)
