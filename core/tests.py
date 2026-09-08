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
    RepasseUniodonto,
    soma_producao_uniodonto,
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
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/repasses/', HTTP_HOST='localhost'
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
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/repasses/', HTTP_HOST='localhost'
            ).status_code,
            403,
        )
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertNotIn('Acerto mensal', home)
        self.assertNotIn('Procedimentos', home)
        self.assertNotIn('Tabela Uniodonto', home)
        self.assertNotIn('Repasse Uniodonto', home)

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
        self.assertEqual(
            self.client.get(
                '/convenios/uniodonto/repasses/', HTTP_HOST='localhost'
            ).status_code,
            403,
        )
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertNotIn('Tabela Uniodonto', home)
        self.assertNotIn('Repasse Uniodonto', home)

    def test_home_admin_tem_card_tabela(self):
        self.client.force_login(self.admin)
        home = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertIn('Tabela Uniodonto', home)
        self.assertIn('Repasse Uniodonto', home)

    def _consulta_uniodonto(self):
        uniodonto = Convenio.objects.get(nome=NOME_CONVENIO_UNIODONTO)
        paciente = Paciente.objects.create(
            nome_completo='Paciente Uniodonto Teste',
            cpf='222.222.222-22',
            data_nascimento=date(1990, 1, 1),
            telefone='11988887777',
            convenio=uniodonto,
        )
        return Consulta.objects.create(
            paciente=paciente,
            data=date(2026, 9, 7),
            hora_inicio=time(10, 0),
            hora_fim=time(11, 0),
            dentista=self.dentista,
        )

    def test_ficha_uniodonto_usa_tabela_oficial(self):
        consulta = self._consulta_uniodonto()
        Procedimento.objects.create(
            dentista=self.dentista,
            nome='Consulta particular',
        )
        self.client.force_login(self.admin)
        html = self.client.get(
            f'/consultas/{consulta.pk}/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertIn('Novo lançamento Uniodonto', html)
        self.assertIn('85100196', html)
        self.assertIn('código TUSS', html)
        self.assertIn('valor US', html)
        self.assertIn('Selecione o procedimento', html)
        self.assertNotIn('Consulta particular', html)
        self.assertNotIn('empty_label', html)
        self.assertNotIn('>Particular<', html)

    def test_lanca_procedimento_uniodonto_congela_snapshot(self):
        consulta = self._consulta_uniodonto()
        item = ProcedimentoUniodonto.objects.get(codigo='85100196')
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/consultas/{consulta.pk}/lancar/',
            {
                'procedimento_uniodonto': item.pk,
                'valor_tabela': '40.00',
                'percentual_desconto': '0',
                'valor_final': '40.00',
                'tipo': 'atendimento',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        lancamento = consulta.lancamentos.get()
        self.assertEqual(lancamento.codigo_tuss, '85100196')
        self.assertEqual(lancamento.nome_procedimento, item.nome)
        self.assertEqual(lancamento.valor_us, Decimal('233.64'))
        self.assertEqual(lancamento.fator_us, FATOR_US_UNIODONTO)
        self.assertEqual(lancamento.valor_tabela, Decimal('40.00'))
        self.assertEqual(lancamento.valor_final, Decimal('40.00'))
        self.assertFalse(lancamento.particular)
        self.assertIsNone(lancamento.procedimento_id)
        self.assertEqual(consulta.valor_a_cobrar, Decimal('40.00'))
        item.valor_reais = Decimal('99.00')
        item.nome = 'Nome alterado na tabela'
        item.save()
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.valor_tabela, Decimal('40.00'))
        self.assertEqual(lancamento.nome_procedimento, 'Restauração em resina fotopolimerizável 1 face')
        html = self.client.get(
            f'/consultas/{consulta.pk}/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertIn('85100196 — Restauração em resina fotopolimerizável 1 face', html)
        self.assertIn('Uniodonto', html)

    def test_ficha_ipasgo_nao_usa_tabela_uniodonto(self):
        ipasgo = Convenio.objects.get(nome='Ipasgo')
        paciente = Paciente.objects.create(
            nome_completo='Paciente Ipasgo Teste',
            cpf='333.333.333-33',
            data_nascimento=date(1990, 1, 1),
            telefone='11977776666',
            convenio=ipasgo,
        )
        consulta = Consulta.objects.create(
            paciente=paciente,
            data=date(2026, 9, 7),
            hora_inicio=time(14, 0),
            hora_fim=time(15, 0),
            dentista=self.dentista,
        )
        Procedimento.objects.create(
            dentista=self.dentista,
            nome='Consulta particular',
        )
        self.client.force_login(self.admin)
        html = self.client.get(
            f'/consultas/{consulta.pk}/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertNotIn('Novo lançamento Uniodonto', html)
        self.assertNotIn('código TUSS', html)
        self.assertNotIn('85100196', html)
        self.assertIn('Consulta particular', html)
        self.assertIn('Particular', html)

    def test_sugestao_producao_soma_valor_tabela_uniodonto(self):
        consulta = self._consulta_uniodonto()
        item = ProcedimentoUniodonto.objects.get(codigo='85200158')
        uniodonto = Convenio.objects.get(nome=NOME_CONVENIO_UNIODONTO)
        LancamentoAtendimento.objects.create(
            consulta=consulta,
            procedimento_uniodonto=item,
            nome_procedimento=item.nome,
            codigo_tuss=item.codigo,
            dentista=self.dentista,
            convenio=uniodonto,
            particular=False,
            valor_tabela=Decimal('352.00'),
            percentual_desconto=Decimal('0.00'),
            valor_final=Decimal('352.00'),
            cadastrado_por=self.admin,
        )
        ipasgo = Convenio.objects.get(nome='Ipasgo')
        paciente_ipasgo = Paciente.objects.create(
            nome_completo='Paciente Ipasgo Repasse',
            cpf='444.444.444-44',
            data_nascimento=date(1990, 1, 1),
            telefone='11966665555',
            convenio=ipasgo,
        )
        consulta_ipasgo = Consulta.objects.create(
            paciente=paciente_ipasgo,
            data=date(2026, 9, 8),
            hora_inicio=time(11, 0),
            hora_fim=time(12, 0),
            dentista=self.dentista,
        )
        procedimento = Procedimento.objects.create(
            dentista=self.dentista,
            nome='Consulta Ipasgo',
        )
        LancamentoAtendimento.objects.create(
            consulta=consulta_ipasgo,
            procedimento=procedimento,
            nome_procedimento=procedimento.nome,
            dentista=self.dentista,
            convenio=ipasgo,
            particular=False,
            valor_tabela=Decimal('120.00'),
            percentual_desconto=Decimal('0.00'),
            valor_final=Decimal('120.00'),
            cadastrado_por=self.admin,
        )
        self.assertEqual(
            soma_producao_uniodonto(self.dentista, date(2026, 9, 1)),
            Decimal('352.00'),
        )

    def test_cadastra_repasse_mesmo_com_diferenca(self):
        consulta = self._consulta_uniodonto()
        item = ProcedimentoUniodonto.objects.get(codigo='85200158')
        self.client.force_login(self.admin)
        self.client.post(
            f'/consultas/{consulta.pk}/lancar/',
            {
                'procedimento_uniodonto': item.pk,
                'valor_tabela': '352.00',
                'percentual_desconto': '0',
                'valor_final': '352.00',
                'tipo': 'atendimento',
            },
            HTTP_HOST='localhost',
        )
        html = self.client.get(
            f'/convenios/uniodonto/repasses/novo/?dentista={self.dentista.pk}&competencia=2026-09',
            HTTP_HOST='localhost',
        ).content.decode()
        self.assertIn('352,00', html)
        resposta = self.client.post(
            '/convenios/uniodonto/repasses/novo/',
            {
                'dentista': self.dentista.pk,
                'competencia': '2026-09',
                'producao_bruta': '352.00',
                'glosa': '20.00',
                'estorno': '0',
                'inss_retido': '30.00',
                'irrf_retido': '10.00',
                'liquido_recebido': '280.00',
                'observacoes': '',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        extrato = RepasseUniodonto.objects.get(
            dentista=self.dentista, competencia=date(2026, 9, 1)
        )
        self.assertEqual(extrato.liquido_calculado, Decimal('292.00'))
        self.assertEqual(extrato.liquido_recebido, Decimal('280.00'))
        self.assertEqual(extrato.diferenca(), Decimal('12.00'))
        lista = self.client.get(
            '/convenios/uniodonto/repasses/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertIn('R$ 280,00', lista)
        duplicado = self.client.post(
            '/convenios/uniodonto/repasses/novo/',
            {
                'dentista': self.dentista.pk,
                'competencia': '2026-09',
                'producao_bruta': '352.00',
                'glosa': '0',
                'estorno': '0',
                'inss_retido': '0',
                'irrf_retido': '0',
                'liquido_recebido': '352.00',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(duplicado.status_code, 200)
        self.assertEqual(RepasseUniodonto.objects.count(), 1)

    def test_sugestao_json_soma_lancamento_uniodonto(self):
        consulta = self._consulta_uniodonto()
        item = ProcedimentoUniodonto.objects.get(codigo='85200158')
        self.client.force_login(self.admin)
        self.client.post(
            f'/consultas/{consulta.pk}/lancar/',
            {
                'procedimento_uniodonto': item.pk,
                'valor_tabela': '352.00',
                'percentual_desconto': '0',
                'valor_final': '352.00',
                'tipo': 'atendimento',
            },
            HTTP_HOST='localhost',
        )
        resposta = self.client.get(
            '/convenios/uniodonto/repasses/sugestao/',
            {'dentista': self.dentista.pk, 'competencia': '2026-09'},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()['sugerido'], '352.00')


PNG_1PX = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII='
)


class AssinaturaEletronicaTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'admin_assinatura', password='x', is_staff=True, is_superuser=True
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Assinatura',
            cpf='555.555.555-55',
            data_nascimento=date(1990, 1, 1),
            telefone='11955554444',
        )

    def test_grava_png_hash_e_campos_icp_vazios(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            '/fichas/assinatura/',
            {
                'paciente': self.paciente.pk,
                'papel': 'paciente',
                'nome_assinante': 'Paciente Assinatura',
                'cpf_assinante': '555.555.555-55',
                'imagem_base64': PNG_1PX,
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        from .models import AssinaturaEletronica

        item = AssinaturaEletronica.objects.get()
        self.assertEqual(item.tipo_assinatura, 'manuscrita')
        self.assertEqual(item.papel, 'paciente')
        self.assertTrue(item.imagem)
        self.assertEqual(len(item.hash_conteudo), 64)
        self.assertEqual(len(item.hash_imagem), 64)
        self.assertEqual(item.certificado_id, '')
        self.assertEqual(item.status_verificacao, 'nao_aplicavel')
        self.assertIsNone(item.pacote_assinatura)
        html = self.client.get(
            '/fichas/assinatura/', HTTP_HOST='localhost'
        ).content.decode()
        self.assertIn('Paciente Assinatura', html)
        img = self.client.get(
            f'/fichas/assinatura/{item.pk}/imagem/', HTTP_HOST='localhost'
        )
        self.assertEqual(img.status_code, 200)

    def test_recusa_assinatura_vazia(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            '/fichas/assinatura/',
            {
                'papel': 'dentista',
                'nome_assinante': 'Dentista',
                'imagem_base64': '',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        from .models import AssinaturaEletronica

        self.assertEqual(AssinaturaEletronica.objects.count(), 0)


def _payload_anamnese(**extra):
    dados = {
        'nome_completo': 'Paciente Teste',
        'data_nascimento': '1990-01-01',
        'cpf': '111.111.111-11',
        'telefone': '11999999999',
        'whatsapp': '11988887777',
        'email': 'paciente@example.com',
        'endereco': 'Rua das Flores, 10',
        'cidade': 'Goiânia',
        'uf': 'GO',
        'profissao': 'Comerciante',
        'nome_responsavel': '',
        'saude_condicoes': ['nenhuma'],
        'saude_outra_texto': '',
        'alergia': 'nao',
        'alergia_qual': '',
        'usa_medicamento': 'nao',
        'medicamento_nome': '',
        'cirurgia_recente': 'nao',
        'cirurgia_qual': '',
        'saude_bucal': ['nenhuma'],
        'experiencia_anterior': 'nao',
        'experiencia_relato': '',
        'o_que_incomoda': 'sensibilidade',
        'o_que_espera': 'tratamento tranquilo',
        'fuma': 'nao',
        'bebida_alcoolica': 'nao',
        'range_dentes': 'nao',
        'gravidez': 'nao_se_aplica',
        'outra_info_saude': 'nao',
        'outra_info_relato': '',
        'aceitou_declaracao': 'on',
        'assinatura_paciente_base64': PNG_1PX,
        'acao': 'enviar',
    }
    dados.update(extra)
    return dados


class FichaCadastroAnamneseTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'admin_anamnese', password='x', is_staff=True, is_superuser=True
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Teste',
            cpf='111.111.111-11',
            data_nascimento=date(1990, 1, 1),
            telefone='11999999999',
        )
        self.menor = Paciente.objects.create(
            nome_completo='Paciente Menor',
            cpf='222.222.222-22',
            data_nascimento=date(2015, 5, 20),
            telefone='11911112222',
        )

    def _abrir_ficha(self, paciente):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/pacientes/{paciente.pk}/anamnese/nova/',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        from .models import FichaCadastroAnamnese

        return FichaCadastroAnamnese.objects.filter(paciente=paciente).latest('pk')

    def test_link_publico_sem_login_e_texto_da_declaracao(self):
        from .anamnese import TEXTO_DECLARACAO_ANAMNESE

        ficha = self._abrir_ficha(self.paciente)
        self.client.logout()
        resposta = self.client.get(
            f'/f/a/{ficha.token}/', HTTP_HOST='localhost'
        )
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn(TEXTO_DECLARACAO_ANAMNESE, html)
        self.assertNotIn('Sair', html)

    def test_lista_mostra_token_completo_no_link(self):
        ficha = self._abrir_ficha(self.paciente)
        token = str(ficha.token)
        self.assertEqual(len(token), 36)
        resposta = self.client.get(
            f'/pacientes/{self.paciente.pk}/anamnese/',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn(token, html)
        self.assertIn(f'/f/a/{token}/', html)

    def test_paciente_envia_pelo_link_e_equipe_conclui(self):
        from .models import AssinaturaEletronica, FichaCadastroAnamnese

        ficha = self._abrir_ficha(self.paciente)
        self.client.logout()
        resposta = self.client.post(
            f'/f/a/{ficha.token}/',
            _payload_anamnese(),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.paciente.refresh_from_db()
        self.assertEqual(
            ficha.status, FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
        )
        self.assertEqual(ficha.preenchida_por, 'paciente')
        self.assertEqual(self.paciente.endereco, 'Rua das Flores, 10')
        self.assertEqual(
            AssinaturaEletronica.objects.filter(
                tipo_documento='anamnese', papel='paciente'
            ).count(),
            1,
        )
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/',
            {'assinatura_dentista_base64': PNG_1PX},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.CONCLUIDA)
        self.assertEqual(
            AssinaturaEletronica.objects.filter(
                tipo_documento='anamnese'
            ).count(),
            2,
        )

    def test_menor_exige_responsavel_e_assinatura_do_responsavel(self):
        from .models import AssinaturaEletronica, FichaCadastroAnamnese

        ficha = self._abrir_ficha(self.menor)
        self.client.logout()
        recusa = self.client.post(
            f'/f/a/{ficha.token}/',
            _payload_anamnese(
                nome_completo='Paciente Menor',
                data_nascimento='2015-05-20',
                cpf='222.222.222-22',
                telefone='11911112222',
                nome_responsavel='',
            ),
            HTTP_HOST='localhost',
        )
        self.assertEqual(recusa.status_code, 200)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.RASCUNHO)
        ok = self.client.post(
            f'/f/a/{ficha.token}/',
            _payload_anamnese(
                nome_completo='Paciente Menor',
                data_nascimento='2015-05-20',
                cpf='222.222.222-22',
                telefone='11911112222',
                nome_responsavel='Maria Responsável',
                gravidez='nao_se_aplica',
            ),
            HTTP_HOST='localhost',
        )
        self.assertEqual(ok.status_code, 302)
        assinatura = AssinaturaEletronica.objects.get(
            tipo_documento='anamnese', documento_id=ficha.pk
        )
        self.assertEqual(assinatura.papel, 'responsavel')
        self.assertEqual(assinatura.nome_assinante, 'Maria Responsável')

    def test_uma_ficha_aberta_por_paciente(self):
        from django.db import IntegrityError
        from .models import FichaCadastroAnamnese

        primeira = self._abrir_ficha(self.paciente)
        segunda_url = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/nova/',
            HTTP_HOST='localhost',
        )
        self.assertEqual(segunda_url.status_code, 302)
        self.assertEqual(FichaCadastroAnamnese.objects.filter(
            paciente=self.paciente
        ).count(), 1)
        with self.assertRaises(IntegrityError):
            from django.db import transaction

            with transaction.atomic():
                FichaCadastroAnamnese.objects.create(
                    paciente=self.paciente,
                    nome_completo=self.paciente.nome_completo,
                    data_nascimento=self.paciente.data_nascimento,
                    cpf=self.paciente.cpf,
                    telefone=self.paciente.telefone,
                )
        primeira.status = FichaCadastroAnamnese.Status.CONCLUIDA
        primeira.save(update_fields=['status'])
        outra = self._abrir_ficha(self.paciente)
        self.assertNotEqual(outra.pk, primeira.pk)

    def test_link_expirado_nao_abre_a_ficha(self):
        from django.utils import timezone
        from datetime import timedelta

        ficha = self._abrir_ficha(self.paciente)
        ficha.token_expira_em = timezone.now() - timedelta(days=1)
        ficha.save(update_fields=['token_expira_em'])
        self.client.logout()
        resposta = self.client.get(
            f'/f/a/{ficha.token}/', HTTP_HOST='localhost'
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('não está mais disponível', resposta.content.decode())

    def test_renovar_link_depois_do_envio_nao_da_404(self):
        from .models import FichaCadastroAnamnese

        ficha = self._abrir_ficha(self.paciente)
        self.client.logout()
        self.client.post(
            f'/f/a/{ficha.token}/',
            _payload_anamnese(),
            HTTP_HOST='localhost',
        )
        ficha.refresh_from_db()
        self.assertEqual(
            ficha.status, FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA
        )
        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/link/',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            resposta.url,
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/',
        )

    def test_equipe_conclui_com_duas_assinaturas(self):
        from .models import AssinaturaEletronica, FichaCadastroAnamnese

        ficha = self._abrir_ficha(self.paciente)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/editar/',
            _payload_anamnese(
                acao='concluir',
                assinatura_dentista_base64=PNG_1PX,
            ),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.CONCLUIDA)
        self.assertEqual(ficha.preenchida_por, 'equipe')
        self.assertEqual(
            AssinaturaEletronica.objects.filter(documento_id=ficha.pk).count(),
            2,
        )

    def test_checklist_nenhuma_nao_mistura_com_outras(self):
        ficha = self._abrir_ficha(self.paciente)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/editar/',
            _payload_anamnese(saude_condicoes=['nenhuma', 'diabetes']),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'não marque as outras opções')


class RegistroEvolucaoClinicaTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Evolucao')
        self.dentista = Dentista.objects.create(
            nome_completo='Dentista Evolucao',
            sala=self.sala,
            valor_hora=Decimal('200.00'),
        )
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Evolucao',
            cpf='333.333.333-33',
            data_nascimento=date(1988, 3, 3),
            telefone='11933334444',
        )
        self.admin = User.objects.create_user(
            'admin_evolucao', password='x', is_staff=True, is_superuser=True
        )
        self.user_dentista = User.objects.create_user(
            'dentista_evolucao', password='x', first_name='Carla'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_dentista,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.user_secretaria = User.objects.create_user(
            'secretaria_evolucao', password='x', first_name='Amanda'
        )
        PerfilUsuario.objects.create(
            usuario=self.user_secretaria,
            dentista=None,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )

    def _payload(self, **extra):
        dados = {
            'data': '2026-09-01',
            'procedimento_etapa': 'Profilaxia',
            'descricao_clinica': 'Remoção de cálculo e polimento.',
            'orientacoes': 'Higiene a cada 6 meses.',
            'nome_profissional': 'Dentista Evolucao',
            'cro': 'CRO-GO 12345',
            'assinatura_base64': PNG_1PX,
        }
        dados.update(extra)
        return dados

    def test_dentista_grava_linha_assinada(self):
        from .models import AssinaturaEletronica, RegistroEvolucaoClinica

        self.client.force_login(self.user_dentista)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 302)
        registro = RegistroEvolucaoClinica.objects.get()
        self.assertEqual(registro.procedimento_etapa, 'Profilaxia')
        self.assertEqual(registro.dentista_id, self.dentista.pk)
        assinatura = AssinaturaEletronica.objects.get(
            tipo_documento='evolucao', documento_id=registro.pk
        )
        self.assertEqual(assinatura.papel, 'dentista')
        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            HTTP_HOST='localhost',
        ).content.decode()
        self.assertIn('Profilaxia', html)
        self.assertIn('CRO-GO 12345', html)
        self.assertIn('Nova evolução', html)

    def test_secretaria_ve_e_nao_lanca(self):
        from .models import RegistroEvolucaoClinica

        self.client.force_login(self.user_dentista)
        self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(),
            HTTP_HOST='localhost',
        )
        self.client.force_login(self.user_secretaria)
        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            HTTP_HOST='localhost',
        ).content.decode()
        self.assertIn('Profilaxia', html)
        self.assertNotIn('Nova evolução', html)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(procedimento_etapa='Outro'),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(RegistroEvolucaoClinica.objects.count(), 1)

    def test_ordem_cronologica_e_legado_nao_aparece(self):
        from .models import Evolucao, RegistroEvolucaoClinica

        Evolucao.objects.create(
            paciente=self.paciente,
            data=date(2020, 1, 1),
            descricao='Importado da planilha',
        )
        self.client.force_login(self.admin)
        self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(data='2026-09-02', procedimento_etapa='Segunda'),
            HTTP_HOST='localhost',
        )
        self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(data='2026-09-01', procedimento_etapa='Primeira'),
            HTTP_HOST='localhost',
        )
        registros = list(
            RegistroEvolucaoClinica.objects.filter(paciente=self.paciente)
        )
        self.assertEqual(
            [item.procedimento_etapa for item in registros],
            ['Primeira', 'Segunda'],
        )
        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            HTTP_HOST='localhost',
        ).content.decode()
        self.assertIn('Primeira', html)
        self.assertIn('Segunda', html)
        self.assertNotIn('Importado da planilha', html)
        self.assertLess(html.find('Primeira'), html.find('Segunda'))

    def test_recusa_sem_assinatura(self):
        from .models import RegistroEvolucaoClinica

        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/evolucao/',
            self._payload(assinatura_base64=''),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(RegistroEvolucaoClinica.objects.count(), 0)
