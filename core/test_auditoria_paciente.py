from datetime import date
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import AuditoriaPaciente, Paciente


def _dados_tela(**extra):
    dados = {
        'nome_completo': 'Paciente Auditoria',
        'cpf': '801.000.000-10',
        'data_nascimento': '12/05/1980',
        'telefone': '11911111111',
        'whatsapp': '',
        'email': '',
        'endereco': '',
        'convenio': '',
        'carteirinha': '',
        'observacoes': '',
        'instagram': '',
        'facebook': '',
        'outra_rede_social': '',
    }
    dados.update(extra)
    return dados


def _dados_admin(paciente, **extra):
    dados = {
        'nome_completo': paciente.nome_completo,
        'cpf': paciente.cpf or '',
        'data_nascimento': paciente.data_nascimento.isoformat(),
        'telefone': paciente.telefone,
        'whatsapp': paciente.whatsapp,
        'email': paciente.email,
        'endereco': paciente.endereco,
        'convenio': paciente.convenio_id or '',
        'carteirinha': paciente.carteirinha,
        'observacoes': paciente.observacoes,
        'instagram': paciente.instagram,
        'facebook': paciente.facebook,
        'outra_rede_social': paciente.outra_rede_social,
    }
    if paciente.ativo:
        dados['ativo'] = 'on'
    dados.update(extra)
    return dados


