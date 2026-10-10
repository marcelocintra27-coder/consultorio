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


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PendenciasFichaTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from .models import FichaCadastroAnamnese, Procedimento, LancamentoAtendimento
        sala = Sala.objects.create(nome='Sala P')
        self.dentista = Dentista.objects.create(nome_completo='Dra. P', sala=sala)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Pendente', data_nascimento=date(1990, 1, 1), telefone='62999990000',
        )
        self.ficha_url = reverse('core:ficha_paciente', args=[self.paciente.pk])
        self.admin = User.objects.create_superuser('admin_pend', password='x')
        self.secretaria = User.objects.create_user('sec_pend', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        FichaCadastroAnamnese.objects.create(
            paciente=self.paciente, tipo='hof', status='aguardando_dentista',
            nome_completo='Paciente Pendente', data_nascimento=date(1990, 1, 1), cpf='',
            telefone='62999990000', alergia='sim', alergia_qual='dipirona',
        )
        consulta = Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista, data=date(2026, 10, 1),
            hora_inicio=time(9), hora_fim=time(10), status='realizada',
        )
        proc = Procedimento.objects.create(dentista=self.dentista, nome='Limpeza')
        LancamentoAtendimento.objects.create(
            consulta=consulta, procedimento=proc, nome_procedimento='Limpeza',
            dentista=self.dentista, particular=True, valor_tabela=Decimal('120'),
            percentual_desconto=Decimal('0'), valor_final=Decimal('120'),
            tipo='atendimento', cadastrado_por=self.admin,
        )

    def test_admin_ve_alergia_assinatura_valor_e_cadastro(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(self.ficha_url)
        self.assertContains(resposta, 'ALERGIA:</strong> dipirona')
        self.assertContains(resposta, 'Anamnese HOF: falta a assinatura do dentista.')
        self.assertContains(resposta, 'R$ 120,00 em aberto da consulta de 01/10/2026.')
        self.assertContains(resposta, 'Cadastro sem CPF')
        self.assertContains(resposta, 'Sem WhatsApp no cadastro')

    def test_secretaria_ve_so_o_que_e_do_cadastro(self):
        self.client.force_login(self.secretaria)
        resposta = self.client.get(self.ficha_url)
        self.assertNotContains(resposta, 'dipirona')
        self.assertNotContains(resposta, 'Anamnese HOF')
        self.assertNotContains(resposta, 'em aberto')
        self.assertContains(resposta, 'Cadastro sem CPF')

    def test_consulta_paga_nao_aparece_como_pendencia(self):
        Consulta.objects.update(pago=True)
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(self.ficha_url), 'em aberto')

    def test_alergia_nao_aparece_se_a_anamnese_ainda_e_rascunho(self):
        from .models import FichaCadastroAnamnese
        FichaCadastroAnamnese.objects.update(status='rascunho')
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(self.ficha_url), 'ALERGIA')
