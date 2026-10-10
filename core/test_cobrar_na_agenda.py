"""Atalho "Cobrar" na agenda: abre a cobrança e volta para a agenda ao salvar."""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, LancamentoAtendimento, Paciente, PrecoProcedimento, Procedimento


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CobrarNaAgendaTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala A')
        outra = Sala.objects.create(nome='Sala B')
        self.dentista = Dentista.objects.create(nome_completo='Dra. A', sala=sala)
        self.outra_dentista = Dentista.objects.create(nome_completo='Dra. B', sala=outra)
        self.procedimento = Procedimento.objects.create(
            dentista=self.dentista, nome='Limpeza', duracao_estimada_minutos=60,
        )
        PrecoProcedimento.objects.create(procedimento=self.procedimento, valor=Decimal('200.00'))
        paciente = Paciente.objects.create(
            nome_completo='Maria Exemplo', cpf='123.456.789-09',
            data_nascimento=date(1990, 1, 1), telefone='62999990000',
        )
        self.dia = date(2026, 10, 12)
        self.consulta = Consulta.objects.create(
            paciente=paciente, dentista=self.dentista, data=self.dia,
            hora_inicio=time(9), hora_fim=time(10),
        )
        self.consulta_outra = Consulta.objects.create(
            paciente=paciente, dentista=self.outra_dentista, data=self.dia,
            hora_inicio=time(11), hora_fim=time(12),
        )
        self.admin = User.objects.create_superuser('admin_cobrar', password='x')
        self.usuario_dentista = User.objects.create_user('dra_a', password='x')
        PerfilUsuario.objects.create(
            usuario=self.usuario_dentista, papel=PerfilUsuario.Papel.DENTISTA, dentista=self.dentista,
        )
        self.secretaria = User.objects.create_user('sec_cobrar', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.agenda = f'/consultas/?data={self.dia.isoformat()}'
        self.atalho = f'/consultas/{self.consulta.pk}/?voltar=agenda#form-lancamento'

    def _payload(self, **extra):
        dados = {
            'procedimento': self.procedimento.pk, 'convenio': '',
            'valor_tabela': '200.00', 'percentual_desconto': '0',
            'valor_final': '200.00', 'tipo': 'atendimento',
        }
        dados.update(extra)
        return dados

    def test_admin_ve_cobrar_em_todas_as_consultas(self):
        self.client.force_login(self.admin)
        html = self.client.get(self.agenda).content.decode()
        self.assertEqual(html.count('>Cobrar</a>'), 2)
        self.assertIn(self.atalho, html)

    def test_dentista_ve_cobrar_so_na_propria_consulta(self):
        self.client.force_login(self.usuario_dentista)
        html = self.client.get(self.agenda).content.decode()
        self.assertEqual(html.count('>Cobrar</a>'), 1)
        self.assertIn(self.atalho, html)

    def test_secretaria_nao_ve_cobrar(self):
        self.client.force_login(self.secretaria)
        html = self.client.get(self.agenda).content.decode()
        self.assertNotIn('>Cobrar</a>', html)

    def test_atalho_abre_formulario_com_aviso_e_volta_para_agenda(self):
        self.client.force_login(self.admin)
        html = self.client.get(
            f'/consultas/{self.consulta.pk}/?voltar=agenda'
        ).content.decode()
        self.assertIn('name="voltar" value="agenda"', html)
        resposta = self.client.post(
            f'/consultas/{self.consulta.pk}/lancar/', self._payload(voltar='agenda'), follow=True,
        )
        self.assertEqual(resposta.redirect_chain[-1][0], self.agenda)
        self.assertContains(resposta, 'Cobrança salva: Maria Exemplo — Limpeza — R$ 200,00.')
        self.assertEqual(LancamentoAtendimento.objects.filter(consulta=self.consulta).count(), 1)

    def test_sem_atalho_continua_voltando_para_a_consulta(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(f'/consultas/{self.consulta.pk}/lancar/', self._payload())
        self.assertEqual(resposta['Location'], f'/consultas/{self.consulta.pk}/')

    def test_erro_no_formulario_mantem_o_caminho_de_volta(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/consultas/{self.consulta.pk}/lancar/', self._payload(valor_final='', voltar='agenda'),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'name="voltar" value="agenda"')
        self.assertFalse(LancamentoAtendimento.objects.exists())

    def test_desconto_com_muitas_casas_avisa_em_portugues_simples(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/consultas/{self.consulta.pk}/lancar/',
            self._payload(percentual_desconto='0.00000', voltar='agenda'),
        )
        self.assertContains(resposta, 'A cobrança ainda não foi salva.')
        self.assertContains(resposta, 'Use no máximo 2 casas depois da vírgula')
        self.assertFalse(LancamentoAtendimento.objects.exists())
