"""Modo simples: preferência por usuário, sem abrir permissão nova."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, Paciente


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ModoSimplesTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala simples')
        self.outra_sala = Sala.objects.create(nome='Sala alheia')
        self.adriana = Dentista.objects.create(nome_completo='Dra. Adriana', sala=self.sala)
        self.simone = Dentista.objects.create(nome_completo='Dra. Simone', sala=self.outra_sala)
        self.dentista = User.objects.create_user('adriana', password='x', first_name='Adriana')
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.dentista, papel=PerfilUsuario.Papel.DENTISTA, dentista=self.adriana,
        )
        self.secretaria = User.objects.create_user('amanda', password='x', first_name='Amanda')
        self.perfil_secretaria = PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.auxiliar = User.objects.create_user('emilly', password='x', first_name='Emilly')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar, papel=PerfilUsuario.Papel.AUXILIAR, dentista=self.adriana,
        )
        self.admin = User.objects.create_superuser('admin_simples', password='x')
        self.hoje = timezone.localdate()
        self.minha = self._consulta('Paciente da Adriana', self.adriana, '11910000001')
        self.alheia = self._consulta('Paciente da Simone', self.simone, '11910000002')
        self.inicio = reverse('core:inicio')
        self.alternar = reverse('core:alternar_modo_simples')
        self.agenda = reverse('core:listar_consultas') + '?data=' + self.hoje.isoformat()
        self.pacientes = reverse('core:listar_pacientes')
        self.materiais = reverse('core:listar_materiais_dia')

    def _consulta(self, nome, dentista, telefone):
        paciente = Paciente.objects.create(
            nome_completo=nome, data_nascimento=date(1990, 1, 1), telefone=telefone,
        )
        return Consulta.objects.create(
            paciente=paciente, dentista=dentista,
            data=self.hoje, hora_inicio=time(9), hora_fim=time(10),
        )

    def _ligar(self, perfil):
        perfil.modo_simples = True
        perfil.save(update_fields=['modo_simples'])

    def test_padrao_desligado(self):
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.modo_simples)
        self.client.force_login(self.dentista)
        pagina = self.client.get(self.inicio)
        self.assertContains(pagina, 'Ativar modo simples')
        self.assertNotContains(pagina, 'Desativar modo simples')
        self.assertNotContains(pagina, 'class="app-autenticado modo-simples"')
        self.assertContains(pagina, 'Agenda clínica de hoje')
        self.assertNotContains(pagina, 'Meus valores de hoje')
        self.assertContains(pagina, 'csrfmiddlewaretoken')

    def test_ligar_e_desligar_pelo_link(self):
        self.client.force_login(self.dentista)
        self.assertEqual(self.client.get(self.alternar).status_code, 405)
        ligado = self.client.post(self.alternar, follow=True)
        self.assertRedirects(ligado, self.inicio)
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.modo_simples)
        self.assertContains(ligado, 'class="app-autenticado modo-simples"')
        self.assertContains(ligado, 'Desativar modo simples')
        html = ligado.content.decode()
        self.assertLess(html.find('Desativar modo simples'), html.find('Trocar minha senha'))

        desligado = self.client.post(self.alternar, follow=True)
        self.assertRedirects(desligado, self.inicio)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.modo_simples)
        self.assertContains(desligado, 'Ativar modo simples')
        self.assertNotContains(desligado, 'class="app-autenticado modo-simples"')
        self.assertContains(desligado, 'Agenda clínica de hoje')

    def test_dentista_com_modo_simples_ve_os_quatro_botoes_e_cada_tela(self):
        self._ligar(self.perfil)
        self.client.force_login(self.dentista)
        pagina = self.client.get(self.inicio)
        self.assertContains(pagina, 'Minha agenda de hoje')
        self.assertContains(pagina, 'Buscar paciente')
        self.assertContains(pagina, 'Registrar atendimento')
        self.assertContains(pagina, 'Meus valores de hoje')
        self.assertContains(pagina, 'Ver painel completo')
        self.assertNotContains(pagina, 'Agenda clínica de hoje')
        self.assertContains(pagina, self.agenda)
        self.assertContains(pagina, self.pacientes)
        self.assertContains(pagina, self.materiais)
        self.assertNotContains(pagina, reverse('core:listar_contas_receber'))
        self.assertNotContains(pagina, reverse('core:relatorios_financeiros'))
        self.assertNotContains(pagina, reverse('locacao:acerto_mensal'))

        agenda = self.client.get(self.agenda)
        self.assertEqual(agenda.status_code, 200)
        self.assertContains(agenda, self.minha.paciente.nome_completo)
        self.assertContains(agenda, reverse('core:ficha_consulta', args=[self.minha.pk]))
        self.assertNotContains(agenda, self.alheia.paciente.nome_completo)
        ficha = self.client.get(reverse('core:ficha_consulta', args=[self.minha.pk]))
        self.assertEqual(ficha.status_code, 200)
        self.assertContains(ficha, self.minha.paciente.nome_completo)
        self.assertEqual(
            self.client.get(reverse('core:ficha_consulta', args=[self.alheia.pk])).status_code,
            403,
        )

        busca = self.client.get(self.pacientes)
        self.assertEqual(busca.status_code, 200)
        self.assertContains(busca, 'Buscar por nome, CPF ou telefone')
        self.assertContains(busca, self.minha.paciente.nome_completo)
        self.assertNotContains(busca, self.alheia.paciente.nome_completo)

        financeiro = self.client.get(self.materiais)
        self.assertEqual(financeiro.status_code, 200)
        self.assertContains(financeiro, 'Total a cobrar')
        self.assertContains(financeiro, self.minha.paciente.nome_completo)
        self.assertNotContains(financeiro, self.alheia.paciente.nome_completo)
        self.assertEqual(self.client.get(reverse('core:listar_contas_receber')).status_code, 403)
        self.assertEqual(self.client.get(reverse('core:relatorios_financeiros')).status_code, 403)
        self.assertEqual(self.client.get(reverse('locacao:acerto_mensal')).status_code, 403)
        self.assertEqual(self.client.get(reverse('core:listar_pagamentos_consulta')).status_code, 403)

        completo = self.client.get(self.inicio, {'painel': 'completo'})
        self.assertContains(completo, 'Agenda clínica de hoje')
        self.assertContains(completo, 'class="app-autenticado modo-simples"')
        self.assertNotContains(completo, 'Meus valores de hoje')
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.modo_simples)

    def test_dentista_sem_modo_simples_ve_o_painel_atual(self):
        self.client.force_login(self.dentista)
        pagina = self.client.get(self.inicio)
        self.assertContains(pagina, 'Rotina clínica')
        self.assertContains(pagina, 'Agenda clínica de hoje')
        self.assertContains(pagina, 'Anamneses pendentes')
        self.assertNotContains(pagina, 'Minha agenda de hoje')
        self.assertNotContains(pagina, 'Ver painel completo')

    def test_outros_papeis_nao_mudam_a_pagina_inicial(self):
        self._ligar(self.perfil_secretaria)
        self.client.force_login(self.secretaria)
        secretaria = self.client.get(self.inicio)
        self.assertContains(secretaria, 'class="app-autenticado modo-simples"')
        self.assertContains(secretaria, 'Rotina da secretária')
        self.assertContains(secretaria, 'Agendar consulta')
        self.assertNotContains(secretaria, 'Minha agenda de hoje')
        self.assertNotContains(secretaria, 'Meus valores de hoje')
        self.assertNotContains(secretaria, 'Registrar atendimento')

        auxiliar = PerfilUsuario.objects.get(usuario=self.auxiliar)
        self._ligar(auxiliar)
        self.client.force_login(self.auxiliar)
        pagina_auxiliar = self.client.get(self.inicio)
        self.assertContains(pagina_auxiliar, 'class="app-autenticado modo-simples"')
        self.assertContains(pagina_auxiliar, 'Auxiliar')
        self.assertNotContains(pagina_auxiliar, 'Minha agenda de hoje')
        self.assertNotContains(pagina_auxiliar, 'Meus valores de hoje')
        self.assertNotContains(pagina_auxiliar, 'Rotina clínica')

        PerfilUsuario.objects.create(
            usuario=self.admin, papel=PerfilUsuario.Papel.SECRETARIA, modo_simples=True,
        )
        self.client.force_login(self.admin)
        admin = self.client.get(self.inicio)
        self.assertContains(admin, 'class="app-autenticado modo-simples"')
        self.assertContains(admin, 'Painel administrativo')
        self.assertNotContains(admin, 'Minha agenda de hoje')
        self.assertNotContains(admin, 'Meus valores de hoje')

    def test_admin_mostra_a_caixinha_e_quem_nao_tem_perfil_nao_alterna(self):
        self.client.force_login(self.admin)
        url = reverse('admin:locacao_perfilusuario_change', args=[self.perfil.pk])
        pagina = self.client.get(url)
        self.assertContains(pagina, 'Modo simples (letra e botões maiores)')
        self.assertContains(pagina, 'name="modo_simples"')
        resposta = self.client.post(url, {
            'usuario': self.dentista.pk,
            'dentista': self.adriana.pk,
            'papel': PerfilUsuario.Papel.DENTISTA,
            'modo_simples': 'on',
        })
        self.assertEqual(resposta.status_code, 302, resposta.content.decode()[:500])
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.modo_simples)

        sem_perfil = User.objects.create_user('sem_perfil_simples', password='x')
        self.client.force_login(sem_perfil)
        self.assertNotContains(self.client.get(self.inicio), 'Ativar modo simples')
        self.assertEqual(self.client.post(self.alternar).status_code, 403)
