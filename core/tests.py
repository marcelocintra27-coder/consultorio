from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import (
    Convenio,
    Paciente,
    Consulta,
    Procedimento,
    PrecoProcedimento,
    LancamentoAtendimento,
    AuditoriaConsulta,
    ProcedimentoUniodonto,
)
from .tabela_uniodonto import (
    FATOR_US_UNIODONTO,
    LOTE_PROCEDIMENTOS_UNIODONTO,
    NOME_CONVENIO_UNIODONTO,
)


class AtendimentoProcedimentoTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Teste Atendimento')
        self.dentista = Dentista.objects.create(
            nome_completo='Dentista Teste Atendimento',
            sala=self.sala,
            valor_hora=Decimal('200.00'),
        )
        self.convenio = Convenio.objects.create(
            nome='Convenio Teste Atendimento',
            valor_hora=Decimal('150.00'),
            percentual_desconto=Decimal('10.00'),
            percentual_imposto=Decimal('0.00'),
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Teste',
            cpf='111.111.111-11',
            data_nascimento=date(1990, 1, 1),
            telefone='11999999999',
            convenio=self.convenio,
        )
        self.admin = User.objects.create_user(
            'admin_teste_atend', password='x', is_staff=True, is_superuser=True
        )
        self.user_dentista = User.objects.create_user(
            'dentista_teste_atend', password='x', first_name='Adriana'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_dentista,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.user_secretaria = User.objects.create_user(
            'secretaria_teste_atend', password='x', first_name='Amanda'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_secretaria,
            dentista=None,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.user_auxiliar = User.objects.create_user(
            'auxiliar_teste_atend', password='x', first_name='Emilly'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_auxiliar,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.procedimento = Procedimento.objects.create(
            dentista=self.dentista,
            nome='Consulta',
            duracao_estimada_minutos=60,
        )
        PrecoProcedimento.objects.create(
            procedimento=self.procedimento,
            convenio=None,
            valor=Decimal('180.00'),
        )
        PrecoProcedimento.objects.create(
            procedimento=self.procedimento,
            convenio=self.convenio,
            valor=Decimal('160.00'),
        )

    def _consulta(self, legado=False, dentista=None):
        return Consulta.objects.create(
            paciente=self.paciente,
            data=date(2026, 9, 7),
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
            dentista=dentista,
            eh_legado=legado,
            valor_historico=Decimal('135.00') if legado else None,
        )

    def test_secretaria_nao_ve_valores_na_agenda(self):
        consulta = self._consulta(dentista=self.dentista)
        self.client.force_login(self.user_secretaria)
        resposta = self.client.get(
            '/consultas/', {'data': '2026-09-07'}, HTTP_HOST='localhost'
        )
        html = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn('Valor a cobrar', html)
        self.assertNotIn(f'R$ {consulta.valor_a_cobrar}', html)
        self.assertNotIn('Procedimentos', html)

    def test_auxiliar_nao_acessa_financeiro(self):
        self.client.force_login(self.user_auxiliar)
        self.assertEqual(
            self.client.get('/procedimentos/', HTTP_HOST='localhost').status_code,
            403,
        )
        self.assertEqual(
            self.client.get('/locacao/acerto/', HTTP_HOST='localhost').status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/tabela/', HTTP_HOST='localhost'
            ).status_code,
            403,
        )

    def test_secretaria_nao_acessa_catalogo_nem_clinica(self):
        self.client.force_login(self.user_secretaria)
        self.assertEqual(
            self.client.get('/procedimentos/', HTTP_HOST='localhost').status_code,
            403,
        )
        self.assertEqual(
            self.client.get('/convenios/', HTTP_HOST='localhost').status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/tabela/', HTTP_HOST='localhost'
            ).status_code,
            403,
        )
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertNotIn('Acerto mensal', home)
        self.assertNotIn('Procedimentos', home)
        self.assertNotIn('Tabela Uniodonto', home)

    def test_secretaria_nao_ve_valores_na_ficha(self):
        consulta = self._consulta(dentista=self.dentista)
        self.client.force_login(self.user_secretaria)
        html = self.client.get(
            f'/consultas/{consulta.pk}/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertNotIn('Valor histórico', html)
        self.assertNotIn('valor de tabela', html)
        self.assertNotIn('Total a cobrar', html)

    def test_catalogo_nao_altera_lancamento(self):
        consulta = self._consulta(dentista=self.dentista)
        lancamento = LancamentoAtendimento.objects.create(
            consulta=consulta,
            procedimento=self.procedimento,
            nome_procedimento='Consulta',
            dentista=self.dentista,
            particular=True,
            valor_tabela=Decimal('180.00'),
            percentual_desconto=Decimal('0.00'),
            valor_final=Decimal('180.00'),
            cadastrado_por=self.user_dentista,
        )
        preco = PrecoProcedimento.objects.get(
            procedimento=self.procedimento, convenio__isnull=True
        )
        preco.valor = Decimal('999.00')
        preco.save()
        self.procedimento.nome = 'Consulta alterada'
        self.procedimento.save()
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.valor_final, Decimal('180.00'))
        self.assertEqual(lancamento.valor_tabela, Decimal('180.00'))
        self.assertEqual(lancamento.nome_procedimento, 'Consulta')

    def test_legado_completar_dentista_nao_muda_valor(self):
        consulta = self._consulta(legado=True, dentista=None)
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/consultas/{consulta.pk}/dentista/',
            {'dentista': self.dentista.pk},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        consulta.refresh_from_db()
        self.assertEqual(consulta.dentista_id, self.dentista.pk)
        self.assertEqual(consulta.valor_historico, Decimal('135.00'))
        self.assertTrue(
            AuditoriaConsulta.objects.filter(consulta=consulta).exists()
        )

    def test_secretaria_nao_complementa_dentista(self):
        consulta = self._consulta(legado=True, dentista=None)
        self.client.force_login(self.user_secretaria)
        resposta = self.client.post(
            f'/consultas/{consulta.pk}/dentista/',
            {'dentista': self.dentista.pk},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 403)

    def test_agendar_exige_dentista(self):
        self.client.force_login(self.user_secretaria)
        resposta = self.client.post(
            '/consultas/agendar/',
            {
                'paciente': self.paciente.pk,
                'data': '2026-09-08',
                'hora_inicio': '09:00',
                'hora_fim': '10:00',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(data=date(2026, 9, 8)).exists())

    def test_dentista_lanca_procedimento(self):
        consulta = self._consulta(dentista=self.dentista)
        self.client.force_login(self.user_dentista)
        resposta = self.client.post(
            f'/consultas/{consulta.pk}/lancar/',
            {
                'procedimento': self.procedimento.pk,
                'convenio': '',
                'valor_tabela': '180.00',
                'percentual_desconto': '0',
                'valor_final': '180.00',
                'tipo': 'atendimento',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(consulta.lancamentos.count(), 1)
        self.assertEqual(consulta.valor_a_cobrar, Decimal('180.00'))

    def test_secretaria_nao_lanca(self):
        consulta = self._consulta(dentista=self.dentista)
        self.client.force_login(self.user_secretaria)
        resposta = self.client.post(
            f'/consultas/{consulta.pk}/lancar/',
            {
                'procedimento': self.procedimento.pk,
                'valor_tabela': '180.00',
                'percentual_desconto': '0',
                'valor_final': '180.00',
                'tipo': 'atendimento',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 403)


class TabelaUniodontoTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Teste Uniodonto')
        self.dentista = Dentista.objects.create(
            nome_completo='Dentista Teste Cooperada',
            sala=self.sala,
            valor_hora=Decimal('200.00'),
        )
        self.admin = User.objects.create_user(
            'admin_teste_uniodonto', password='x', is_staff=True, is_superuser=True
        )
        self.user_secretaria = User.objects.create_user(
            'secretaria_teste_uniodonto', password='x', first_name='Amanda'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_secretaria,
            dentista=None,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        Convenio.objects.get_or_create(
            nome='Ipasgo',
            defaults={'ativo': True, 'usa_tabela_oficial': False},
        )

    def test_lote_oficial_tem_57_itens(self):
        self.assertEqual(len(LOTE_PROCEDIMENTOS_UNIODONTO), 57)
        self.assertEqual(ProcedimentoUniodonto.objects.count(), 57)
        uniodonto = Convenio.objects.get(nome=NOME_CONVENIO_UNIODONTO)
        self.assertTrue(uniodonto.usa_tabela_oficial)
        resina = ProcedimentoUniodonto.objects.get(codigo='85100196')
        self.assertEqual(resina.valor_us, Decimal('233.64'))
        self.assertEqual(resina.valor_reais, Decimal('40.00'))
        self.assertEqual(resina.fator_us, FATOR_US_UNIODONTO)
        cariostatico = ProcedimentoUniodonto.objects.get(codigo='84000031')
        self.assertEqual(cariostatico.valor_reais, Decimal('28.00'))
        self.assertEqual(cariostatico.categoria, 'nao_classificada')
        endo = ProcedimentoUniodonto.objects.get(codigo='85200166')
        self.assertEqual(endo.valor_reais, Decimal('143.00'))
        self.assertEqual(endo.categoria, 'endodontia')

    def test_lista_mostra_tabela_oficial(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(
            '/convenios/uniodonto/tabela/', HTTP_HOST='localhost'
        )
        html = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('fator vigente US', html)
        self.assertIn('0,1712', html)
        self.assertIn('57 procedimentos', html)
        self.assertIn('85100196', html)
        self.assertIn('Restauração em resina fotopolimerizável 1 face', html)
        self.assertIn('R$ 40,00', html)
        self.assertIn('Aplicação de cariostático', html)
        self.assertIn('R$ 28,00', html)
        self.assertIn('Não classificada', html)
        self.assertIn('Dentística', html)

    def test_catalogo_dentista_nao_mistura_uniodonto(self):
        procedimento = Procedimento.objects.create(
            dentista=self.dentista,
            nome='Consulta particular',
        )
        PrecoProcedimento.objects.create(
            procedimento=procedimento,
            convenio=None,
            valor=Decimal('180.00'),
        )
        ipasgo = Convenio.objects.get(nome='Ipasgo')
        PrecoProcedimento.objects.create(
            procedimento=procedimento,
            convenio=ipasgo,
            valor=Decimal('120.00'),
        )
        self.client.force_login(self.admin)
        html = self.client.get(
            '/procedimentos/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertIn('Ipasgo', html)
        self.assertIn('Particular', html)
        self.assertNotIn('<th>Uniodonto</th>', html)
        self.assertNotIn('85100196', html)
        form = self.client.get(
            f'/procedimentos/cadastrar/?dentista={self.dentista.pk}',
            HTTP_HOST='localhost',
        ).content.decode()
        self.assertIn('preço Ipasgo', form)
        self.assertNotIn('preço Uniodonto', form)

    def test_secretaria_nao_acessa_tabela_uniodonto(self):
        self.client.force_login(self.user_secretaria)
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/tabela/', HTTP_HOST='localhost'
            ).status_code,
            403,
        )
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertNotIn('Tabela Uniodonto', home)

    def test_home_admin_tem_card_tabela(self):
        self.client.force_login(self.admin)
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertIn('Tabela Uniodonto', home)
