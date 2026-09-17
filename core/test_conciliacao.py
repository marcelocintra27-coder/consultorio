from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .conciliacao import registrar_importacao_arquivo
from .models import (
    AjusteConciliacao,
    AuditoriaConciliacao,
    Conciliacao,
    ContaReceber,
    ImportacaoExtrato,
    ItemConciliacao,
    LancamentoExtrato,
    Paciente,
    ParcelaContaReceber,
    RecebimentoPaciente,
)


class ConciliacaoTests(TestCase):
    def setUp(self):
        sala = Sala.objects.create(nome='Sala Conciliação')
        self.dentista = Dentista.objects.create(nome_completo='Dentista Conciliação', sala=sala)
        self.admin = User.objects.create_superuser('admin_conciliacao', 'admin@example.com', 'x')
        self.dentista_user = User.objects.create_user('dentista_conciliacao', password='x')
        PerfilUsuario.objects.create(usuario=self.dentista_user, dentista=self.dentista, papel=PerfilUsuario.Papel.DENTISTA)
        self.secretaria = User.objects.create_user('secretaria_conciliacao', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.auxiliar = User.objects.create_user('auxiliar_conciliacao', password='x')
        PerfilUsuario.objects.create(usuario=self.auxiliar, dentista=self.dentista, papel=PerfilUsuario.Papel.AUXILIAR)
        self.staff = User.objects.create_user('staff_conciliacao', password='x', is_staff=True)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Conciliação', cpf='961.000.000-01',
            data_nascimento=date(1980, 1, 1), telefone='11900000001',
        )

    def _recebimento(self, valor=Decimal('100.00')):
        conta = ContaReceber.objects.create(
            paciente=self.paciente, descricao='Tratamento conciliável',
            valor_original=valor, criado_por=self.admin,
        )
        parcela = ParcelaContaReceber.objects.create(
            conta=conta, numero=1, vencimento=timezone.localdate(), valor_original=valor,
        )
        return RecebimentoPaciente.objects.create(
            parcela=parcela, tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
            valor=valor, desconto=Decimal('0.00'),
            forma_pagamento='pix', operador=self.admin,
        )

    def _origem_manual(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('core:criar_importacao_extrato_manual'), {
            'instituicao': 'Banco Teste', 'conta_referencia': 'Conta final 1234',
            'periodo_inicial': timezone.localdate(), 'periodo_final': timezone.localdate(),
        })
        self.assertEqual(resposta.status_code, 302)
        return ImportacaoExtrato.objects.order_by('-pk').first()

    def _lancamento(self, valor='100.00'):
        importacao = self._origem_manual()
        resposta = self.client.post(
            reverse('core:criar_lancamento_extrato_manual', args=[importacao.pk]),
            {
                'referencia_externa': 'E2E-123', 'data': timezone.localdate(),
                'descricao': 'PIX recebido', 'natureza': 'entrada', 'valor': valor,
                'saldo_informado': '',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        return LancamentoExtrato.objects.get(importacao=importacao)

    def test_conciliacao_manual_total_preserva_recebimento_e_audita(self):
        recebimento = self._recebimento()
        lancamento = self._lancamento()
        resposta = self.client.post(reverse('core:conciliar_lancamento_extrato', args=[lancamento.pk]), {
            'recebimento': recebimento.pk, 'baixa': '', 'movimento_caixa': '',
            'repasse_uniodonto': '', 'valor_conciliado': '100.00',
        })
        self.assertEqual(resposta.status_code, 302)
        conciliacao = Conciliacao.objects.get(lancamento_extrato=lancamento)
        self.assertEqual(conciliacao.situacao, Conciliacao.Situacao.CONCILIADA)
        self.assertEqual(conciliacao.valor_conciliado, Decimal('100.00'))
        self.assertTrue(RecebimentoPaciente.objects.filter(pk=recebimento.pk).exists())
        self.assertTrue(AuditoriaConciliacao.objects.filter(conciliacao=conciliacao, acao='item_confirmado').exists())

    def test_conciliacao_parcial_e_impede_origem_duplicada(self):
        recebimento = self._recebimento(Decimal('100.00'))
        lancamento = self._lancamento('100.00')
        self.assertEqual(self.client.post(reverse('core:conciliar_lancamento_extrato', args=[lancamento.pk]), {
            'recebimento': recebimento.pk, 'baixa': '', 'movimento_caixa': '',
            'repasse_uniodonto': '', 'valor_conciliado': '60.00',
        }).status_code, 302)
        conciliacao = Conciliacao.objects.get(lancamento_extrato=lancamento)
        self.assertEqual(conciliacao.situacao, Conciliacao.Situacao.PARCIAL)

        segundo_recebimento = self._recebimento(Decimal('40.00'))
        self.assertEqual(self.client.post(reverse('core:conciliar_lancamento_extrato', args=[lancamento.pk]), {
            'recebimento': segundo_recebimento.pk, 'baixa': '', 'movimento_caixa': '',
            'repasse_uniodonto': '', 'valor_conciliado': '40.00',
        }).status_code, 302)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.situacao, Conciliacao.Situacao.CONCILIADA)

        outro = self._lancamento('50.00')
        resposta = self.client.post(reverse('core:conciliar_lancamento_extrato', args=[outro.pk]), {
            'recebimento': recebimento.pk, 'baixa': '', 'movimento_caixa': '',
            'repasse_uniodonto': '', 'valor_conciliado': '50.00',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'valor conciliado suficiente')
        self.assertEqual(ItemConciliacao.objects.filter(ativo=True).count(), 2)

    def test_divergencia_e_cancelamento_sao_eventos_logicos_auditaveis(self):
        recebimento = self._recebimento()
        lancamento = self._lancamento()
        self.client.post(reverse('core:conciliar_lancamento_extrato', args=[lancamento.pk]), {
            'recebimento': recebimento.pk, 'baixa': '', 'movimento_caixa': '',
            'repasse_uniodonto': '', 'valor_conciliado': '100.00',
        })
        conciliacao = Conciliacao.objects.get(lancamento_extrato=lancamento)
        self.assertEqual(self.client.post(reverse('core:registrar_ajuste_conciliacao', args=[conciliacao.pk]), {
            'tipo': AjusteConciliacao.Tipo.TAXA_PIX, 'valor': '2.50', 'motivo': 'Taxa informada no extrato',
        }).status_code, 302)
        self.assertEqual(AjusteConciliacao.objects.get().valor, Decimal('2.50'))
        self.assertEqual(self.client.post(reverse('core:registrar_ajuste_conciliacao', args=[conciliacao.pk]), {
            'tipo': AjusteConciliacao.Tipo.DIVERGENCIA, 'valor': '1.00', 'motivo': 'Diferença identificada',
        }).status_code, 302)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.situacao, Conciliacao.Situacao.DIVERGENTE)
        self.assertEqual(self.client.post(reverse('core:cancelar_conciliacao', args=[conciliacao.pk]), {
            'motivo': 'Lançamento bancário duplicado',
        }).status_code, 302)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.situacao, Conciliacao.Situacao.CANCELADA)
        self.assertFalse(conciliacao.itens.get().ativo)
        self.assertTrue(RecebimentoPaciente.objects.filter(pk=recebimento.pk).exists())
        self.assertTrue(AuditoriaConciliacao.objects.filter(conciliacao=conciliacao, acao='cancelada_logicamente').exists())

    def test_csv_e_ofx_preparados_para_importacao_bloqueiam_mesmo_arquivo(self):
        conteudo = 'data,descricao,valor,natureza,referencia\n2026-09-12,Pix recebido,45.00,entrada,abc-123\n'
        importacao = registrar_importacao_arquivo(
            instituicao='Banco Teste', conta_referencia='Conta 1234',
            formato=ImportacaoExtrato.Formato.CSV, conteudo=conteudo, usuario=self.admin,
        )
        self.assertEqual(importacao.lancamentos.count(), 1)
        self.assertTrue(
            AuditoriaConciliacao.objects.filter(
                importacao=importacao, acao='arquivo_importado'
            ).exists()
        )
        with self.assertRaises(ValidationError):
            registrar_importacao_arquivo(
                instituicao='Banco Teste', conta_referencia='Conta 1234',
                formato=ImportacaoExtrato.Formato.CSV, conteudo=conteudo, usuario=self.admin,
            )
        ofx = '<STMTTRN><DTPOSTED>20260912<TRNAMT>-10.00<FITID>ofx-1<MEMO>Tarifa</STMTTRN>'
        importacao_ofx = registrar_importacao_arquivo(
            instituicao='Banco Teste', conta_referencia='Conta 1234',
            formato=ImportacaoExtrato.Formato.OFX, conteudo=ofx, usuario=self.admin,
        )
        self.assertEqual(importacao_ofx.lancamentos.get().natureza, 'saida')

    def test_rotas_sao_exclusivas_do_administrador(self):
        urls = [
            reverse('core:listar_conciliacoes'),
            reverse('core:criar_importacao_extrato_manual'),
        ]
        for usuario in (self.dentista_user, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
