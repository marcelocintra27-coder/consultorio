"""Auxiliar digitaliza ficha antiga com as mesmas regras da secretária."""
import tempfile
from datetime import date, time
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from unittest.mock import patch

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, DigitalizacaoFicha, FichaCadastroAnamnese, Paciente
from .test_busca_paciente import _dados


def _png(nome='folha.png'):
    saida = BytesIO()
    Image.new('RGB', (20, 20), 'white').save(saida, format='PNG')
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AuxiliarDigitalizaTests(TestCase):
    def setUp(self):
        diretorio = tempfile.TemporaryDirectory()
        self.addCleanup(diretorio.cleanup)
        cfg = override_settings(MEDIA_ROOT=Path(diretorio.name))
        cfg.enable()
        self.addCleanup(cfg.disable)
        self.sala = Sala.objects.create(nome='Sala Emilly')
        self.outra_sala = Sala.objects.create(nome='Sala Simone')
        self.adriana = Dentista.objects.create(nome_completo='Dra. Adriana', sala=self.sala)
        self.simone = Dentista.objects.create(nome_completo='Dra. Simone', sala=self.outra_sala)
        self.emilly = User.objects.create_user('emilly', password='x', first_name='Emilly')
        PerfilUsuario.objects.create(
            usuario=self.emilly, papel=PerfilUsuario.Papel.AUXILIAR, dentista=self.adriana,
        )
        self.bruna = User.objects.create_user('bruna', password='x', first_name='Bruna')
        PerfilUsuario.objects.create(
            usuario=self.bruna, papel=PerfilUsuario.Papel.AUXILIAR, dentista=self.simone,
        )
        self.secretaria = User.objects.create_user('amanda', password='x', first_name='Amanda')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.vinculada = Paciente.objects.create(
            nome_completo='Paciente da Adriana',
            data_nascimento=date(1988, 4, 4),
            telefone='11911110000',
        )
        self.de_outra = Paciente.objects.create(
            nome_completo='Paciente da Simone',
            data_nascimento=date(1979, 5, 5),
            telefone='11922220000',
        )
        self.sem_consulta = Paciente.objects.create(
            nome_completo='Paciente sem consulta',
            data_nascimento=date(1995, 6, 6),
            telefone='11933330000',
        )
        self.inativa = Paciente.objects.create(
            nome_completo='Paciente inativa',
            data_nascimento=date(1960, 1, 1),
            telefone='11944440000',
            ativo=False,
        )
        Consulta.objects.create(
            paciente=self.vinculada, dentista=self.adriana,
            data=date(2026, 10, 8), hora_inicio=time(9), hora_fim=time(10),
        )
        Consulta.objects.create(
            paciente=self.de_outra, dentista=self.simone,
            data=date(2026, 10, 8), hora_inicio=time(11), hora_fim=time(12),
        )
        self.envio = reverse('core:digitalizacao_upload')
        self.lista = reverse('core:listar_digitalizacoes')
        self.client.force_login(self.emilly)

    def test_auxiliar_abre_a_tela_e_envia_para_qualquer_paciente_ativo(self):
        pagina = self.client.get(self.envio)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Digitalizar ficha antiga')
        self.assertContains(pagina, self.vinculada.nome_completo)
        self.assertContains(pagina, self.de_outra.nome_completo)
        self.assertContains(pagina, self.sem_consulta.nome_completo)
        self.assertNotContains(pagina, self.inativa.nome_completo)
        self.assertContains(pagina, 'Cadastrar novo paciente')

        recusa = self.client.post(self.envio, {
            'paciente': self.inativa.pk,
            'imagens': _png(),
            'tipo': 'cadastro',
        })
        self.assertEqual(recusa.status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())

        resposta = self.client.post(self.envio, {
            'paciente': self.de_outra.pk,
            'imagens': _png('folha-emilly.png'),
            'tipo': 'cadastro',
        })
        self.assertEqual(resposta.status_code, 302)
        ficha = DigitalizacaoFicha.objects.get()
        self.assertEqual(ficha.paciente, self.de_outra)
        self.assertEqual(ficha.digitalizado_por, self.emilly)
        with patch('core.views.processar_digitalizacao_com_ia') as processar:
            self.assertEqual(
                self.client.post(
                    reverse('core:digitalizacao_processar_ia', args=[ficha.pk]),
                ).status_code,
                403,
            )
            processar.assert_not_called()

    def test_auxiliar_ve_so_as_proprias_folhas_e_nao_revisa(self):
        minha = DigitalizacaoFicha.objects.create(
            paciente=self.vinculada,
            imagem=_png('minha.png'),
            digitalizado_por=self.emilly,
        )
        da_bruna = DigitalizacaoFicha.objects.create(
            paciente=self.de_outra,
            imagem=_png('bruna.png'),
            digitalizado_por=self.bruna,
        )
        lista = self.client.get(self.lista)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Fichas digitalizadas')
        self.assertContains(lista, self.vinculada.nome_completo)
        self.assertNotContains(lista, self.de_outra.nome_completo)
        self.assertNotContains(lista, 'Bruna')

        detalhe = self.client.get(reverse('core:detalhe_digitalizacao', args=[minha.pk]))
        self.assertEqual(detalhe.status_code, 200)
        self.assertNotContains(detalhe, 'name="acao" value="conferida"')
        self.assertEqual(
            self.client.get(reverse('core:detalhe_digitalizacao', args=[da_bruna.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('core:revisar_digitalizacao', args=[minha.pk]),
                {'acao': 'conferida'},
            ).status_code,
            403,
        )
        minha.refresh_from_db()
        self.assertEqual(minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

    def test_auxiliar_continua_sem_financeiro_prontuario_e_anamnese(self):
        self.assertEqual(self.client.get(reverse('core:listar_contas_receber')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('core:ficha_evolucao_clinica', args=[self.vinculada.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse('core:nova_ficha_anamnese', args=[self.vinculada.pk])).status_code,
            403,
        )
        self.assertFalse(FichaCadastroAnamnese.objects.filter(paciente=self.vinculada).exists())
        self.assertEqual(
            self.client.get(reverse('core:editar_paciente', args=[self.vinculada.pk])).status_code,
            403,
        )
        lista = self.client.get(reverse('core:listar_pacientes'))
        self.assertContains(lista, self.vinculada.nome_completo)
        self.assertNotContains(lista, self.de_outra.nome_completo)
        self.assertNotContains(lista, '>Cadastrar<')

    def test_menu_da_auxiliar_mostra_digitalizar_e_fichas(self):
        inicio = self.client.get(reverse('core:inicio'))
        self.assertContains(inicio, 'Auxiliar')
        self.assertContains(inicio, 'Digitalizar ficha antiga')
        self.assertContains(inicio, 'Fichas digitalizadas')
        self.assertContains(inicio, self.envio)
        self.assertContains(inicio, self.lista)
        self.assertNotContains(inicio, 'Financeiro atual')
        self.assertNotContains(inicio, reverse('core:agendar_consulta'))

    def test_cadastra_paciente_so_voltando_para_a_digitalizacao(self):
        cadastro = reverse('core:cadastrar_paciente')
        self.assertEqual(self.client.get(cadastro).status_code, 403)
        self.assertEqual(self.client.post(cadastro, _dados()).status_code, 403)
        self.assertFalse(Paciente.objects.filter(telefone_busca='11900001111').exists())

        pagina = self.client.get(self.envio)
        self.assertContains(pagina, f'href="{cadastro}?voltar=digitalizacao"')
        aberto = self.client.get(cadastro, {'voltar': 'digitalizacao'})
        self.assertEqual(aberto.status_code, 200)

        resposta = self.client.post(
            cadastro,
            {**_dados(nome_completo='Nova da Emilly'), 'voltar': 'digitalizacao'},
            follow=True,
        )
        nova = Paciente.objects.get(telefone_busca='11900001111')
        destino = f'{self.envio}?paciente={nova.pk}'
        self.assertRedirects(resposta, destino)
        self.assertContains(resposta, 'Paciente cadastrado. Agora tire as fotos das folhas.')
        self.assertEqual(resposta.context['form'].initial.get('paciente'), nova.pk)
        self.assertContains(resposta, 'Nova da Emilly')
