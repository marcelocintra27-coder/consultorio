from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    AuditoriaFormaPagamento,
    ContaReceber,
    FormaPagamentoConfiguravel,
    MovimentoCaixa,
    Paciente,
    ParcelaContaReceber,
    RecebimentoPaciente,
)


class FormasPagamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for codigo, nome in (
            ('pix', 'Pix'),
            ('dinheiro', 'Dinheiro'),
            ('cartao_debito', 'Cartão de Débito'),
            ('cartao_credito', 'Cartão de Crédito'),
            ('transferencia', 'Transferência'),
        ):
            FormaPagamentoConfiguravel.objects.get_or_create(
                codigo=codigo, defaults={'nome': nome, 'ativo': True},
            )

    def setUp(self):
        sala = Sala.objects.create(nome='Sala Formas')
        dentista = Dentista.objects.create(nome_completo='Dentista Formas', sala=sala)
        self.admin = User.objects.create_superuser('admin_formas', 'admin@example.com', 'x')
        self.dentista = User.objects.create_user('dentista_formas', password='x')
        PerfilUsuario.objects.create(usuario=self.dentista, dentista=dentista, papel=PerfilUsuario.Papel.DENTISTA)
        self.secretaria = User.objects.create_user('secretaria_formas', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.auxiliar = User.objects.create_user('auxiliar_formas', password='x')
        PerfilUsuario.objects.create(usuario=self.auxiliar, dentista=dentista, papel=PerfilUsuario.Papel.AUXILIAR)
        self.staff = User.objects.create_user('staff_formas', password='x', is_staff=True)
        paciente = Paciente.objects.create(
            nome_completo='Paciente Formas', cpf='951.000.000-01',
            data_nascimento=date(1980, 1, 1), telefone='11900000001',
        )
        conta = ContaReceber.objects.create(
            paciente=paciente, descricao='Tratamento', valor_original=Decimal('100.00'), criado_por=self.admin,
        )
        self.parcela = ParcelaContaReceber.objects.create(
            conta=conta, numero=1, vencimento=timezone.localdate(), valor_original=Decimal('100.00'),
        )

    def test_formas_iniciais_e_cadastro_auditado(self):
        self.assertEqual(
            set(FormaPagamentoConfiguravel.objects.values_list('codigo', flat=True)),
            {'pix', 'dinheiro', 'cartao_debito', 'cartao_credito', 'transferencia'},
        )
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('core:cadastrar_forma_pagamento_configuravel'), {
            'nome': 'Boleto', 'codigo': 'boleto', 'ativo': 'on',
            'tipo_taxa': 'valor_fixo', 'valor_taxa': '3.50',
            'prazo_recebimento_dias': '2', 'conta_destino': 'Conta operacional',
        })
        self.assertEqual(resposta.status_code, 302)
        boleto = FormaPagamentoConfiguravel.objects.get(codigo='boleto')
        self.assertEqual(boleto.valor_taxa, Decimal('3.50'))
        self.assertTrue(AuditoriaFormaPagamento.objects.filter(forma_pagamento=boleto, acao='criada').exists())

    def test_novo_recebimento_vincula_configuracao_sem_reinterpretar_legado(self):
        forma = FormaPagamentoConfiguravel.objects.get(codigo='cartao_debito')
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('core:registrar_recebimento', args=[self.parcela.pk]), {
            'valor': '100.00', 'desconto': '0.00',
            'forma_pagamento': '', 'forma_pagamento_configurada': forma.pk,
            'observacoes': 'Pagamento com débito',
        })
        self.assertEqual(resposta.status_code, 302)
        recebimento = RecebimentoPaciente.objects.get()
        self.assertEqual(recebimento.forma_pagamento_configurada, forma)
        self.assertEqual(recebimento.forma_pagamento, 'outros')
        self.assertEqual(MovimentoCaixa.objects.count(), 0)

    def test_forma_inativa_preserva_historico_e_nao_aceita_novo_recebimento(self):
        forma = FormaPagamentoConfiguravel.objects.get(codigo='pix')
        forma.ativo = False
        forma.save()
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('core:registrar_recebimento', args=[self.parcela.pk]), {
            'valor': '100.00', 'desconto': '0.00',
            'forma_pagamento': '', 'forma_pagamento_configurada': forma.pk,
            'observacoes': '',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(RecebimentoPaciente.objects.count(), 0)

    def test_administracao_e_exclusiva_do_administrador(self):
        urls = [
            reverse('core:listar_formas_pagamento_configuraveis'),
            reverse('core:cadastrar_forma_pagamento_configuravel'),
        ]
        for usuario in (self.dentista, self.secretaria, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
