import tempfile
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AtividadeDiaria,
    AuditoriaConsulta,
    AuditoriaPaciente,
    Consulta,
    DigitalizacaoFicha,
    Paciente,
    RegistroAcesso,
)

SP = ZoneInfo('America/Sao_Paulo')


class Relogio:
    def __init__(self, momento):
        self.instante = momento.astimezone(UTC)

    def agora(self):
        return self.instante

    def avancar(self, **delta):
        self.instante += timedelta(**delta)


class RegistroAcessoTests(TestCase):
    def test_login_logout_e_senha_errada_nao_guardam_senha(self):
        senha = 'segredo-unico-nao-gravar'
        errada = 'tentativa-errada-xyz'
        usuaria = User.objects.create_user('amanda', password=senha)
        self.assertEqual(
            self.client.post(reverse('entrar'), {
                'username': 'amanda', 'password': senha,
            }).status_code,
            302,
        )
        entrada = RegistroAcesso.objects.get(tipo=RegistroAcesso.Tipo.ENTROU)
        self.assertEqual(entrada.usuario, usuaria)
        self.assertEqual(entrada.usuario_digitado, '')
        self.assertIsNotNone(entrada.criado_em)

        self.assertEqual(
            self.client.post(reverse('entrar'), {
                'username': 'amanda', 'password': errada,
            }).status_code,
            200,
        )
        falha = RegistroAcesso.objects.get(tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU)
        self.assertIsNone(falha.usuario_id)
        self.assertEqual(falha.usuario_digitado, 'amanda')

        self.client.force_login(usuaria)
        self.assertEqual(self.client.get(reverse('sair')).status_code, 302)
        saida = RegistroAcesso.objects.get(tipo=RegistroAcesso.Tipo.SAIU)
        self.assertEqual(saida.usuario, usuaria)

        nomes = {campo.name for campo in RegistroAcesso._meta.fields}
        self.assertFalse(nomes & {'senha', 'password', 'ip', 'endereco_ip'})
        for registro in RegistroAcesso.objects.all():
            self.assertNotIn(senha, registro.usuario_digitado)
            self.assertNotIn(errada, registro.usuario_digitado)

    def test_aviso_aparece_na_tela_de_login(self):
        resposta = self.client.get(reverse('entrar'))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta, 'Os acessos e as ações neste sistema são registrados.',
        )


class AtividadeDiariaMiddlewareTests(TestCase):
    def test_intervalo_de_cinco_minutos_e_dia_de_sao_paulo(self):
        usuaria = User.objects.create_user('turno', password='x')
        self.client.force_login(usuaria)
        relogio = Relogio(datetime(2026, 9, 28, 21, 30, tzinfo=SP))
        with patch('django.utils.timezone.now', relogio.agora):
            self.assertEqual(self.client.get(reverse('core:inicio')).status_code, 200)
            registro = AtividadeDiaria.objects.get()
            self.assertEqual(registro.usuario, usuaria)
            self.assertEqual(registro.data, date(2026, 9, 28))
            self.assertEqual(registro.primeira_atividade, relogio.instante)
            self.assertEqual(registro.ultima_atividade, relogio.instante)

            relogio.avancar(minutes=4)
            self.client.get(reverse('core:inicio'))
            registro.refresh_from_db()
            self.assertEqual(registro.ultima_atividade, relogio.instante - timedelta(minutes=4))
            self.assertEqual(AtividadeDiaria.objects.count(), 1)

            relogio.avancar(minutes=2)
            self.client.get(reverse('core:inicio'))
            registro.refresh_from_db()
            self.assertEqual(registro.primeira_atividade, relogio.instante - timedelta(minutes=6))
            self.assertEqual(registro.ultima_atividade, relogio.instante)
            self.assertEqual(registro.data, date(2026, 9, 28))

            relogio.instante = datetime(2026, 9, 29, 0, 1, tzinfo=SP).astimezone(UTC)
            self.client.get(reverse('core:inicio'))
            self.assertEqual(AtividadeDiaria.objects.count(), 2)
            novo = AtividadeDiaria.objects.get(data=date(2026, 9, 29))
            self.assertEqual(novo.primeira_atividade, relogio.instante)
            self.assertEqual(novo.ultima_atividade, relogio.instante)
            registro.refresh_from_db()
            self.assertEqual(registro.data, date(2026, 9, 28))


class RelatorioAtividadeTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ajuste = override_settings(MEDIA_ROOT=self.tmp.name)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        sala = Sala.objects.create(nome='Sala atividade')
        dentista = Dentista.objects.create(nome_completo='Dentista atividade', sala=sala)
        self.secretaria = User.objects.create_user(
            'secretaria_atividade', password='x', first_name='Ana', last_name='Souza',
        )
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.dentista = User.objects.create_user('dentista_atividade', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista, papel=PerfilUsuario.Papel.DENTISTA, dentista=dentista,
        )
        self.auxiliar = User.objects.create_user('auxiliar_atividade', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar, papel=PerfilUsuario.Papel.AUXILIAR, dentista=dentista,
        )
        self.staff = User.objects.create_user(
            'staff_atividade', password='x', is_staff=True,
        )
        self.admin = User.objects.create_superuser('admin_atividade', password='x')
        self.instante = datetime(2026, 9, 28, 21, 30, tzinfo=SP)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente da Atividade',
            cpf='802.000.000-10',
            data_nascimento=date(1980, 5, 12),
            telefone='11900000000',
        )

    def _no_instante(self, modelo, pk, campo):
        modelo.objects.filter(pk=pk).update(**{campo: self.instante})

    def _montar_dia(self):
        AtividadeDiaria.objects.create(
            usuario=self.secretaria,
            data=date(2026, 9, 28),
            primeira_atividade=self.instante,
            ultima_atividade=self.instante,
        )
        for _ in range(2):
            acesso = RegistroAcesso.objects.create(
                usuario=self.secretaria, tipo=RegistroAcesso.Tipo.ENTROU,
            )
            self._no_instante(RegistroAcesso, acesso.pk, 'criado_em')
        falha = RegistroAcesso.objects.create(
            usuario_digitado=self.secretaria.username,
            tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU,
        )
        self._no_instante(RegistroAcesso, falha.pk, 'criado_em')
        outra = RegistroAcesso.objects.create(
            usuario_digitado='intruso',
            tipo=RegistroAcesso.Tipo.TENTATIVA_FALHOU,
        )
        self._no_instante(RegistroAcesso, outra.pk, 'criado_em')
        criado = AuditoriaPaciente.objects.create(
            paciente=self.paciente,
            usuario=self.secretaria,
            acao=AuditoriaPaciente.Acao.CRIADO,
            origem=AuditoriaPaciente.Origem.TELA,
            alteracoes={'nome_completo': {'antes': None, 'depois': 'Paciente da Atividade'}},
        )
        self._no_instante(AuditoriaPaciente, criado.pk, 'criado_em')
        alterado = AuditoriaPaciente.objects.create(
            paciente=self.paciente,
            usuario=self.secretaria,
            acao=AuditoriaPaciente.Acao.ALTERADO,
            origem=AuditoriaPaciente.Origem.TELA,
            alteracoes={'telefone': {'antes': '1', 'depois': '2'}},
        )
        self._no_instante(AuditoriaPaciente, alterado.pk, 'criado_em')
        consulta = Consulta.objects.create(
            paciente=self.paciente,
            data=date(2026, 9, 28),
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
        )
        auditoria = AuditoriaConsulta.objects.create(
            consulta=consulta,
            usuario=self.secretaria,
            descricao='Confirmou a consulta',
        )
        self._no_instante(AuditoriaConsulta, auditoria.pk, 'cadastrado_em')
        foto = DigitalizacaoFicha.objects.create(
            paciente=self.paciente,
            imagem=SimpleUploadedFile('ficha.png', b'png', 'image/png'),
            digitalizado_por=self.secretaria,
        )
        self._no_instante(DigitalizacaoFicha, foto.pk, 'criado_em')

    def _abrir(self, **params):
        self.client.force_login(self.admin)
        return self.client.get(reverse('core:relatorio_atividade'), params)

    def test_relatorio_soma_acoes_no_dia_local(self):
        self._montar_dia()
        resposta = self._abrir(data_inicial='2026-09-28', data_final='2026-09-28')
        self.assertEqual(resposta.status_code, 200)
        linhas = [
            linha for linha in resposta.context['linhas']
            if linha['usuario'] == self.secretaria
        ]
        self.assertEqual(len(linhas), 1)
        linha = linhas[0]
        self.assertEqual(linha['entradas'], 2)
        self.assertEqual(linha['tentativas'], 1)
        self.assertEqual(linha['pacientes_cadastrados'], 1)
        self.assertEqual(linha['pacientes_alterados'], 1)
        self.assertEqual(linha['consultas'], 1)
        self.assertEqual(linha['fotos'], 1)
        self.assertContains(resposta, '21:30')
        self.assertContains(resposta, 'Ana Souza')

        dia_seguinte = self._abrir(data_inicial='2026-09-29', data_final='2026-09-29')
        self.assertFalse([
            linha for linha in dia_seguinte.context['linhas']
            if linha['usuario'] == self.secretaria
        ])

        detalhe = self.client.get(reverse(
            'core:relatorio_atividade_dia',
            args=[self.secretaria.pk, '2026-09-28'],
        ))
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, 'Entrou no sistema')
        self.assertContains(detalhe, 'Senha incorreta')
        self.assertContains(detalhe, 'Cadastrou o paciente Paciente da Atividade')
        self.assertContains(detalhe, 'Alterou o paciente Paciente da Atividade')
        self.assertContains(detalhe, 'Confirmou a consulta')
        self.assertContains(detalhe, 'Enviou foto de ficha de Paciente da Atividade')
        self.assertContains(detalhe, '21:30')

        csv = self.client.get(reverse('core:relatorio_atividade_csv'), {
            'data_inicial': '2026-09-28', 'data_final': '2026-09-28',
        })
        self.assertEqual(csv.status_code, 200)
        texto = csv.content.decode('utf-8-sig')
        self.assertIn('Ana Souza', texto)
        self.assertIn('28/09/2026', texto)
        self.assertIn('21:30', texto)
        self.assertIn('Pacientes cadastrados', texto)

    def test_outros_perfis_recebem_403_no_relatorio_e_no_csv(self):
        relatorio = reverse('core:relatorio_atividade')
        arquivo = reverse('core:relatorio_atividade_csv')
        for usuario in (self.secretaria, self.auxiliar, self.dentista, self.staff):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(relatorio).status_code, 403)
            self.assertEqual(self.client.get(arquivo).status_code, 403)

    def test_menu_do_administrador_tem_o_link(self):
        self.client.force_login(self.admin)
        pagina = self.client.get(reverse('core:inicio'))
        self.assertContains(pagina, 'Relatório de atividade')
        self.assertContains(pagina, reverse('core:relatorio_atividade'))
        self.client.force_login(self.secretaria)
        pagina = self.client.get(reverse('core:inicio'))
        self.assertNotContains(pagina, reverse('core:relatorio_atividade'))

    def test_admin_nao_edita_nem_apaga_os_registros(self):
        acesso = RegistroAcesso.objects.create(
            usuario=self.admin, tipo=RegistroAcesso.Tipo.ENTROU,
        )
        atividade = AtividadeDiaria.objects.create(
            usuario=self.admin,
            data=date(2026, 9, 28),
            primeira_atividade=self.instante,
            ultima_atividade=self.instante,
        )
        self.client.force_login(self.admin)
        for modelo, obj in ((RegistroAcesso, acesso), (AtividadeDiaria, atividade)):
            change = reverse(
                f'admin:core_{modelo._meta.model_name}_change', args=[obj.pk],
            )
            delete = reverse(
                f'admin:core_{modelo._meta.model_name}_delete', args=[obj.pk],
            )
            modeladmin = admin.site._registry[modelo]
            pedido = type('Pedido', (), {'user': self.admin})()
            self.assertFalse(modeladmin.has_add_permission(pedido))
            self.assertFalse(modeladmin.has_change_permission(pedido, obj))
            self.assertFalse(modeladmin.has_delete_permission(pedido, obj))
            self.assertEqual(self.client.post(change, {'tipo': 'saiu'}).status_code, 403)
            self.assertEqual(self.client.post(delete, {'post': 'yes'}).status_code, 403)
        acesso.refresh_from_db()
        self.assertEqual(acesso.tipo, RegistroAcesso.Tipo.ENTROU)
        self.assertTrue(AtividadeDiaria.objects.filter(pk=atividade.pk).exists())
        self.assertEqual(
            self.client.get(reverse('admin:core_registroacesso_changelist')).status_code,
            200,
        )
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse('admin:core_registroacesso_changelist')).status_code,
            403,
        )
        self.client.force_login(self.secretaria)
        self.assertEqual(
            self.client.get(reverse('admin:core_registroacesso_changelist')).status_code,
            302,
        )
