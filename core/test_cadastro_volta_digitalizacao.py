"""Retorno do cadastro de paciente para a digitalização."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, Paciente
from .test_busca_paciente import _dados


class CadastroVoltaDigitalizacaoTests(TestCase):
    def setUp(self):
        self.secretaria = User.objects.create_user('secretaria_volta', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.sala_a = Sala.objects.create(nome='Sala volta A')
        self.sala_b = Sala.objects.create(nome='Sala volta B')
        self.dentista_a = Dentista.objects.create(nome_completo='Dra. Volta A', sala=self.sala_a)
        self.dentista_b = Dentista.objects.create(nome_completo='Dra. Volta B', sala=self.sala_b)
        self.usuario_a = User.objects.create_user('dentista_volta_a', password='x')
        PerfilUsuario.objects.create(
            usuario=self.usuario_a,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=self.dentista_a,
        )
        self.usuario_b = User.objects.create_user('dentista_volta_b', password='x')
        PerfilUsuario.objects.create(
            usuario=self.usuario_b,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=self.dentista_b,
        )
        self.ruth = Paciente.objects.create(
            nome_completo='Ruth Gonçalves Souza',
            data_nascimento=date(1980, 2, 2),
            telefone='11977776655',
        )
        self.alheio = Paciente.objects.create(
            nome_completo='Carlos Alheio',
            data_nascimento=date(1970, 1, 1),
            telefone='11888880000',
        )
        self.inativo = Paciente.objects.create(
            nome_completo='Inativo da Dra',
            data_nascimento=date(1975, 3, 3),
            telefone='11777770000',
            ativo=False,
        )
        Consulta.objects.create(
            paciente=self.ruth, dentista=self.dentista_a,
            data=date(2026, 10, 6), hora_inicio=time(9), hora_fim=time(10),
        )
        Consulta.objects.create(
            paciente=self.alheio, dentista=self.dentista_b,
            data=date(2026, 10, 6), hora_inicio=time(11), hora_fim=time(12),
        )
        Consulta.objects.create(
            paciente=self.inativo, dentista=self.dentista_a,
            data=date(2026, 10, 6), hora_inicio=time(14), hora_fim=time(15),
        )
        self.client.force_login(self.secretaria)

    def test_so_a_digitalizacao_abre_cadastro_com_voltar(self):
        cadastro = reverse('core:cadastrar_paciente')
        pagina = self.client.get(reverse('core:digitalizacao_upload'))
        self.assertContains(pagina, f'href="{cadastro}?voltar=digitalizacao"')
        self.assertContains(pagina, 'Cadastrar novo paciente')

        agenda = self.client.get(reverse('core:agendar_consulta'))
        self.assertEqual(agenda.status_code, 200)
        self.assertContains(agenda, f'href="{cadastro}"')
        self.assertNotContains(agenda, 'voltar=digitalizacao')

        lista = self.client.get(reverse('core:listar_pacientes'))
        self.assertContains(lista, f'href="{cadastro}"')
        self.assertNotContains(lista, 'voltar=digitalizacao')

    def test_salvar_com_voltar_digitalizacao_abre_o_envio(self):
        resposta = self.client.post(
            reverse('core:cadastrar_paciente'),
            {**_dados(), 'voltar': 'digitalizacao'},
            follow=True,
        )
        novo = Paciente.objects.get(telefone_busca='11900001111')
        destino = f"{reverse('core:digitalizacao_upload')}?paciente={novo.pk}"
        self.assertRedirects(resposta, destino)
        self.assertContains(resposta, 'Paciente cadastrado. Agora tire as fotos das folhas.')
        self.assertContains(resposta, '✓ Paciente:')
        self.assertContains(resposta, 'paciente-escolhido-faixa')
        self.assertEqual(resposta.context['form'].initial.get('paciente'), novo.pk)
        self.assertRegex(
            resposta.content.decode(),
            rf'<option value="{novo.pk}"[^>]*\bselected\b',
        )
        self.assertContains(resposta, novo.nome_completo)

    def test_sem_voltar_continua_na_lista(self):
        resposta = self.client.post(reverse('core:cadastrar_paciente'), _dados(
            nome_completo='Sem Retorno Silva',
            telefone='11900004444',
        ))
        self.assertRedirects(resposta, reverse('core:listar_pacientes'))
        self.assertNotIn('paciente=', resposta.url)

    def test_voltar_diferente_e_ignorado(self):
        valores = (
            'lista',
            'https://evil.example/phish',
            '/digitalizacao/nova/',
            'Digitalizacao',
            'digitalizacao/',
            'digitalizacao?paciente=1',
        )
        nomes = (
            'Ana Lista',
            'Bruno Phish',
            'Carla Caminho',
            'Diana Caixa',
            'Elena Barra',
            'Fabio Query',
        )
        for indice, valor in enumerate(valores):
            resposta = self.client.post(reverse('core:cadastrar_paciente'), {
                **_dados(
                    nome_completo=nomes[indice],
                    data_nascimento=f'{indice + 2:02d}/05/1991',
                    telefone=f'1192000{indice:04d}',
                ),
                'voltar': valor,
            })
            self.assertRedirects(resposta, reverse('core:listar_pacientes'))
            self.assertNotIn('digitalizacao', resposta.url)
            self.assertNotIn('evil.example', resposta.url)

        pagina = self.client.get(reverse('core:cadastrar_paciente'), {
            'voltar': 'https://evil.example/phish',
        })
        self.assertNotContains(pagina, 'evil.example')
        self.assertNotContains(pagina, 'name="voltar"')

        outro = self.client.get(
            f"{reverse('core:cadastrar_paciente')}?voltar=digitalizacao&voltar=lista",
        )
        self.assertNotContains(outro, 'name="voltar"')

    def test_aviso_de_duplicado_mantem_voltar(self):
        dados = _dados(
            nome_completo='Souza Ruth de Oliveira',
            data_nascimento='02/02/1980',
            telefone='11922223333',
        )
        url = reverse('core:cadastrar_paciente')
        aviso = self.client.post(f'{url}?voltar=digitalizacao', dados)
        self.assertEqual(aviso.status_code, 200)
        self.assertContains(aviso, 'Já existe paciente parecido')
        self.assertContains(aviso, 'name="voltar" value="digitalizacao"')
        self.assertEqual(Paciente.objects.filter(telefone_busca='11922223333').count(), 0)

        aviso_post = self.client.post(url, {**dados, 'voltar': 'digitalizacao'})
        self.assertContains(aviso_post, 'name="voltar" value="digitalizacao"')
        self.assertContains(aviso_post, 'Já existe paciente parecido')

        confirmado = self.client.post(url, {
            **dados,
            'voltar': 'digitalizacao',
            'cadastrar_mesmo_assim': '1',
            'confirmar_duplicado': 'on',
        }, follow=True)
        novo = Paciente.objects.get(telefone_busca='11922223333')
        self.assertRedirects(
            confirmado,
            f"{reverse('core:digitalizacao_upload')}?paciente={novo.pk}",
        )
        self.assertContains(
            confirmado, 'Paciente cadastrado. Agora tire as fotos das folhas.',
        )
        self.assertEqual(confirmado.context['form'].initial.get('paciente'), novo.pk)

    def test_get_paciente_deixa_escolhido_se_visivel(self):
        self.client.force_login(self.usuario_a)
        resposta = self.client.get(reverse('core:digitalizacao_upload'), {
            'paciente': self.ruth.pk,
        })
        self.assertEqual(resposta.context['form'].initial.get('paciente'), self.ruth.pk)
        html = resposta.content.decode()
        self.assertRegex(html, rf'<option value="{self.ruth.pk}"[^>]*\bselected\b')
        self.assertIn('✓ Paciente:', html)
        self.assertIn('paciente-escolhido-faixa', html)
        self.assertIn(self.ruth.nome_completo, html)
        self.assertNotIn('Paciente cadastrado. Agora tire as fotos das folhas.', html)

    def test_paciente_de_outro_usuario_ou_inativo_e_ignorado(self):
        self.client.force_login(self.usuario_a)
        for paciente in (self.alheio, self.inativo):
            resposta = self.client.get(reverse('core:digitalizacao_upload'), {
                'paciente': paciente.pk,
            })
            self.assertEqual(resposta.status_code, 200)
            self.assertNotIn('paciente', resposta.context['form'].initial)
            html = resposta.content.decode()
            self.assertNotRegex(
                html, rf'<option value="{paciente.pk}"[^>]*\bselected\b',
            )
            self.assertNotIn(paciente.nome_completo, html)

        inexistente = self.client.get(reverse('core:digitalizacao_upload'), {
            'paciente': '999999',
        })
        self.assertNotIn('paciente', inexistente.context['form'].initial)
        texto = self.client.get(reverse('core:digitalizacao_upload'), {
            'paciente': 'abc',
        })
        self.assertNotIn('paciente', texto.context['form'].initial)
