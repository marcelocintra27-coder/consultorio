from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import CategoriaContaPagar, ContaPagar, Fornecedor
from .models import AuditoriaDespesa, Dentista, Despesa, Sala


class DespesasFinanceiroTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala despesas')
        self.dentista = Dentista.objects.create(nome_completo='Dentista', sala=self.sala)
        self.admin = User.objects.create_superuser('admin_despesa', 'a@x.com', 'x')
        self.fornecedor = Fornecedor.objects.create(nome='Fornecedor despesa')
        self.categoria = CategoriaContaPagar.objects.create(nome='Categoria despesa')

    def _conta(self, valor=Decimal('100.00')):
        return ContaPagar.objects.create(
            fornecedor=self.fornecedor, categoria=self.categoria, descricao='Conta ligada',
            competencia=timezone.localdate(), vencimento=timezone.localdate() + timedelta(days=1),
            valor_original=valor, responsavel=self.admin,
            situacao=ContaPagar.Situacao.APROVADA, aprovado_por=self.admin,
            aprovado_em=timezone.now(),
        )

    def test_despesa_nova_vincula_conta_sem_alterar_competencia(self):
        conta = self._conta()
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('locacao:cadastrar_despesa'), {
            'descricao': 'Rateio novo', 'valor': '100.00', 'competencia': '2026-09',
            'tipo': Despesa.Tipo.COMPARTILHADA, 'pago_por': self.dentista.pk,
            'conta_pagar': conta.pk, 'observacoes': '',
        })
        self.assertEqual(resposta.status_code, 302)
        despesa = Despesa.objects.get(descricao='Rateio novo')
        self.assertEqual(despesa.conta_pagar, conta)
        self.assertEqual(despesa.competencia.isoformat(), '2026-09-01')
        self.assertTrue(AuditoriaDespesa.objects.filter(despesa=despesa).exists())

    def test_valor_diferente_da_conta_e_rejeitado(self):
        conta = self._conta()
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('locacao:cadastrar_despesa'), {
            'descricao': 'Inválida', 'valor': '99.00', 'competencia': '2026-09',
            'tipo': Despesa.Tipo.INDIVIDUAL, 'pago_por': self.dentista.pk,
            'conta_pagar': conta.pk, 'observacoes': '',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'deve coincidir')
        self.assertFalse(Despesa.objects.filter(descricao='Inválida').exists())

    def test_historica_sem_vinculo_e_rateio_sao_preservados(self):
        despesa = Despesa.objects.create(descricao='Histórica', valor=Decimal('90'), competencia=timezone.localdate(), tipo=Despesa.Tipo.COMPARTILHADA, pago_por=self.dentista)
        self.assertIsNone(despesa.conta_pagar_id)
        self.assertEqual(despesa.valor_cota(), Decimal('90.00'))

    def test_data_pagamento_vem_da_baixa_e_nao_da_competencia(self):
        conta = self._conta()
        despesa = Despesa.objects.create(descricao='Ligada', valor=Decimal('100'), competencia=timezone.localdate(), pago_por=self.dentista, conta_pagar=conta)
        self.assertIsNone(despesa.data_efetiva_pagamento)

    def test_despesas_exigem_administrador(self):
        usuario = User.objects.create_user('comum_despesa', password='x')
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('locacao:listar_despesas')).status_code, 403)
