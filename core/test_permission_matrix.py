from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AuditoriaConsulta,
    Consulta,
    FichaAutorizacaoCusto,
    FichaCadastroAnamnese,
    Paciente,
)


class MatrizPermissoesTests(TestCase):
    def setUp(self):
        sala_um = Sala.objects.create(nome='Sala da Dra. Um')
        sala_dois = Sala.objects.create(nome='Sala do Dr. Dois')
        self.dentista_um = Dentista.objects.create(
            nome_completo='Dra. Um', sala=sala_um
        )
        self.dentista_dois = Dentista.objects.create(
            nome_completo='Dr. Dois', sala=sala_dois
        )
        self.paciente_um = Paciente.objects.create(
            nome_completo='Paciente da Dra. Um',
            cpf='701.000.000-01',
            data_nascimento=date(1980, 1, 1),
            telefone='11900000001',
        )
        self.paciente_dois = Paciente.objects.create(
            nome_completo='Paciente do Dr. Dois',
            cpf='701.000.000-02',
            data_nascimento=date(1981, 1, 1),
            telefone='11900000002',
        )
        self.consulta_um = Consulta.objects.create(
            paciente=self.paciente_um,
            dentista=self.dentista_um,
            data=date(2026, 9, 11),
            hora_inicio=time(9),
            hora_fim=time(10),
        )
        self.consulta_dois = Consulta.objects.create(
            paciente=self.paciente_dois,
            dentista=self.dentista_dois,
            data=date(2026, 9, 11),
            hora_inicio=time(10),
            hora_fim=time(11),
        )
        self.secretaria = User.objects.create_user('secretaria_matriz', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.dentista_user = User.objects.create_user('dentista_matriz', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user,
            dentista=self.dentista_um,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.auxiliar = User.objects.create_user('auxiliar_matriz', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            dentista=self.dentista_um,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.admin = User.objects.create_superuser(
            'admin_matriz', 'admin@example.com', 'x'
        )

    def test_agenda_respeita_escopo_de_cada_perfil(self):
        url = reverse('core:listar_consultas') + '?data=2026-09-11'

        self.client.force_login(self.secretaria)
        resposta = self.client.get(url)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertContains(resposta, self.paciente_dois.nome_completo)

        self.client.force_login(self.dentista_user)
        resposta = self.client.get(url)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertNotContains(resposta, self.paciente_dois.nome_completo)

        self.client.force_login(self.auxiliar)
        resposta = self.client.get(url)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertNotContains(resposta, self.paciente_dois.nome_completo)
        self.assertNotContains(resposta, 'Agendar')

        self.client.force_login(self.admin)
        resposta = self.client.get(url)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertContains(resposta, self.paciente_dois.nome_completo)

    def test_secretaria_filtra_pendencias_de_confirmacao_sem_expor_valores(self):
        self.consulta_um.status = Consulta.Status.CONFIRMADA
        self.consulta_um.save(update_fields=['status'])
        url = (
            reverse('core:listar_consultas')
            + '?data=2026-09-11&status='
            + Consulta.Status.AGENDADA
        )

        self.client.force_login(self.secretaria)
        resposta = self.client.get(url)

        self.assertContains(resposta, self.paciente_dois.nome_completo)
        self.assertNotContains(resposta, self.paciente_um.nome_completo)
        self.assertContains(resposta, 'Todas as situações')
        self.assertNotContains(resposta, 'Valor a cobrar')

    def test_consulta_e_status_exigem_escopo_de_agenda(self):
        ficha_dois = reverse('core:ficha_consulta', args=[self.consulta_dois.pk])
        status_um = reverse('core:alterar_status_consulta', args=[self.consulta_um.pk])
        status_dois = reverse('core:alterar_status_consulta', args=[self.consulta_dois.pk])

        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(ficha_dois).status_code, 403)
        self.assertEqual(
            self.client.post(status_dois, {'status': Consulta.Status.CANCELADA}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(status_um, {'status': Consulta.Status.PRESENTE}).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(status_um, {'status': Consulta.Status.REALIZADA}).status_code,
            302,
        )

        self.client.force_login(self.auxiliar)
        self.assertEqual(
            self.client.get(reverse('core:ficha_consulta', args=[self.consulta_um.pk])).status_code,
            200,
        )
        self.assertEqual(self.client.get(ficha_dois).status_code, 403)
        self.assertEqual(
            self.client.post(status_um, {'status': Consulta.Status.CANCELADA}).status_code,
            403,
        )

        self.client.force_login(self.secretaria)
        self.assertEqual(
            self.client.post(status_dois, {'status': Consulta.Status.REALIZADA}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(status_dois, {'status': Consulta.Status.CANCELADA}).status_code,
            302,
        )

    def test_cadastro_de_paciente_respeita_vinculo_e_leitura_do_auxiliar(self):
        listar = reverse('core:listar_pacientes')
        editar_um = reverse('core:editar_paciente', args=[self.paciente_um.pk])
        editar_dois = reverse('core:editar_paciente', args=[self.paciente_dois.pk])

        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(editar_um).status_code, 200)
        self.assertEqual(self.client.get(editar_dois).status_code, 403)
        resposta = self.client.get(listar)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertNotContains(resposta, self.paciente_dois.nome_completo)

        self.client.force_login(self.auxiliar)
        resposta = self.client.get(listar)
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertNotContains(resposta, self.paciente_dois.nome_completo)
        self.assertEqual(self.client.get(editar_um).status_code, 403)

        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(editar_dois).status_code, 200)
        self.assertEqual(self.client.get(reverse('core:cadastrar_paciente')).status_code, 200)

    def test_dentista_cadastra_paciente_e_agenda_apenas_para_si(self):
        self.client.force_login(self.dentista_user)
        resposta = self.client.post(
            reverse('core:cadastrar_paciente'),
            {
                'nome_completo': 'Novo paciente da dentista',
                'cpf': '701.000.000-03',
                'data_nascimento': '1990-01-01',
                'telefone': '11900000003',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        novo_paciente = Paciente.objects.get(cpf='701.000.000-03')

        resposta = self.client.post(
            reverse('core:agendar_consulta'),
            {
                'paciente': novo_paciente.pk,
                'dentista': self.dentista_dois.pk,
                'data': '2026-09-12',
                'hora_inicio': '09:00',
                'hora_fim': '10:00',
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            Consulta.objects.filter(
                paciente=novo_paciente,
                dentista=self.dentista_dois,
            ).exists()
        )

        resposta = self.client.post(
            reverse('core:agendar_consulta'),
            {
                'paciente': novo_paciente.pk,
                'dentista': self.dentista_um.pk,
                'data': '2026-09-12',
                'hora_inicio': '09:00',
                'hora_fim': '10:00',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            Consulta.objects.filter(
                paciente=novo_paciente,
                dentista=self.dentista_um,
            ).exists()
        )

    def test_financeiro_administrativo_e_negado_ao_dentista_mas_lancamento_proprio_e_permitido(self):
        pagamentos = reverse('core:listar_pagamentos_consulta')
        materiais_um = reverse('core:materiais_consulta', args=[self.consulta_um.pk])
        materiais_dois = reverse('core:materiais_consulta', args=[self.consulta_dois.pk])
        marcar_pago = reverse('core:marcar_consulta_paga', args=[self.consulta_um.pk])

        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(pagamentos).status_code, 403)
        self.assertEqual(self.client.get(materiais_um).status_code, 200)
        self.assertEqual(self.client.get(materiais_dois).status_code, 403)
        self.assertEqual(self.client.post(marcar_pago, {'acao': 'marcar'}).status_code, 403)

        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(materiais_um).status_code, 403)

        self.client.force_login(self.auxiliar)
        self.assertEqual(self.client.get(materiais_um).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(pagamentos).status_code, 200)
        self.assertEqual(self.client.post(marcar_pago, {'acao': 'marcar'}).status_code, 302)

    def test_menu_lateral_exibe_somente_rotas_do_perfil(self):
        inicio = reverse('core:inicio')

        self.client.force_login(self.secretaria)
        resposta = self.client.get(inicio)
        self.assertContains(resposta, 'Secretária')
        self.assertContains(resposta, 'Agenda')
        self.assertContains(resposta, 'Pacientes')
        self.assertNotContains(resposta, 'Financeiro atual')
        self.assertNotContains(resposta, 'Materiais utilizados')

        self.client.force_login(self.dentista_user)
        resposta = self.client.get(inicio)
        self.assertContains(resposta, 'Dentista')
        self.assertContains(resposta, 'Minha rotina')
        self.assertContains(resposta, 'Materiais utilizados')
        self.assertNotContains(resposta, 'Financeiro atual')
        self.assertNotContains(resposta, 'Administração técnica')

        self.client.force_login(self.auxiliar)
        resposta = self.client.get(inicio)
        self.assertContains(resposta, 'Auxiliar')
        self.assertContains(resposta, 'Consulta')
        self.assertNotContains(resposta, reverse('core:agendar_consulta'))
        self.assertNotContains(resposta, 'Materiais utilizados')

        self.client.force_login(self.admin)
        resposta = self.client.get(inicio)
        self.assertContains(resposta, 'Administrador')
        self.assertContains(resposta, 'Financeiro atual')
        self.assertContains(resposta, 'Administração')

    def test_administracao_e_dashboard_sao_exclusivos_do_superusuario(self):
        administracao = reverse('core:administracao')
        staff = User.objects.create_user(
            'staff_tecnico_matriz', password='x', is_staff=True
        )

        for usuario in (self.secretaria, self.dentista_user, self.auxiliar, staff):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(administracao).status_code, 403)

        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('core:inicio'))
        self.assertContains(resposta, 'Painel administrativo')
        self.assertContains(resposta, 'Consultas em andamento')
        self.assertContains(resposta, 'Gerenciar acesso e configurações')
        self.assertNotContains(resposta, 'Rotina clínica')

        resposta = self.client.get(administracao)
        self.assertContains(resposta, 'Administração da clínica')
        self.assertContains(resposta, 'Usuários e permissões')
        self.assertContains(resposta, 'Profissionais e salas')
        self.assertContains(resposta, 'Auditoria')

    def test_dashboard_da_secretaria_exibe_apenas_operacao_autorizada(self):
        self.consulta_um.data = timezone.localdate()
        self.consulta_um.save(update_fields=['data'])
        self.consulta_dois.data = timezone.localdate()
        self.consulta_dois.save(update_fields=['data'])
        self.consulta_um.status = Consulta.Status.REALIZADA
        self.consulta_um.save(update_fields=['status'])
        self.consulta_dois.status = Consulta.Status.CANCELADA
        self.consulta_dois.save(update_fields=['status'])

        self.client.force_login(self.secretaria)
        resposta = self.client.get(reverse('core:inicio'))

        self.assertContains(resposta, 'Rotina da secretária')
        self.assertContains(resposta, 'Consultas do dia')
        self.assertContains(resposta, 'Agendar consulta')
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertContains(resposta, self.paciente_dois.nome_completo)
        self.assertContains(resposta, 'Realizadas')
        self.assertContains(resposta, 'Canceladas')
        self.assertNotContains(resposta, 'Pagamentos')
        self.assertNotContains(resposta, 'Materiais')
        self.assertNotContains(resposta, 'Administração técnica')
        self.assertNotContains(resposta, 'Prontuário')

    def test_dashboard_do_dentista_exibe_apenas_rotina_clinica_vinculada(self):
        self.consulta_um.data = timezone.localdate()
        self.consulta_um.status = Consulta.Status.PRESENTE
        self.consulta_um.save(update_fields=['data', 'status'])
        self.consulta_dois.data = timezone.localdate()
        self.consulta_dois.save(update_fields=['data'])
        FichaCadastroAnamnese.objects.create(
            paciente=self.paciente_um,
            dentista=self.dentista_um,
            status=FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA,
            nome_completo=self.paciente_um.nome_completo,
            data_nascimento=self.paciente_um.data_nascimento,
            cpf=self.paciente_um.cpf,
            telefone=self.paciente_um.telefone,
        )
        FichaAutorizacaoCusto.objects.create(
            paciente=self.paciente_um,
            consulta=self.consulta_um,
            nome_completo=self.paciente_um.nome_completo,
            data_nascimento=self.paciente_um.data_nascimento,
            cpf=self.paciente_um.cpf,
        )

        self.client.force_login(self.dentista_user)
        resposta = self.client.get(reverse('core:inicio'))

        self.assertContains(resposta, 'Rotina clínica')
        self.assertContains(resposta, 'Agenda clínica de hoje')
        self.assertContains(resposta, 'Em atendimento')
        self.assertContains(resposta, 'Anamneses pendentes')
        self.assertContains(resposta, 'Documentos pendentes')
        self.assertContains(resposta, self.paciente_um.nome_completo)
        self.assertNotContains(resposta, self.paciente_dois.nome_completo)
        self.assertNotContains(resposta, 'Pagamentos')
        self.assertNotContains(resposta, 'Financeiro atual')
        self.assertNotContains(resposta, 'Administração técnica')

    def test_ficha_separa_contextos_sem_ampliar_permissoes(self):
        ficha = reverse('core:ficha_consulta', args=[self.consulta_um.pk])
        AuditoriaConsulta.objects.create(
            consulta=self.consulta_um,
            usuario=self.admin,
            descricao='status alterado para agendada',
        )

        self.client.force_login(self.secretaria)
        resposta = self.client.get(ficha)
        self.assertContains(resposta, 'Resumo da consulta')
        self.assertContains(resposta, 'Atendimento')
        self.assertNotContains(resposta, 'Prontuário e documentos')
        self.assertNotContains(resposta, 'Financeiro da consulta')
        self.assertNotContains(resposta, 'Auditoria')

        self.client.force_login(self.dentista_user)
        resposta = self.client.get(ficha)
        self.assertContains(resposta, 'Prontuário e documentos')
        self.assertContains(resposta, 'Operação da própria consulta')
        self.assertNotContains(resposta, 'Financeiro da consulta')
        self.assertNotContains(resposta, 'Auditoria')

        self.client.force_login(self.admin)
        resposta = self.client.get(ficha)
        self.assertContains(resposta, 'Prontuário e documentos')
        self.assertContains(resposta, 'Financeiro da consulta')
        self.assertContains(resposta, 'Auditoria')
