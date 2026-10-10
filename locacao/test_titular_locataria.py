"""Telas que separam titular (dona de sala) e locatária (aluga horários)."""
from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, Sala, TurnoLocacao


class TitularLocatariaTelasTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Adriana X')
        Sala.objects.create(nome='Sala Vaga X')
        self.titular = Dentista.objects.create(nome_completo='Adriana Titular X', sala=self.sala)
        self.locataria = Dentista.objects.create(
            nome_completo='Gabriela Locataria X', tipo=Dentista.Tipo.LOCATARIA,
        )
        TurnoLocacao.objects.create(
            dentista=self.locataria, sala=self.sala, dia_semana=0,
            hora_inicio=time(8), hora_fim=time(12),
        )
        self.client.force_login(User.objects.create_superuser('admin_tlx', password='x'))

    def test_equipe_separa_e_mostra_quem_aluga_de_quem(self):
        html = self.client.get(reverse('core:equipe')).content.decode()
        self.assertIn('Dentistas titulares', html)
        self.assertIn('Dentistas locatárias', html)
        self.assertIn('paga o aluguel direto a ela', html)
        titulares, locatarias = html.split('Dentistas locatárias', 1)
        titulares = titulares.split('Dentistas titulares', 1)[1]
        self.assertIn('Adriana Titular X', titulares)
        self.assertIn('Gabriela Locataria X', titulares)  # na coluna "Quem aluga"
        self.assertIn('seg 08:00–12:00', titulares)
        self.assertIn('Gabriela Locataria X', locatarias)
        self.assertIn('Adriana Titular X', locatarias)  # na coluna "Aluga de quem"
        self.assertIn('?tipo=titular', html)
        self.assertIn('?tipo=locataria', html)

    def test_nova_locataria_nao_mostra_escolha_de_tipo(self):
        resposta = self.client.get(reverse('locacao:cadastrar_dentista'), {'tipo': 'locataria'})
        self.assertContains(resposta, 'Nova dentista locatária')
        self.assertContains(resposta, 'type="hidden" name="tipo" value="locataria"')
        self.assertNotContains(resposta, 'Como trabalha na clínica')

    def test_nova_titular_cria_com_sala(self):
        vaga = Sala.objects.get(nome='Sala Vaga X')
        resposta = self.client.post(reverse('locacao:cadastrar_dentista'), {
            'nome_completo': 'Claudia Nova X', 'tipo': 'titular', 'sala': vaga.pk, 'valor_hora': '0',
        })
        self.assertRedirects(resposta, reverse('core:equipe'))
        self.assertEqual(Dentista.objects.get(nome_completo='Claudia Nova X').sala, vaga)

    def test_nome_repetido_e_recusado_mas_editar_a_propria_nao(self):
        resposta = self.client.post(reverse('locacao:cadastrar_dentista'), {
            'nome_completo': '  adriana   titular x ', 'tipo': 'locataria', 'valor_hora': '0',
        })
        self.assertContains(resposta, 'Já existe uma dentista com este nome')
        self.assertEqual(Dentista.objects.filter(nome_completo__iexact='adriana titular x').count(), 1)
        resposta = self.client.post(
            reverse('locacao:editar_dentista', args=[self.titular.pk]),
            {'nome_completo': 'Adriana Titular X', 'tipo': 'titular', 'sala': self.sala.pk, 'valor_hora': '0'},
        )
        self.assertEqual(resposta.status_code, 302)

    def test_tela_da_titular_mostra_quem_aluga_e_esconde_o_tipo(self):
        resposta = self.client.get(reverse('locacao:editar_dentista', args=[self.titular.pk]))
        self.assertContains(resposta, 'Quem aluga esta sala')
        self.assertContains(resposta, 'Gabriela Locataria X')
        self.assertContains(resposta, '<details class="mudar-tipo">')

    def test_tela_da_locataria_mostra_de_quem_aluga_e_dono_da_sala(self):
        resposta = self.client.get(reverse('locacao:editar_dentista', args=[self.locataria.pk]))
        self.assertContains(resposta, 'Aluga de:')
        self.assertContains(resposta, 'Sala Adriana X — da Adriana Titular X')
        self.assertContains(resposta, 'Sala Vaga X — sem titular')

    def test_locataria_em_sala_sem_titular_avisa_certo(self):
        vaga = Sala.objects.get(nome='Sala Vaga X')
        outra = Dentista.objects.create(nome_completo='Beatriz Loc X', tipo=Dentista.Tipo.LOCATARIA)
        TurnoLocacao.objects.create(
            dentista=outra, sala=vaga, dia_semana=3, hora_inicio=time(8), hora_fim=time(12),
        )
        self.assertContains(self.client.get(reverse('core:equipe')), 'Sala sem titular')
        resposta = self.client.get(reverse('locacao:editar_dentista', args=[outra.pk]))
        self.assertContains(resposta, 'a sala dos turnos não tem titular')