class AuditoriaPacienteTests(TestCase):
    def setUp(self):
        self.secretaria = User.objects.create_user('secretaria_auditoria', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        sala = Sala.objects.create(nome='Sala auditoria')
        dentista = Dentista.objects.create(nome_completo='Dentista auditoria', sala=sala)
        self.dentista = User.objects.create_user('dentista_auditoria', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=dentista,
        )
        self.auxiliar = User.objects.create_user('auxiliar_auditoria', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            papel=PerfilUsuario.Papel.AUXILIAR,
            dentista=dentista,
        )
        self.admin = User.objects.create_superuser('admin_auditoria', password='x')
        self.staff = User.objects.create_user(
            'staff_auditoria', password='x', is_staff=True,
        )

    def _paciente(self, **extra):
        dados = {
            'nome_completo': 'Paciente Já Existente',
            'cpf': '801.000.000-11',
            'data_nascimento': date(1981, 2, 2),
            'telefone': '11922222222',
        }
        dados.update(extra)
        return Paciente.objects.create(**dados)

    def test_cadastro_pela_tela_grava_criado_com_o_usuario(self):
        self.client.force_login(self.secretaria)
        resposta = self.client.post(
            reverse('core:cadastrar_paciente'), _dados_tela(),
        )
        self.assertEqual(resposta.status_code, 302)
        paciente = Paciente.objects.get(cpf='801.000.000-10')
        auditoria = AuditoriaPaciente.objects.get()
        self.assertEqual(auditoria.paciente, paciente)
        self.assertEqual(auditoria.usuario, self.secretaria)
        self.assertEqual(auditoria.acao, AuditoriaPaciente.Acao.CRIADO)
        self.assertEqual(auditoria.origem, AuditoriaPaciente.Origem.TELA)
        self.assertEqual(
            auditoria.alteracoes['nome_completo'],
            {'antes': None, 'depois': 'Paciente Auditoria'},
        )
        self.assertEqual(
            auditoria.alteracoes['telefone'],
            {'antes': None, 'depois': '11911111111'},
        )
        self.assertEqual(
            auditoria.alteracoes['data_nascimento'],
            {'antes': None, 'depois': '1980-05-12'},
        )
        self.assertEqual(
            auditoria.alteracoes['ativo'],
            {'antes': None, 'depois': True},
        )
        self.assertIsNotNone(auditoria.criado_em)

    def test_edicao_que_muda_campo_grava_antes_e_depois(self):
        paciente = self._paciente()
        self.client.force_login(self.secretaria)
        resposta = self.client.post(
            reverse('core:editar_paciente', args=[paciente.pk]),
            _dados_tela(
                nome_completo=paciente.nome_completo,
                cpf=paciente.cpf,
                data_nascimento='02/02/1981',
                telefone='11933333333',
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        paciente.refresh_from_db()
        self.assertEqual(paciente.telefone, '11933333333')
        auditoria = AuditoriaPaciente.objects.get()
        self.assertEqual(auditoria.acao, AuditoriaPaciente.Acao.ALTERADO)
        self.assertEqual(auditoria.origem, AuditoriaPaciente.Origem.TELA)
        self.assertEqual(auditoria.usuario, self.secretaria)
        self.assertEqual(
            auditoria.alteracoes,
            {'telefone': {'antes': '11922222222', 'depois': '11933333333'}},
        )

    def test_edicao_sem_mudanca_nao_grava_auditoria(self):
        paciente = self._paciente()
        self.client.force_login(self.secretaria)
        resposta = self.client.post(
            reverse('core:editar_paciente', args=[paciente.pk]),
            _dados_tela(
                nome_completo=paciente.nome_completo,
                cpf=paciente.cpf,
                data_nascimento='02/02/1981',
                telefone=paciente.telefone,
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(AuditoriaPaciente.objects.exists())

    def test_admin_grava_alteracao_desativacao_e_cadastro(self):
        paciente = self._paciente()
        self.assertFalse(AuditoriaPaciente.objects.exists())
        self.client.force_login(self.admin)
        alteracao = self.client.post(
            reverse('admin:core_paciente_change', args=[paciente.pk]),
            _dados_admin(paciente, nome_completo='Nome alterado no admin'),
        )
        self.assertEqual(alteracao.status_code, 302, alteracao.content)
        auditoria = AuditoriaPaciente.objects.get()
        self.assertEqual(auditoria.usuario, self.admin)
        self.assertEqual(auditoria.acao, AuditoriaPaciente.Acao.ALTERADO)
        self.assertEqual(auditoria.origem, AuditoriaPaciente.Origem.ADMINISTRACAO)
        self.assertEqual(
            auditoria.alteracoes['nome_completo'],
            {'antes': 'Paciente Já Existente', 'depois': 'Nome Alterado No Admin'},
        )

        paciente.refresh_from_db()
        dados = _dados_admin(paciente)
        dados.pop('ativo')
        desativacao = self.client.post(
            reverse('admin:core_paciente_change', args=[paciente.pk]),
            dados,
        )
        self.assertEqual(desativacao.status_code, 302, desativacao.content)
        paciente.refresh_from_db()
        self.assertFalse(paciente.ativo)
        baixa = AuditoriaPaciente.objects.exclude(pk=auditoria.pk).get()
        self.assertEqual(baixa.acao, AuditoriaPaciente.Acao.DESATIVADO)
        self.assertEqual(baixa.origem, AuditoriaPaciente.Origem.ADMINISTRACAO)
        self.assertEqual(
            baixa.alteracoes['ativo'],
            {'antes': True, 'depois': False},
        )

        cadastro = self.client.post(
            reverse('admin:core_paciente_add'),
            _dados_admin(paciente, nome_completo='Paciente criado no admin', cpf='801.000.000-12'),
        )
        self.assertEqual(cadastro.status_code, 302, cadastro.content)
        novo = Paciente.objects.get(cpf='801.000.000-12')
        criada = AuditoriaPaciente.objects.get(paciente=novo)
        self.assertEqual(criada.acao, AuditoriaPaciente.Acao.CRIADO)
        self.assertEqual(criada.origem, AuditoriaPaciente.Origem.ADMINISTRACAO)
        self.assertEqual(criada.usuario, self.admin)
        self.assertEqual(
            criada.alteracoes['nome_completo'],
            {'antes': None, 'depois': 'Paciente Criado No Admin'},
        )

    def test_auditoria_e_somente_leitura_no_admin(self):
        self.client.force_login(self.secretaria)
        self.client.post(reverse('core:cadastrar_paciente'), _dados_tela())
        auditoria = AuditoriaPaciente.objects.get()
        original = dict(auditoria.alteracoes)
        change = reverse('admin:core_auditoriapaciente_change', args=[auditoria.pk])
        delete = reverse('admin:core_auditoriapaciente_delete', args=[auditoria.pk])
        adicionar = reverse('admin:core_auditoriapaciente_add')

        self.client.force_login(self.admin)
        modeladmin = admin.site._registry[AuditoriaPaciente]
        pedido = type('Pedido', (), {'user': self.admin})()
        self.assertFalse(modeladmin.has_add_permission(pedido))
        self.assertFalse(modeladmin.has_change_permission(pedido, auditoria))
        self.assertFalse(modeladmin.has_delete_permission(pedido, auditoria))
        self.assertEqual(
            modeladmin.list_filter, ('paciente', 'usuario', 'acao', 'criado_em'),
        )
        self.assertEqual(self.client.get(change).status_code, 200)
        self.assertEqual(self.client.post(change, {'acao': 'criado'}).status_code, 403)
        self.assertEqual(self.client.post(delete, {'post': 'yes'}).status_code, 403)
        self.assertEqual(self.client.get(adicionar).status_code, 403)
        auditoria.refresh_from_db()
        self.assertEqual(auditoria.alteracoes, original)
        self.assertEqual(auditoria.acao, AuditoriaPaciente.Acao.CRIADO)
        self.assertTrue(AuditoriaPaciente.objects.filter(pk=auditoria.pk).exists())

    def test_secretaria_dentista_auxiliar_e_staff_nao_veem_auditoria(self):
        self.client.force_login(self.secretaria)
        self.client.post(reverse('core:cadastrar_paciente'), _dados_tela())
        lista = reverse('admin:core_auditoriapaciente_changelist')
        for usuario in (self.secretaria, self.dentista, self.auxiliar):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(lista).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(lista).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(lista).status_code, 200)

    def test_falha_na_auditoria_nao_salva_o_paciente(self):
        self.client.force_login(self.secretaria)
        with patch(
            'core.auditoria_paciente.AuditoriaPaciente.objects.create',
            side_effect=RuntimeError('falha de auditoria'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('core:cadastrar_paciente'), _dados_tela())
        self.assertFalse(Paciente.objects.filter(cpf='801.000.000-10').exists())

        paciente = self._paciente()
        with patch(
            'core.auditoria_paciente.AuditoriaPaciente.objects.create',
            side_effect=RuntimeError('falha de auditoria'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse('core:editar_paciente', args=[paciente.pk]),
                    _dados_tela(
                        nome_completo=paciente.nome_completo,
                        cpf=paciente.cpf,
                        data_nascimento='02/02/1981',
                        telefone='11999999999',
                    ),
                )
        paciente.refresh_from_db()
        self.assertEqual(paciente.telefone, '11922222222')
        self.assertFalse(AuditoriaPaciente.objects.exists())
