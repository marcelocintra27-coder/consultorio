from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from locacao.models import Dentista, Sala

from .models import Convenio, PrecoProcedimento, Procedimento
from .views import _salvar_precos


class PrecoProcedimentoUnicidadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sala = Sala.objects.create(nome='R001')
        cls.dentista = Dentista.objects.create(nome_completo='Dentista R001', sala=sala)
        cls.proc_a = Procedimento.objects.create(dentista=cls.dentista, nome='Canal')
        cls.proc_b = Procedimento.objects.create(dentista=cls.dentista, nome='Limpeza')
        cls.convenio_x = Convenio.objects.create(nome='Convênio X R001')
        cls.convenio_y = Convenio.objects.create(nome='Convênio Y R001')

    def test_permite_um_particular_e_bloqueia_o_segundo(self):
        PrecoProcedimento.objects.create(
            procedimento=self.proc_a, convenio=None, valor=Decimal('1200.00'),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PrecoProcedimento.objects.create(
                procedimento=self.proc_a, convenio=None, valor=Decimal('1300.00'),
            )
        self.assertEqual(
            PrecoProcedimento.objects.filter(
                procedimento=self.proc_a, convenio__isnull=True,
            ).count(),
            1,
        )

    def test_permite_um_preco_por_convenio_e_bloqueia_duplicata(self):
        PrecoProcedimento.objects.create(
            procedimento=self.proc_a, convenio=self.convenio_x, valor=Decimal('650.00'),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PrecoProcedimento.objects.create(
                procedimento=self.proc_a, convenio=self.convenio_x, valor=Decimal('700.00'),
            )
        self.assertEqual(
            PrecoProcedimento.objects.filter(
                procedimento=self.proc_a, convenio=self.convenio_x,
            ).count(),
            1,
        )

    def test_permite_outro_convenio_e_outro_procedimento(self):
        PrecoProcedimento.objects.create(
            procedimento=self.proc_a, convenio=None, valor=Decimal('1200.00'),
        )
        PrecoProcedimento.objects.create(
            procedimento=self.proc_a, convenio=self.convenio_x, valor=Decimal('650.00'),
        )
        PrecoProcedimento.objects.create(
            procedimento=self.proc_a, convenio=self.convenio_y, valor=Decimal('700.00'),
        )
        PrecoProcedimento.objects.create(
            procedimento=self.proc_b, convenio=None, valor=Decimal('200.00'),
        )
        PrecoProcedimento.objects.create(
            procedimento=self.proc_b, convenio=self.convenio_x, valor=Decimal('180.00'),
        )
        self.assertEqual(PrecoProcedimento.objects.count(), 5)

    def test_atualizar_valor_nao_cria_duplicata(self):
        particular, criado = PrecoProcedimento.objects.update_or_create(
            procedimento=self.proc_a,
            convenio=None,
            defaults={'valor': Decimal('1200.00')},
        )
        self.assertTrue(criado)
        mesmo, criado = PrecoProcedimento.objects.update_or_create(
            procedimento=self.proc_a,
            convenio=None,
            defaults={'valor': Decimal('1250.00')},
        )
        self.assertFalse(criado)
        self.assertEqual(particular.pk, mesmo.pk)
        mesmo.refresh_from_db()
        self.assertEqual(mesmo.valor, Decimal('1250.00'))
        self.assertEqual(
            PrecoProcedimento.objects.filter(
                procedimento=self.proc_a, convenio__isnull=True,
            ).count(),
            1,
        )

        convenio, criado = PrecoProcedimento.objects.update_or_create(
            procedimento=self.proc_a,
            convenio=self.convenio_x,
            defaults={'valor': Decimal('650.00')},
        )
        self.assertTrue(criado)
        mesmo_conv, criado = PrecoProcedimento.objects.update_or_create(
            procedimento=self.proc_a,
            convenio=self.convenio_x,
            defaults={'valor': Decimal('680.00')},
        )
        self.assertFalse(criado)
        self.assertEqual(convenio.pk, mesmo_conv.pk)
        mesmo_conv.refresh_from_db()
        self.assertEqual(mesmo_conv.valor, Decimal('680.00'))
        self.assertEqual(PrecoProcedimento.objects.count(), 2)


class SalvarPrecosRequest:
    def __init__(self, post):
        self.POST = post


class SalvarPrecosAtualizaExistenteTests(TestCase):
    def test_salvar_precos_atualiza_sem_duplicar(self):
        sala = Sala.objects.create(nome='R001b')
        dentista = Dentista.objects.create(nome_completo='Dentista R001b', sala=sala)
        procedimento = Procedimento.objects.create(dentista=dentista, nome='Canal')
        convenio = Convenio.objects.create(
            nome='Convênio catálogo R001', ativo=True, usa_tabela_oficial=False,
        )
        _salvar_precos(
            SalvarPrecosRequest({
                'preco_particular': '1200.00',
                f'preco_convenio_{convenio.pk}': '650.00',
            }),
            procedimento,
        )
        _salvar_precos(
            SalvarPrecosRequest({
                'preco_particular': '1250.00',
                f'preco_convenio_{convenio.pk}': '680.00',
            }),
            procedimento,
        )
        self.assertEqual(PrecoProcedimento.objects.filter(procedimento=procedimento).count(), 2)
        self.assertEqual(
            PrecoProcedimento.objects.get(procedimento=procedimento, convenio=None).valor,
            Decimal('1250.00'),
        )
        self.assertEqual(
            PrecoProcedimento.objects.get(procedimento=procedimento, convenio=convenio).valor,
            Decimal('680.00'),
        )
