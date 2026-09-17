from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AuditoriaFinanceira,
    ContaReceber,
    ParcelaContaReceber,
    RecebimentoPaciente,
    Paciente,
)


class InadimplenciaTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Inadimplência')
        dentista = Dentista.objects.create(nome_completo='Dentista Financeiro', sala=sala)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Inadimplente',
            cpf='950.000.000-01',
            data_nascimento=timezone.localdate() - timedelta(days=12000),
            telefone='11900000001',
        )
        self.outro_paciente = Paciente.objects.create(
            nome_completo='Paciente Pontual',
            cpf='950.000.000-02',
            data_nascimento=timezone.localdate() - timedelta(days=11000),
            telefone='11900000002',
        )
        self.admin = User.objects.create_superuser('admin_inad', 'admin@example.com', 'x')
        self.dentista_user = User.objects.create_user('dentista_inad', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user,
            dentista=dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_inad', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.auxiliar = User.objects.create_user('auxiliar_inad', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            dentista=dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.staff = User.objects.create_user('staff_inad', password='x', is_staff=True)

    def _parcela(self, *, vencimento, valor=Decimal('100.00'), paciente=None, descricao='Tratamento pendente'):
        conta = ContaReceber.objects.create(
            paciente=paciente or self.paciente,
            descricao=descricao,
            data_emissao=timezone.localdate(),
            valor_original=valor,
            criado_por=self.admin,
        )
        return ParcelaContaReceber.objects.create(
            conta=conta,
            numero=1,
            vencimento=vencimento,
            valor_original=valor,
        )

    def _recebimento(self, parcela, valor, desconto=Decimal('0.00')):
        return RecebimentoPaciente.objects.create(
            parcela=parcela,
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=valor,
            desconto=desconto,
            forma_pagamento='pix',
            operador=self.admin,
        )

    def _listar(self, **params):
        self.client.force_login(self.admin)
        return self.client.get(reverse('core:listar_inadimplencia'), params)

    def test_parcela_vencida_em_aberto_e_listada_com_dias_de_atraso(self):
        vencimento = timezone.localdate() - timedelta(days=10)
        self._parcela(vencimento=vencimento)

        resposta = self._listar()

        self.assertContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, '10 dias')
        self.assertContains(resposta, 'R$ 100,00')

    def test_parcela_com_vencimento_hoje_nao_e_inadimplente(self):
        self._parcela(vencimento=timezone.localdate())

        resposta = self._listar()

        self.assertNotContains(resposta, self.paciente.nome_completo)

    def test_parcela_parcialmente_paga_permanece_inadimplente_com_saldo(self):
        parcela = self._parcela(vencimento=timezone.localdate() - timedelta(days=20))
        self._recebimento(parcela, Decimal('40.00'))

        resposta = self._listar()

        self.assertContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, 'R$ 60,00')

    def test_parcela_liquidada_nao_e_listada(self):
        parcela = self._parcela(vencimento=timezone.localdate() - timedelta(days=20))
        self._recebimento(parcela, Decimal('100.00'))

        resposta = self._listar()

        self.assertNotContains(resposta, self.paciente.nome_completo)

    def test_desconto_que_liquida_a_parcela_nao_gera_inadimplencia(self):
        parcela = self._parcela(vencimento=timezone.localdate() - timedelta(days=20))
        self._recebimento(parcela, Decimal('1.00'), Decimal('99.00'))

        resposta = self._listar()

        self.assertNotContains(resposta, self.paciente.nome_completo)

    def test_estorno_reabre_saldo_e_recoloca_parcela_na_inadimplencia(self):
        parcela = self._parcela(vencimento=timezone.localdate() - timedelta(days=20))
        original = self._recebimento(parcela, Decimal('100.00'))
        RecebimentoPaciente.objects.create(
            parcela=parcela,
            tipo=RecebimentoPaciente.Tipo.ESTORNO,
            valor=Decimal('30.00'),
            desconto=Decimal('0.00'),
            operador=self.admin,
            recebimento_original=original,
        )

        resposta = self._listar()

        self.assertContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, 'R$ 30,00')

    def test_filtro_por_faixa_de_atraso(self):
        self._parcela(vencimento=timezone.localdate() - timedelta(days=15))
        self._parcela(
            vencimento=timezone.localdate() - timedelta(days=45),
            paciente=self.outro_paciente,
            descricao='Tratamento antigo',
        )

        resposta = self._listar(faixa='31-60')

        self.assertNotContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, self.outro_paciente.nome_completo)

    def test_filtro_por_paciente_ou_descricao(self):
        self._parcela(vencimento=timezone.localdate() - timedelta(days=15))
        self._parcela(
            vencimento=timezone.localdate() - timedelta(days=15),
            paciente=self.outro_paciente,
            descricao='Outro tratamento',
        )

        resposta = self._listar(q='Outro tratamento')

        self.assertNotContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, self.outro_paciente.nome_completo)

    def test_historico_financeiro_existente_do_titulo_e_exibido(self):
        parcela = self._parcela(vencimento=timezone.localdate() - timedelta(days=10))
        AuditoriaFinanceira.objects.create(
            conta=parcela.conta,
            parcela=parcela,
            usuario=self.admin,
            acao=AuditoriaFinanceira.Acao.CONTA_CRIADA,
            descricao='Título criado para acompanhamento financeiro.',
        )

        resposta = self._listar()

        self.assertContains(resposta, 'Histórico financeiro')
        self.assertContains(resposta, 'Título criado para acompanhamento financeiro.')

    def test_inadimplencia_e_exclusiva_do_administrador(self):
        self._parcela(vencimento=timezone.localdate() - timedelta(days=10))
        url = reverse('core:listar_inadimplencia')

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        for usuario in (self.dentista_user, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(url).status_code, 403)
