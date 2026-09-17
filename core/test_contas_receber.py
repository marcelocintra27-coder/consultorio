from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AuditoriaFinanceira,
    ContaReceber,
    ParcelaContaReceber,
    RecebimentoPaciente,
    Consulta,
    Paciente,
)


class ContasReceberTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Financeira')
        self.dentista = Dentista.objects.create(
            nome_completo='Dentista Financeiro', sala=sala
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Financeiro',
            cpf='901.000.000-01',
            data_nascimento=date(1980, 1, 1),
            telefone='11900000001',
        )
        self.consulta = Consulta.objects.create(
            paciente=self.paciente,
            dentista=self.dentista,
            data=date(2026, 9, 11),
            hora_inicio=time(9),
            hora_fim=time(10),
            pago=True,
            forma_pagamento=Consulta.FormaPagamento.PIX,
        )
        self.admin = User.objects.create_superuser(
            'admin_financeiro', 'admin@example.com', 'x'
        )
        self.dentista_user = User.objects.create_user('dentista_financeiro', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_financeira', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.auxiliar = User.objects.create_user('auxiliar_financeiro', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.staff = User.objects.create_user(
            'staff_financeiro', password='x', is_staff=True
        )

    def _conta(self, valor=Decimal('100.00')):
        conta = ContaReceber.objects.create(
            paciente=self.paciente,
            consulta=self.consulta,
            descricao='Tratamento financeiro',
            data_emissao=date(2026, 9, 11),
            valor_original=valor,
            criado_por=self.admin,
        )
        parcela = ParcelaContaReceber.objects.create(
            conta=conta,
            numero=1,
            vencimento=date(2026, 10, 10),
            valor_original=valor,
        )
        return conta, parcela

    def test_cria_conta_e_parcelas_sem_alterar_pagamento_legado(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse('core:criar_conta_receber'),
            {
                'paciente': self.paciente.pk,
                'consulta': self.consulta.pk,
                'descricao': 'Tratamento parcelado',
                'data_emissao': '2026-09-11',
                'parcelas-TOTAL_FORMS': '2',
                'parcelas-INITIAL_FORMS': '0',
                'parcelas-MIN_NUM_FORMS': '1',
                'parcelas-MAX_NUM_FORMS': '1000',
                'parcelas-0-vencimento': '2026-10-10',
                'parcelas-0-valor_original': '60.00',
                'parcelas-1-vencimento': '2026-11-10',
                'parcelas-1-valor_original': '40.00',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        conta = ContaReceber.objects.get(descricao='Tratamento parcelado')
        self.assertEqual(conta.valor_original, Decimal('100.00'))
        self.assertEqual(conta.parcelas.count(), 2)
        self.assertEqual(conta.saldo, Decimal('100.00'))
        self.assertEqual(conta.situacao, 'aberta')
        self.assertTrue(
            AuditoriaFinanceira.objects.filter(
                conta=conta, acao=AuditoriaFinanceira.Acao.CONTA_CRIADA
            ).exists()
        )
        self.consulta.refresh_from_db()
        self.assertTrue(self.consulta.pago)
        self.assertEqual(self.consulta.forma_pagamento, Consulta.FormaPagamento.PIX)

    def test_baixa_parcial_total_e_desconto_recalculam_saldo(self):
        conta, parcela = self._conta()
        self.client.force_login(self.admin)
        url = reverse('core:registrar_recebimento', args=[parcela.pk])

        resposta = self.client.post(
            url,
            {
                'valor': '40.00',
                'desconto': '10.00',
                'forma_pagamento': Consulta.FormaPagamento.PIX,
                'observacoes': 'Entrada e desconto autorizado',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        parcela.refresh_from_db()
        self.assertEqual(parcela.saldo, Decimal('50.00'))
        self.assertEqual(parcela.situacao, 'parcial')

        resposta = self.client.post(
            url,
            {
                'valor': '50.00',
                'desconto': '0.00',
                'forma_pagamento': Consulta.FormaPagamento.DINHEIRO,
                'observacoes': '',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        parcela.refresh_from_db()
        conta.refresh_from_db()
        self.assertEqual(parcela.saldo, Decimal('0.00'))
        self.assertEqual(parcela.situacao, 'liquidada')
        self.assertEqual(conta.saldo, Decimal('0.00'))
        self.assertEqual(conta.situacao, 'liquidada')
        self.assertEqual(
            AuditoriaFinanceira.objects.filter(
                conta=conta,
                acao=AuditoriaFinanceira.Acao.RECEBIMENTO_REGISTRADO,
            ).count(),
            2,
        )

    def test_recebimento_acima_do_saldo_e_rejeitado(self):
        _, parcela = self._conta()
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse('core:registrar_recebimento', args=[parcela.pk]),
            {
                'valor': '100.01',
                'desconto': '0.00',
                'forma_pagamento': Consulta.FormaPagamento.PIX,
                'observacoes': '',
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'não pode exceder o saldo')
        self.assertEqual(RecebimentoPaciente.objects.count(), 0)

    def test_estorno_cria_evento_compensatorio_sem_apagar_recebimento(self):
        conta, parcela = self._conta()
        recebimento = RecebimentoPaciente.objects.create(
            parcela=parcela,
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=Decimal('70.00'),
            desconto=Decimal('0.00'),
            forma_pagamento=Consulta.FormaPagamento.PIX,
            operador=self.admin,
        )
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse('core:estornar_recebimento', args=[recebimento.pk]),
            {'valor': '20.00', 'observacoes': 'Devolução parcial'},
        )
        self.assertEqual(resposta.status_code, 302)
        estorno = RecebimentoPaciente.objects.get(
            tipo=RecebimentoPaciente.Tipo.ESTORNO
        )
        self.assertEqual(estorno.recebimento_original_id, recebimento.pk)
        self.assertTrue(RecebimentoPaciente.objects.filter(pk=recebimento.pk).exists())
        parcela.refresh_from_db()
        self.assertEqual(parcela.saldo, Decimal('50.00'))
        self.assertTrue(
            AuditoriaFinanceira.objects.filter(
                conta=conta,
                recebimento=estorno,
                acao=AuditoriaFinanceira.Acao.ESTORNO_REGISTRADO,
            ).exists()
        )

        resposta = self.client.post(
            reverse('core:estornar_recebimento', args=[recebimento.pk]),
            {'valor': '51.00', 'observacoes': 'Excede o valor recebido'},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'não pode exceder o valor ainda estornável')
        self.assertEqual(
            RecebimentoPaciente.objects.filter(
                tipo=RecebimentoPaciente.Tipo.ESTORNO
            ).count(),
            1,
        )

    def test_recibo_tem_numero_unico_e_acesso_exclusivo_do_administrador(self):
        _, parcela = self._conta()
        recebimento = RecebimentoPaciente.objects.create(
            parcela=parcela,
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=Decimal('25.00'),
            desconto=Decimal('0.00'),
            forma_pagamento=Consulta.FormaPagamento.CARTAO_CREDITO,
            operador=self.admin,
        )
        self.assertTrue(recebimento.numero_recibo.startswith('RCB-'))

        self.client.force_login(self.admin)
        resposta = self.client.get(
            reverse('core:ver_recibo_recebimento', args=[recebimento.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, recebimento.numero_recibo)

        self.client.force_login(self.secretaria)
        self.assertEqual(
            self.client.get(
                reverse('core:ver_recibo_recebimento', args=[recebimento.pk])
            ).status_code,
            403,
        )

    def test_rotas_financeiras_sao_negadas_a_perfis_nao_administradores(self):
        _, parcela = self._conta()
        urls = [
            reverse('core:listar_contas_receber'),
            reverse('core:criar_conta_receber'),
            reverse('core:registrar_recebimento', args=[parcela.pk]),
        ]
        for usuario in (self.dentista_user, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_estorno_exige_recebimento_original_da_mesma_parcela(self):
        _, parcela_um = self._conta()
        outra_conta, parcela_dois = self._conta(Decimal('80.00'))
        original = RecebimentoPaciente.objects.create(
            parcela=parcela_um,
            tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=Decimal('10.00'),
            desconto=Decimal('0.00'),
            forma_pagamento=Consulta.FormaPagamento.PIX,
            operador=self.admin,
        )
        estorno_invalido = RecebimentoPaciente(
            parcela=parcela_dois,
            tipo=RecebimentoPaciente.Tipo.ESTORNO,
            valor=Decimal('5.00'),
            desconto=Decimal('0.00'),
            operador=self.admin,
            recebimento_original=original,
        )
        with self.assertRaisesMessage(Exception, 'mesma parcela'):
            estorno_invalido.full_clean()
        self.assertEqual(outra_conta.saldo, Decimal('80.00'))
