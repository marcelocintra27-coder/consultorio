from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, Despesa, DividaAvulsa, PagamentoPar, Sala
from locacao.models import PerfilUsuario

from .models import (
    AuditoriaContaPagar,
    BaixaContaPagar,
    CategoriaContaPagar,
    ContaPagar,
    Fornecedor,
)


class ContasPagarTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Contas a Pagar')
        self.dentista = Dentista.objects.create(nome_completo='Dentista Financeiro', sala=sala)
        outra_sala = Sala.objects.create(nome='Outra sala Contas a Pagar')
        self.outro_dentista = Dentista.objects.create(
            nome_completo='Outra Dentista', sala=outra_sala
        )
        self.admin = User.objects.create_superuser('admin_pagar', 'admin@example.com', 'x')
        self.dentista_user = User.objects.create_user('dentista_pagar', password='x')
        PerfilUsuario.objects.create(usuario=self.dentista_user, dentista=self.dentista, papel=PerfilUsuario.Papel.DENTISTA)
        self.secretaria = User.objects.create_user('secretaria_pagar', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.auxiliar = User.objects.create_user('auxiliar_pagar', password='x')
        PerfilUsuario.objects.create(usuario=self.auxiliar, dentista=self.dentista, papel=PerfilUsuario.Papel.AUXILIAR)
        self.staff = User.objects.create_user('staff_pagar', password='x', is_staff=True)
        self.fornecedor = Fornecedor.objects.create(nome='Fornecedor de materiais')
        self.categoria = CategoriaContaPagar.objects.create(nome='Materiais administrativos')

    def _conta(self, valor=Decimal('100.00'), situacao=ContaPagar.Situacao.PENDENTE_APROVACAO):
        conta = ContaPagar.objects.create(
            fornecedor=self.fornecedor,
            categoria=self.categoria,
            descricao='Compra administrativa',
            competencia=timezone.localdate(),
            vencimento=timezone.localdate() + timedelta(days=10),
            valor_original=valor,
            recorrencia=ContaPagar.Recorrencia.MENSAL,
            situacao=situacao,
            responsavel=self.admin,
            aprovado_por=self.admin if situacao != ContaPagar.Situacao.PENDENTE_APROVACAO else None,
            aprovado_em=timezone.now() if situacao != ContaPagar.Situacao.PENDENTE_APROVACAO else None,
        )
        return conta

    def _aprovar(self, conta):
        self.client.force_login(self.admin)
        return self.client.post(reverse('core:aprovar_conta_pagar', args=[conta.pk]))

    def _baixa(self, conta, valor, chave=None):
        self.client.force_login(self.admin)
        return self.client.post(
            reverse('core:registrar_baixa_conta_pagar', args=[conta.pk]),
            {'valor': valor, 'chave_operacao': chave or uuid4(), 'observacoes': 'Baixa testada'},
        )

    def test_cria_conta_pagar_aguardando_aprovacao_e_audita(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('core:criar_conta_pagar'), {
            'fornecedor': self.fornecedor.pk,
            'categoria': self.categoria.pk,
            'descricao': 'Assinatura administrativa',
            'competencia': timezone.localdate().isoformat(),
            'vencimento': (timezone.localdate() + timedelta(days=5)).isoformat(),
            'valor_original': '150.00',
            'recorrencia': ContaPagar.Recorrencia.MENSAL,
            'observacoes': '',
        })
        self.assertEqual(resposta.status_code, 302)
        conta = ContaPagar.objects.get(descricao='Assinatura administrativa')
        self.assertEqual(conta.situacao, ContaPagar.Situacao.PENDENTE_APROVACAO)
        self.assertEqual(conta.responsavel, self.admin)
        self.assertTrue(AuditoriaContaPagar.objects.filter(conta=conta, acao=AuditoriaContaPagar.Acao.CONTA_CRIADA).exists())

    def test_fornecedor_e_categoria_sao_cadastros_administrativos(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('core:cadastrar_fornecedor'), {'nome': 'Fornecedor novo', 'documento': '', 'contato': '', 'ativo': 'on'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('core:cadastrar_categoria_conta_pagar'), {'nome': 'Serviços', 'ativa': 'on'}).status_code, 302)
        self.assertTrue(Fornecedor.objects.filter(nome='Fornecedor novo').exists())
        self.assertTrue(CategoriaContaPagar.objects.filter(nome='Serviços').exists())

    def test_aprovacao_registra_aprovador_e_nao_duplica(self):
        conta = self._conta()
        self.assertEqual(self._aprovar(conta).status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.situacao, ContaPagar.Situacao.APROVADA)
        self.assertEqual(conta.aprovado_por, self.admin)
        self.assertIsNotNone(conta.aprovado_em)
        self.assertEqual(self._aprovar(conta).status_code, 302)
        self.assertEqual(AuditoriaContaPagar.objects.filter(conta=conta, acao=AuditoriaContaPagar.Acao.CONTA_APROVADA).count(), 1)

    def test_baixa_e_negada_antes_da_aprovacao(self):
        conta = self._conta()
        resposta = self._baixa(conta, '10.00')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Somente uma conta aprovada')
        self.assertEqual(BaixaContaPagar.objects.count(), 0)

    def test_baixa_parcial_mantem_saldo_e_auditoria(self):
        conta = self._conta()
        self._aprovar(conta)
        self.assertEqual(self._baixa(conta, '40.00').status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.saldo, Decimal('60.00'))
        self.assertEqual(conta.situacao, ContaPagar.Situacao.APROVADA)
        self.assertTrue(AuditoriaContaPagar.objects.filter(conta=conta, acao=AuditoriaContaPagar.Acao.BAIXA_REGISTRADA).exists())

    def test_baixa_total_liquida_conta(self):
        conta = self._conta()
        self._aprovar(conta)
        self._baixa(conta, '100.00')
        conta.refresh_from_db()
        self.assertEqual(conta.saldo, Decimal('0.00'))
        self.assertEqual(conta.situacao, ContaPagar.Situacao.PAGA)

    def test_baixa_acima_do_saldo_e_rejeitada(self):
        conta = self._conta()
        self._aprovar(conta)
        resposta = self._baixa(conta, '100.01')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'não pode exceder o saldo')
        self.assertEqual(BaixaContaPagar.objects.count(), 0)

    def test_chave_de_operacao_impede_baixa_duplicada(self):
        conta = self._conta()
        self._aprovar(conta)
        chave = uuid4()
        self.assertEqual(self._baixa(conta, '30.00', chave).status_code, 302)
        resposta = self._baixa(conta, '30.00', chave)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'operação já foi registrada')
        self.assertEqual(BaixaContaPagar.objects.filter(conta=conta).count(), 1)

    def test_recorrencia_e_apenas_informativa_sem_criar_novo_titulo(self):
        conta = self._conta()
        self.assertEqual(conta.recorrencia, ContaPagar.Recorrencia.MENSAL)
        self.assertEqual(ContaPagar.objects.count(), 1)

    def test_preserva_despesa_divida_e_acerto_legados(self):
        despesa = Despesa.objects.create(
            descricao='Despesa de locação', valor=Decimal('70.00'),
            competencia=timezone.localdate(), pago_por=self.dentista,
        )
        divida = DividaAvulsa.objects.create(
            descricao='Dívida de locação', valor=Decimal('30.00'),
            competencia=timezone.localdate(), de_dentista=self.dentista,
            para_dentista=self.outro_dentista,
        )
        pagamento = PagamentoPar.objects.create(
            de_dentista=self.dentista, para_dentista=self.outro_dentista,
            valor=Decimal('20.00'), competencia=timezone.localdate(),
        )
        conta = self._conta()
        self._aprovar(conta)
        self._baixa(conta, '100.00')
        despesa.refresh_from_db(); divida.refresh_from_db(); pagamento.refresh_from_db()
        self.assertEqual(despesa.valor, Decimal('70.00'))
        self.assertEqual(divida.valor, Decimal('30.00'))
        self.assertEqual(pagamento.valor, Decimal('20.00'))

    def test_rotas_de_contas_pagar_sao_exclusivas_do_administrador(self):
        conta = self._conta()
        urls = [
            reverse('core:listar_contas_pagar'), reverse('core:criar_conta_pagar'),
            reverse('core:listar_fornecedores'), reverse('core:listar_categorias_conta_pagar'),
            reverse('core:detalhe_conta_pagar', args=[conta.pk]),
        ]
        for usuario in (self.dentista_user, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_telas_de_contas_pagar_nao_possuem_upload_de_comprovante(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('core:criar_conta_pagar'))
        self.assertNotContains(resposta, 'type="file"')
