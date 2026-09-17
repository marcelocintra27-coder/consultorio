from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, Despesa, PerfilUsuario, Sala

from .models import (
    AjusteConciliacao,
    CaixaDiario,
    CategoriaContaPagar,
    Conciliacao,
    ContaPagar,
    ContaReceber,
    Fornecedor,
    ImportacaoExtrato,
    LancamentoExtrato,
    MovimentoCaixa,
    Paciente,
    ParcelaContaReceber,
    RecebimentoPaciente,
)


class RelatoriosFinanceirosTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        sala = Sala.objects.create(nome='Sala relatórios')
        self.dentista = Dentista.objects.create(nome_completo='Dentista relatórios', sala=sala)
        self.admin = User.objects.create_superuser('admin_relatorios', 'admin@example.com', 'x')
        self.dentista_user = User.objects.create_user('dentista_relatorios', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user, dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_relatorios', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.auxiliar = User.objects.create_user('auxiliar_relatorios', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar, dentista=self.dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.staff = User.objects.create_user('staff_relatorios', password='x', is_staff=True)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente relatórios', cpf='960.000.000-01',
            data_nascimento=self.hoje - timedelta(days=12000), telefone='11900000000',
        )
        self.fornecedor = Fornecedor.objects.create(nome='Fornecedor relatórios')
        self.categoria = CategoriaContaPagar.objects.create(nome='Operação')

    def _parcela(self, valor=Decimal('120.00'), vencimento=None):
        conta = ContaReceber.objects.create(
            paciente=self.paciente, descricao='Tratamento',
            data_emissao=self.hoje, valor_original=valor, criado_por=self.admin,
        )
        return ParcelaContaReceber.objects.create(
            conta=conta, numero=1, vencimento=vencimento or self.hoje,
            valor_original=valor,
        )

    def _conta_pagar(self, valor=Decimal('80.00')):
        return ContaPagar.objects.create(
            fornecedor=self.fornecedor, categoria=self.categoria,
            descricao='Insumos', competencia=self.hoje, vencimento=self.hoje,
            valor_original=valor, responsavel=self.admin,
        )

    def _relatorio(self, inicio=None, fim=None):
        self.client.force_login(self.admin)
        return self.client.get(reverse('core:relatorios_financeiros'), {
            'data_inicial': inicio or self.hoje.replace(day=1).isoformat(),
            'data_final': fim or self.hoje.isoformat(),
        })

    def test_realizado_e_previsto_usam_fontes_separadas(self):
        caixa = CaixaDiario.objects.create(
            data=self.hoje, saldo_inicial=Decimal('0.00'), aberto_por=self.admin,
        )
        MovimentoCaixa.objects.create(
            caixa=caixa, tipo=MovimentoCaixa.Tipo.ENTRADA_AUTOMATICA,
            valor=Decimal('100.00'), usuario=self.admin,
        )
        MovimentoCaixa.objects.create(
            caixa=caixa, tipo=MovimentoCaixa.Tipo.SAIDA_AUTOMATICA,
            valor=Decimal('40.00'), usuario=self.admin,
        )
        self._parcela(Decimal('120.00'))
        self._conta_pagar(Decimal('80.00'))
        Despesa.objects.create(
            descricao='Despesa histórica', valor=Decimal('15.00'), competencia=self.hoje,
            pago_por=self.dentista,
        )

        resposta = self._relatorio()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['resultado_realizado'], Decimal('60.00'))
        self.assertEqual(resposta.context['resultado_previsto'], Decimal('25.00'))

    def test_despesa_vinculada_nao_duplica_com_conta_pagar(self):
        conta = self._conta_pagar(Decimal('80.00'))
        Despesa.objects.create(
            descricao='Despesa vinculada', valor=Decimal('80.00'), competencia=self.hoje,
            pago_por=self.dentista, conta_pagar=conta,
        )
        Despesa.objects.create(
            descricao='Despesa histórica', valor=Decimal('20.00'), competencia=self.hoje,
            pago_por=self.dentista,
        )

        resposta = self._relatorio()

        self.assertEqual(resposta.context['previsto_pagar_contas'], Decimal('80.00'))
        self.assertEqual(resposta.context['previsto_despesas_legadas'], Decimal('20.00'))
        self.assertEqual(resposta.context['resultado_previsto'], Decimal('-100.00'))

    def test_recebimentos_estornos_descontos_taxas_e_divergencias_sao_separados(self):
        parcela = self._parcela()
        original = RecebimentoPaciente.objects.create(
            parcela=parcela, tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=Decimal('100.00'), desconto=Decimal('10.00'),
            forma_pagamento='pix', operador=self.admin,
        )
        RecebimentoPaciente.objects.create(
            parcela=parcela, tipo=RecebimentoPaciente.Tipo.ESTORNO,
            valor=Decimal('20.00'), desconto=Decimal('0.00'), operador=self.admin,
            recebimento_original=original,
        )
        importacao = ImportacaoExtrato.objects.create(
            instituicao='Banco', conta_referencia='Conta', criado_por=self.admin,
        )
        lancamento = LancamentoExtrato.objects.create(
            importacao=importacao, indice_origem=1, data=self.hoje,
            descricao='Recebimento', natureza=LancamentoExtrato.Natureza.ENTRADA,
            valor=Decimal('80.00'),
        )
        conciliacao = Conciliacao.objects.create(
            lancamento_extrato=lancamento, criado_por=self.admin,
        )
        AjusteConciliacao.objects.create(
            conciliacao=conciliacao, tipo=AjusteConciliacao.Tipo.TAXA_PIX,
            valor=Decimal('2.00'), motivo='Taxa Pix', criado_por=self.admin,
        )
        AjusteConciliacao.objects.create(
            conciliacao=conciliacao, tipo=AjusteConciliacao.Tipo.DIVERGENCIA,
            valor=Decimal('3.00'), motivo='Diferença informada', criado_por=self.admin,
        )

        resposta = self._relatorio()

        grupo = resposta.context['recebimentos_por_forma'][0]
        self.assertEqual(grupo['recebido'], Decimal('100.00'))
        self.assertEqual(grupo['estornado'], Decimal('20.00'))
        self.assertEqual(grupo['desconto'], Decimal('10.00'))
        self.assertEqual(grupo['liquido'], Decimal('70.00'))
        self.assertEqual(resposta.context['taxas_conciliacao'], Decimal('2.00'))
        self.assertEqual(resposta.context['divergencias_conciliacao'], Decimal('3.00'))

    def test_vencidos_no_periodo_respeitam_saldo_atual(self):
        vencimento = self.hoje - timedelta(days=1)
        parcela_aberta = self._parcela(Decimal('50.00'), vencimento)
        parcela_liquidada = self._parcela(Decimal('30.00'), vencimento)
        RecebimentoPaciente.objects.create(
            parcela=parcela_liquidada, tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=Decimal('30.00'), desconto=Decimal('0.00'),
            forma_pagamento='dinheiro', operador=self.admin,
        )

        resposta = self._relatorio(vencimento.isoformat(), self.hoje.isoformat())

        self.assertEqual(resposta.context['quantidade_vencida'], 1)
        self.assertEqual(resposta.context['saldo_vencido'], parcela_aberta.saldo)

    def test_relatorios_sao_exclusivos_do_administrador(self):
        url = reverse('core:relatorios_financeiros')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        for usuario in (self.dentista_user, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(url).status_code, 403)
