from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AuditoriaCaixa,
    BaixaContaPagar,
    CaixaDiario,
    CategoriaContaPagar,
    Consulta,
    ContaPagar,
    ContaReceber,
    Fornecedor,
    MovimentoCaixa,
    Paciente,
    ParcelaContaReceber,
    RecebimentoPaciente,
)


class CaixaTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Caixa')
        self.dentista = Dentista.objects.create(
            nome_completo='Dentista Caixa', sala=sala
        )
        self.admin = User.objects.create_superuser('admin_caixa', 'a@x.com', 'x')
        self.dentista_user = User.objects.create_user('dentista_caixa', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_caixa', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA
        )
        self.auxiliar = User.objects.create_user('auxiliar_caixa', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.staff = User.objects.create_user(
            'staff_caixa', password='x', is_staff=True
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Caixa',
            cpf='981.000.000-01',
            data_nascimento=date(1980, 1, 1),
            telefone='11900000001',
        )

    def abrir(self, saldo='10.00'):
        self.client.force_login(self.admin)
        return self.client.post(
            reverse('core:abrir_caixa'),
            {'data': timezone.localdate(), 'saldo_inicial': saldo},
        )

    def _parcela_receber(self, valor=Decimal('100.00')):
        consulta = Consulta.objects.create(
            paciente=self.paciente,
            dentista=self.dentista,
            data=timezone.localdate(),
            hora_inicio=time(9),
            hora_fim=time(10),
        )
        conta = ContaReceber.objects.create(
            paciente=self.paciente,
            consulta=consulta,
            descricao='Tratamento para caixa',
            valor_original=valor,
            criado_por=self.admin,
        )
        return ParcelaContaReceber.objects.create(
            conta=conta,
            numero=1,
            vencimento=timezone.localdate(),
            valor_original=valor,
        )

    def _conta_pagar_aprovada(self, valor=Decimal('60.00')):
        fornecedor = Fornecedor.objects.create(nome='Fornecedor Caixa')
        categoria = CategoriaContaPagar.objects.create(nome='Categoria Caixa')
        return ContaPagar.objects.create(
            fornecedor=fornecedor,
            categoria=categoria,
            descricao='Conta para caixa',
            competencia=timezone.localdate(),
            vencimento=timezone.localdate(),
            valor_original=valor,
            situacao=ContaPagar.Situacao.APROVADA,
            responsavel=self.admin,
            aprovado_por=self.admin,
            aprovado_em=timezone.now(),
        )

    def test_abertura_unica_e_ajuste_auditado(self):
        self.assertEqual(self.abrir().status_code, 302)
        caixa = CaixaDiario.objects.get()
        self.assertEqual(self.abrir().status_code, 200)
        resposta = self.client.post(
            reverse('core:movimento_manual_caixa', args=[caixa.pk]),
            {'tipo': 'ajuste_entrada', 'valor': '5.00', 'motivo': 'Troco inicial'},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(caixa.saldo_esperado, Decimal('15.00'))
        self.assertTrue(AuditoriaCaixa.objects.exists())

    def test_recebimento_e_baixa_alimentam_caixa_aberto_sem_duplicidade(self):
        self.abrir('0.00')
        caixa = CaixaDiario.objects.get()
        parcela = self._parcela_receber()
        resposta = self.client.post(
            reverse('core:registrar_recebimento', args=[parcela.pk]),
            {
                'valor': '100.00',
                'desconto': '0.00',
                'forma_pagamento': Consulta.FormaPagamento.PIX,
                'observacoes': 'Recebimento testado',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        recebimento = RecebimentoPaciente.objects.get()
        movimento_recebimento = MovimentoCaixa.objects.get(recebido=recebimento)
        self.assertEqual(
            movimento_recebimento.tipo, MovimentoCaixa.Tipo.ENTRADA_AUTOMATICA
        )

        resposta = self.client.post(
            reverse('core:estornar_recebimento', args=[recebimento.pk]),
            {'valor': '20.00', 'observacoes': 'Estorno testado'},
        )
        self.assertEqual(resposta.status_code, 302)
        estorno = RecebimentoPaciente.objects.get(
            tipo=RecebimentoPaciente.Tipo.ESTORNO
        )
        movimento_estorno = MovimentoCaixa.objects.get(recebido=estorno)
        self.assertEqual(movimento_estorno.tipo, MovimentoCaixa.Tipo.SAIDA_AUTOMATICA)

        conta_pagar = self._conta_pagar_aprovada()
        resposta = self.client.post(
            reverse('core:registrar_baixa_conta_pagar', args=[conta_pagar.pk]),
            {
                'valor': '60.00',
                'chave_operacao': uuid4(),
                'observacoes': 'Baixa testada',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        baixa = BaixaContaPagar.objects.get()
        movimento_baixa = MovimentoCaixa.objects.get(baixa=baixa)
        self.assertEqual(movimento_baixa.tipo, MovimentoCaixa.Tipo.SAIDA_AUTOMATICA)
        self.assertEqual(caixa.saldo_esperado, Decimal('20.00'))
        self.assertEqual(MovimentoCaixa.objects.count(), 3)
        self.assertEqual(AuditoriaCaixa.objects.filter(caixa=caixa).count(), 4)

    def test_fechamento_exige_justificativa_e_e_imutavel(self):
        self.abrir('0.00')
        caixa = CaixaDiario.objects.get()
        resposta = self.client.post(
            reverse('core:fechar_caixa', args=[caixa.pk]),
            {'saldo_contado': '1.00', 'justificativa_diferenca': ''},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse('core:fechar_caixa', args=[caixa.pk]),
                {
                    'saldo_contado': '1.00',
                    'justificativa_diferenca': 'Conferência manual',
                },
            ).status_code,
            302,
        )
        caixa.refresh_from_db()
        self.assertEqual(caixa.situacao, CaixaDiario.Situacao.FECHADO)
        self.assertEqual(
            self.client.post(
                reverse('core:movimento_manual_caixa', args=[caixa.pk]),
                {'tipo': 'ajuste_entrada', 'valor': '1.00', 'motivo': 'Correção'},
            ).status_code,
            200,
        )
        self.assertEqual(MovimentoCaixa.objects.count(), 0)

    def test_caixa_e_exclusivo_do_administrador(self):
        urls = [reverse('core:caixa_diario'), reverse('core:abrir_caixa')]
        for usuario in (
            self.dentista_user,
            self.secretaria,
            self.auxiliar,
            self.staff,
        ):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
