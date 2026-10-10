"""Lista de pacientes com um botão por linha, paginação e ficha só para leitura."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, Paciente


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ListaEFichaPacienteTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala F')
        self.dentista = Dentista.objects.create(nome_completo='Dra. F', sala=sala)
        self.paciente = Paciente.objects.create(
            nome_completo='Maria Ficha', data_nascimento=date(1990, 1, 1), telefone='62999990000',
        )
        self.admin = User.objects.create_superuser('admin_ficha', password='x')
        self.secretaria = User.objects.create_user('sec_ficha', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.lista = reverse('core:listar_pacientes')
        self.ficha = reverse('core:ficha_paciente', args=[self.paciente.pk])

    def test_lista_tem_um_botao_por_paciente(self):
        self.client.force_login(self.admin)
        html = self.client.get(self.lista).content.decode()
        self.assertIn('Abrir ficha', html)
        self.assertIn(self.ficha, html)
        self.assertNotIn('>Anamnese</a>', html)
        self.assertNotIn('>Editar</a>', html)
        self.assertIn('anos', html)

    def test_lista_pagina_de_25_em_25_e_mantem_a_busca(self):
        for i in range(30):
            Paciente.objects.create(
                nome_completo=f'Teste Pagina {i:02d}', data_nascimento=date(1980, 1, 1),
                telefone=f'6290000{i:04d}',
            )
        self.client.force_login(self.admin)
        primeira = self.client.get(self.lista)
        self.assertEqual(primeira.content.decode().count('Abrir ficha</a>'), 25)
        self.assertContains(primeira, 'Página 1 de 2')
        busca = self.client.get(self.lista, {'q': 'Teste Pagina'})
        self.assertContains(busca, 'q=Teste%20Pagina&amp;pagina=2')

    def test_admin_ve_ficha_com_prontuario_e_editar(self):
        Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista, data=date(2099, 1, 5),
            hora_inicio=time(9), hora_fim=time(10),
        )
        self.client.force_login(self.admin)
        resposta = self.client.get(self.ficha)
        self.assertContains(resposta, 'Maria Ficha')
        self.assertContains(resposta, 'Editar dados')
        self.assertContains(resposta, 'Plano e consentimento')
        self.assertContains(resposta, 'Autorização de custos')
        self.assertContains(resposta, '05/01/2099 às 09:00')

    def test_secretaria_ve_ficha_sem_prontuario(self):
        self.client.force_login(self.secretaria)
        resposta = self.client.get(self.ficha)
        self.assertContains(resposta, 'Editar dados')
        self.assertNotContains(resposta, 'Plano e consentimento')
        self.assertNotContains(resposta, 'Receitas e prescrições')

    def test_dentista_nao_abre_ficha_de_paciente_de_outra(self):
        outra = Dentista.objects.create(nome_completo='Dra. G', sala=Sala.objects.create(nome='Sala G'))
        usuario = User.objects.create_user('dra_g', password='x')
        PerfilUsuario.objects.create(usuario=usuario, papel=PerfilUsuario.Papel.DENTISTA, dentista=outra)
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(self.ficha).status_code, 404)
