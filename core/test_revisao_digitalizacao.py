"""Lista, foto protegida e revisão das fichas digitalizadas."""
from datetime import date, datetime, time, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.models import (
    Consulta,
    DigitalizacaoFicha,
    Paciente,
    RegistroAcesso,
    TrocaPacienteDigitalizacao,
)
from core.relatorio_atividade import eventos_do_dia, linhas_do_relatorio
from locacao.models import Dentista, PerfilUsuario, Sala


def _png(nome='folha.png'):
    saida = BytesIO()
    Image.new('RGB', (20, 20), 'white').save(saida, format='PNG')
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


def _arquivo(nome, conteudo):
    return SimpleUploadedFile(nome, conteudo, 'application/octet-stream')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RevisaoDigitalizacaoTests(TestCase):
    def setUp(self):
        self.tmp = override_settings(MEDIA_ROOT=self._pasta())
        self.tmp.enable()
        self.addCleanup(self.tmp.disable)
        self.dentista_a = Dentista.objects.create(
            nome_completo='Dentista A', sala=Sala.objects.create(nome='Sala A'),
        )
        self.dentista_b = Dentista.objects.create(
            nome_completo='Dentista B', sala=Sala.objects.create(nome='Sala B'),
        )
        self.dentista_user = self._usuario('dentista_a', 'dentista', self.dentista_a, 'Dra. Ana')
        self.outro_dentista = self._usuario('dentista_b', 'dentista', self.dentista_b, 'Dra. Bia')
        self.admin = User.objects.create_superuser('admin_revisao', password='teste')
        self.admin.first_name = 'Admin'
        self.admin.save(update_fields=['first_name'])
        self.secretaria = self._usuario('secretaria_a', 'secretaria', None, 'Ana')
        self.outra_secretaria = self._usuario('secretaria_b', 'secretaria', None, 'Bia')
        self.auxiliar = self._usuario('auxiliar_revisao', 'auxiliar', self.dentista_a, 'Aux')
        self.staff = User.objects.create_user('staff_revisao', password='teste', is_staff=True)
        self.paciente_a = self._paciente('Paciente da Ana')
        self.paciente_b = self._paciente('Paciente isolado B')
        self.paciente_solto = self._paciente('Paciente sem consulta')
        self._consulta(self.paciente_a, self.dentista_a)
        self._consulta(self.paciente_b, self.dentista_b)
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)
        self.minha = self._ficha(self.paciente_a, self.secretaria)
        self.da_outra = self._ficha(self.paciente_a, self.outra_secretaria, nome='outra.png')
        self.para_refazer = self._ficha(
            self.paciente_b, self.secretaria, tipo='anamnese',
            status=DigitalizacaoFicha.Status.REFAZER, nome='escura.png',
            motivo='Foto escura demais',
        )
        self.conferida = self._ficha(
            self.paciente_solto, self.admin,
            status=DigitalizacaoFicha.Status.CONFIRMADA, nome='pronta.png',
        )
        self.antiga = self._ficha(self.paciente_a, self.secretaria, nome='antiga.png')
        self._em(self.antiga, self.ontem)

    def _pasta(self):
        import tempfile
        from pathlib import Path
        diretorio = tempfile.TemporaryDirectory()
        self.addCleanup(diretorio.cleanup)
        return Path(diretorio.name)

    def _usuario(self, nome, papel, dentista, primeiro):
        usuario = User.objects.create_user(nome, password='teste', first_name=primeiro)
        PerfilUsuario.objects.create(usuario=usuario, papel=papel, dentista=dentista)
        return usuario

    def _paciente(self, nome):
        return Paciente.objects.create(
            nome_completo=nome, cpf=None, data_nascimento=date(1990, 1, 1), telefone='123',
        )

    def _consulta(self, paciente, dentista):
        return Consulta.objects.create(
            paciente=paciente, dentista=dentista,
            data=date(2026, 9, 21), hora_inicio=time(10), hora_fim=time(11),
        )

    def _ficha(self, paciente, usuario, tipo='cadastro', status=None, nome='ficha.png',
               motivo='', conteudo=b'foto-de-teste'):
        return DigitalizacaoFicha.objects.create(
            paciente=paciente,
            imagem=_arquivo(nome, conteudo),
            tipo=tipo,
            status=status or DigitalizacaoFicha.Status.PENDENTE_REVISAO,
            digitalizado_por=usuario,
            motivo_refazer=motivo,
        )

    def _em(self, ficha, dia):
        ficha.criado_em = timezone.make_aware(datetime.combine(dia, time(15, 30)))
        ficha.save(update_fields=['criado_em'])

    def _entrar(self, usuario):
        self.client.force_login(usuario)

    def test_secretaria_ve_so_as_proprias_e_nao_revisa(self):
        self._entrar(self.secretaria)
        lista = self.client.get(reverse('core:listar_digitalizacoes'))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Minhas fichas enviadas')
        self.assertContains(lista, 'Pendentes: 2. Para refazer: 1.')
        self.assertContains(lista, self.paciente_a.nome_completo)
        self.assertContains(lista, self.paciente_b.nome_completo)
        self.assertNotContains(lista, 'Bia')
        self.assertNotContains(lista, self.paciente_solto.nome_completo)
        self.assertContains(lista, 'Foto escura demais')
        self.assertContains(lista, 'ficha-refazer')
        self.assertContains(lista, 'Enviar nova foto')
        self.assertContains(
            lista,
            f'?paciente={self.paciente_b.pk}&amp;tipo=anamnese',
        )
        self.assertNotContains(lista, '<img')
        self.assertNotContains(lista, self.minha.imagem.name)
        self.assertNotContains(lista, '/media/')
        self.assertFalse(RegistroAcesso.objects.filter(
            tipo=RegistroAcesso.Tipo.ABRIU_FOTO,
        ).exists())

        detalhe = self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, reverse('core:foto_digitalizacao', args=[self.minha.pk]))
        self.assertNotContains(detalhe, 'name="acao" value="conferida"')
        self.assertNotContains(detalhe, self.minha.imagem.name)
        self.assertEqual(
            self.client.get(reverse('core:detalhe_digitalizacao', args=[self.da_outra.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('core:foto_digitalizacao', args=[self.da_outra.pk])).status_code,
            404,
        )
        self.assertFalse(RegistroAcesso.objects.filter(
            tipo=RegistroAcesso.Tipo.ABRIU_FOTO,
        ).exists())
        resposta = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'conferida'},
        )
        self.assertEqual(resposta.status_code, 403)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

    def test_admin_ve_tudo_e_revisa_de_novo(self):
        self._entrar(self.admin)
        lista = self.client.get(reverse('core:inicio'))
        self.assertContains(lista, 'Fichas digitalizadas')
        self.assertContains(lista, reverse('core:listar_digitalizacoes'))
        self.assertNotContains(lista, 'Digitalizar ficha antiga')

        lista = self.client.get(reverse('core:listar_digitalizacoes'))
        self.assertContains(lista, 'Fichas digitalizadas')
        self.assertContains(lista, 'Pendentes: 3. Para refazer: 1.')
        self.assertContains(lista, 'Ana')
        self.assertContains(lista, 'Bia')
        self.assertContains(lista, self.paciente_solto.nome_completo)

        filtrada = self.client.get(reverse('core:listar_digitalizacoes'), {'situacao': 'confirmada'})
        self.assertContains(filtrada, 'Pendentes: 3. Para refazer: 1.')
        self.assertContains(filtrada, self.paciente_solto.nome_completo)
        self.assertNotContains(filtrada, 'Foto escura demais')

        detalhe = self.client.get(reverse('core:detalhe_digitalizacao', args=[self.para_refazer.pk]))
        self.assertContains(detalhe, 'name="acao" value="conferida"')
        self.assertContains(detalhe, 'Foto escura demais')
        self.assertContains(detalhe, 'csrfmiddlewaretoken')

        vazio = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'refazer', 'motivo_refazer': '   '},
        )
        self.assertRedirects(vazio, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)
        self.assertEqual(self.minha.revisado_por, None)

        longo = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'refazer', 'motivo_refazer': 'x' * 2001},
        )
        self.assertRedirects(longo, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

        invalida = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'apagar'},
        )
        self.assertEqual(invalida.status_code, 400)
        self.assertEqual(self.client.get(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
        ).status_code, 405)

        motivo = 'Folha cortada <script>'
        self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'refazer', 'motivo_refazer': motivo},
        )
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.REFAZER)
        self.assertEqual(self.minha.motivo_refazer, motivo)
        self.assertEqual(self.minha.revisado_por, self.admin)
        self.assertIsNotNone(self.minha.revisado_em)
        pagina_refazer = self.client.get(
            reverse('core:detalhe_digitalizacao', args=[self.minha.pk]),
        )
        self.assertContains(pagina_refazer, 'Folha cortada &lt;script&gt;')

        self._entrar(self.dentista_user)
        de_novo = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'conferida'},
        )
        self.assertRedirects(de_novo, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.CONFIRMADA)
        self.assertEqual(self.minha.motivo_refazer, '')
        self.assertEqual(self.minha.revisado_por, self.dentista_user)
        pagina = self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.assertContains(pagina, 'Dra. Ana')
        self.assertContains(pagina, 'Conferida')
        self.assertNotContains(pagina, 'Folha cortada')

    def test_csrf_impede_revisao(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        resposta = cliente.post(
            reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
            {'acao': 'conferida'},
        )
        self.assertEqual(resposta.status_code, 403)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

    def test_dentista_ve_e_revisa_somente_o_prontuario(self):
        self._entrar(self.dentista_user)
        lista = self.client.get(reverse('core:listar_digitalizacoes'))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Fichas digitalizadas')
        self.assertContains(lista, self.paciente_a.nome_completo)
        self.assertNotContains(lista, 'Foto escura demais')
        self.assertNotContains(lista, self.paciente_b.nome_completo)
        self.assertNotContains(lista, 'Enviar nova foto')
        self.assertEqual(
            self.client.get(reverse('core:detalhe_digitalizacao', args=[self.para_refazer.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('core:revisar_digitalizacao', args=[self.para_refazer.pk]),
                {'acao': 'conferida'},
            ).status_code,
            404,
        )
        self.para_refazer.refresh_from_db()
        self.assertEqual(self.para_refazer.status, DigitalizacaoFicha.Status.REFAZER)

        resposta = self.client.post(
            reverse('core:revisar_digitalizacao', args=[self.da_outra.pk]),
            {'acao': 'refazer', 'motivo_refazer': 'Tremida'},
        )
        self.assertEqual(resposta.status_code, 302)
        self.da_outra.refresh_from_db()
        self.assertEqual(self.da_outra.status, DigitalizacaoFicha.Status.REFAZER)
        self.assertEqual(self.da_outra.motivo_refazer, 'Tremida')
        self.assertEqual(self.da_outra.revisado_por, self.dentista_user)

        self._entrar(self.outro_dentista)
        self.assertEqual(
            self.client.get(reverse('core:foto_digitalizacao', args=[self.minha.pk])).status_code,
            404,
        )

    def test_perfis_sem_lista_recebem_403(self):
        for usuario in (self.auxiliar, self.staff):
            self._entrar(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.client.get(reverse('core:listar_digitalizacoes')).status_code, 403)
                self.assertEqual(
                    self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk])).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(reverse('core:foto_digitalizacao', args=[self.minha.pk])).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.post(
                        reverse('core:revisar_digitalizacao', args=[self.minha.pk]),
                        {'acao': 'conferida'},
                    ).status_code,
                    403,
                )
        self.assertFalse(RegistroAcesso.objects.filter(
            tipo=RegistroAcesso.Tipo.ABRIU_FOTO,
        ).exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse('core:listar_digitalizacoes')).status_code, 302)

    def test_foto_protegida_registra_abertura_e_cabecalhos(self):
        self._entrar(self.secretaria)
        casos = (
            ('folha.jpg', b'\xff\xd8\xff', 'image/jpeg'),
            ('folha.jpeg', b'\xff\xd8\xff', 'image/jpeg'),
            ('folha.JPG', b'\xff\xd8\xff', 'image/jpeg'),
            ('folha.png', b'\x89PNG', 'image/png'),
            ('folha.gif', b'GIF89a', 'image/gif'),
            ('folha.webp', b'RIFF', 'image/webp'),
        )
        for nome, conteudo, tipo in casos:
            registro = self._ficha(self.paciente_a, self.secretaria, nome=nome, conteudo=conteudo)
            antes = RegistroAcesso.objects.count()
            resposta = self.client.get(reverse('core:foto_digitalizacao', args=[registro.pk]))
            self.assertEqual(resposta.status_code, 200, nome)
            self.assertEqual(resposta['Content-Type'], tipo)
            self.assertEqual(
                resposta['Content-Disposition'],
                f'inline; filename="ficha-{registro.pk}{nome[nome.rfind("."):].lower()}"',
            )
            self.assertEqual(resposta['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(resposta['Cache-Control'], 'private, no-store')
            self.assertEqual(b''.join(resposta.streaming_content), conteudo)
            self.assertNotIn(registro.imagem.name, resposta['Content-Disposition'])
            self.assertEqual(RegistroAcesso.objects.count(), antes + 1)
            acesso = RegistroAcesso.objects.latest('pk')
            self.assertEqual(acesso.usuario, self.secretaria)
            self.assertEqual(acesso.tipo, RegistroAcesso.Tipo.ABRIU_FOTO)

        self.client.get(reverse('core:foto_digitalizacao', args=[self.minha.pk]))
        textos = [evento['texto'] for evento in eventos_do_dia(self.secretaria, self.hoje)]
        self.assertIn('Abriu foto de ficha digitalizada', textos)
        self.assertNotIn('Senha incorreta', textos)
        linhas = [
            linha for linha in linhas_do_relatorio(self.hoje, self.hoje, usuaria=self.secretaria)
            if linha['usuario'] == self.secretaria
        ]
        self.assertEqual(linhas[0]['entradas'], 1)

        sem_extensao = self._ficha(self.paciente_a, self.secretaria, nome='sem-extensao')
        antes = RegistroAcesso.objects.count()
        self.assertEqual(
            self.client.get(reverse('core:foto_digitalizacao', args=[sem_extensao.pk])).status_code,
            404,
        )
        sem_extensao.imagem.delete(save=False)
        self.minha.imagem.storage.delete(self.minha.imagem.name)
        self.assertEqual(
            self.client.get(reverse('core:foto_digitalizacao', args=[self.minha.pk])).status_code,
            404,
        )
        self.assertEqual(RegistroAcesso.objects.count(), antes)

    def test_filtros_periodo_e_paginacao(self):
        self._entrar(self.admin)
        por_nome = self.client.get(reverse('core:listar_digitalizacoes'), {'paciente': 'sem consulta'})
        self.assertContains(por_nome, self.paciente_solto.nome_completo)
        self.assertNotContains(por_nome, self.paciente_a.nome_completo)
        por_pessoa = self.client.get(
            reverse('core:listar_digitalizacoes'), {'enviado_por': self.outra_secretaria.pk},
        )
        self.assertContains(por_pessoa, 'Bia')
        self.assertNotContains(por_pessoa, 'Foto escura demais')
        de_hoje = self.client.get(
            reverse('core:listar_digitalizacoes'),
            {'de': self.hoje.isoformat(), 'ate': self.hoje.isoformat()},
        )
        self.assertNotIn(self.antiga.pk, {ficha.pk for ficha in de_hoje.context['pagina']})
        self.assertContains(de_hoje, self.paciente_b.nome_completo)
        so_ontem = self.client.get(
            reverse('core:listar_digitalizacoes'),
            {'de': self.ontem.isoformat(), 'ate': self.ontem.isoformat()},
        )
        self.assertContains(so_ontem, self.paciente_a.nome_completo)
        self.assertNotContains(so_ontem, self.paciente_b.nome_completo)
        invertido = self.client.get(
            reverse('core:listar_digitalizacoes'),
            {'de': self.hoje.isoformat(), 'ate': self.ontem.isoformat()},
        )
        self.assertContains(invertido, 'A data final não pode ser anterior à inicial.')
        self.assertContains(invertido, self.paciente_b.nome_completo)
        self.assertContains(invertido, self.paciente_solto.nome_completo)

        for indice in range(21):
            self._ficha(self.paciente_solto, self.admin, nome=f'lote-{indice}.png')
        pagina = self.client.get(reverse('core:listar_digitalizacoes'))
        self.assertContains(pagina, 'Página 1 de 2')
        self.assertContains(pagina, 'Próxima')
        seguinte = self.client.get(reverse('core:listar_digitalizacoes'), {'pagina': 2})
        self.assertContains(seguinte, 'Página 2 de 2')
        self.assertContains(seguinte, 'Anterior')
        primeira = [
            ficha.pk for ficha in pagina.context['pagina'].object_list
        ]
        self.assertEqual(primeira, sorted(primeira, reverse=True))

    def test_envio_mostra_as_de_hoje_e_preseleciona(self):
        self._entrar(self.secretaria)
        antes = self.client.get(reverse('core:digitalizacao_upload'))
        self.assertContains(antes, 'Enviadas hoje')
        self.assertEqual(
            {ficha.pk for ficha in antes.context['enviadas_hoje']},
            {self.minha.pk, self.para_refazer.pk},
        )
        self.assertNotIn(self.antiga.pk, {ficha.pk for ficha in antes.context['enviadas_hoje']})
        self.assertNotIn(self.da_outra.pk, {ficha.pk for ficha in antes.context['enviadas_hoje']})

        resposta = self.client.post(reverse('core:digitalizacao_upload'), {
            'paciente': self.paciente_a.pk,
            'imagem': _png(),
            'tipo': 'evolucao',
        })
        self.assertEqual(resposta.status_code, 302)
        pagina = self.client.get(reverse('core:digitalizacao_upload'))
        nova = DigitalizacaoFicha.objects.exclude(pk__in=[
            self.minha.pk, self.da_outra.pk, self.para_refazer.pk, self.conferida.pk, self.antiga.pk,
        ]).get()
        self.assertEqual(DigitalizacaoFicha.objects.filter(pk=self.para_refazer.pk).count(), 1)
        self.assertContains(pagina, 'Enviadas hoje')
        self.assertContains(pagina, 'Evolução')
        self.assertContains(pagina, reverse('core:detalhe_digitalizacao', args=[nova.pk]))
        self.assertNotContains(pagina, '<img')
        self.assertNotContains(pagina, nova.imagem.name)
        self.assertNotContains(pagina, '/media/')

        pre = self.client.get(reverse('core:digitalizacao_upload'), {
            'paciente': self.paciente_b.pk, 'tipo': 'anamnese',
        })
        self.assertEqual(pre.context['form'].initial['paciente'], self.paciente_b.pk)
        self.assertEqual(pre.context['form'].initial['tipo'], 'anamnese')
        self.assertContains(pre, 'value="anamnese" selected')

        self._entrar(self.dentista_user)
        negado = self.client.get(reverse('core:digitalizacao_upload'), {
            'paciente': self.paciente_b.pk, 'tipo': 'invasivo',
        })
        self.assertNotIn('paciente', negado.context['form'].initial)
        self.assertNotIn('tipo', negado.context['form'].initial)

    def test_pagina_do_paciente_so_para_quem_tem_prontuario(self):
        url = reverse('core:editar_paciente', args=[self.paciente_a.pk])
        self._entrar(self.admin)
        admin = self.client.get(url)
        self.assertContains(admin, 'Fichas antigas digitalizadas')
        self.assertContains(admin, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.assertContains(admin, reverse('core:detalhe_digitalizacao', args=[self.da_outra.pk]))
        self.assertNotContains(admin, self.minha.imagem.name)
        self.assertNotContains(admin, '/media/')
        self.assertLess(
            admin.content.decode().find(reverse('core:detalhe_digitalizacao', args=[self.da_outra.pk])),
            admin.content.decode().find(reverse('core:detalhe_digitalizacao', args=[self.antiga.pk])),
        )

        self._entrar(self.secretaria)
        secretaria = self.client.get(url)
        self.assertEqual(secretaria.status_code, 200)
        self.assertNotContains(secretaria, 'Fichas antigas digitalizadas')

        self._entrar(self.dentista_user)
        dentista = self.client.get(url)
        self.assertContains(dentista, 'Fichas antigas digitalizadas')
        self.assertEqual(
            self.client.get(reverse('core:editar_paciente', args=[self.paciente_b.pk])).status_code,
            403,
        )

        vazio = reverse('core:editar_paciente', args=[self.paciente_solto.pk])
        self._entrar(self.admin)
        self.conferida.paciente = None
        self.conferida.save(update_fields=['paciente'])
        self.assertContains(self.client.get(vazio), 'Nenhuma ficha digitalizada.')

    def test_dentista_inativo_nao_lista(self):
        self.dentista_a.ativo = False
        self.dentista_a.save(update_fields=['ativo'])
        self._entrar(self.dentista_user)
        self.assertEqual(self.client.get(reverse('core:listar_digitalizacoes')).status_code, 403)

    def test_confirmacao_no_html_e_sucesso_mostra_a_foto_gravada(self):
        self._entrar(self.secretaria)
        formulario = self.client.get(reverse('core:digitalizacao_upload'))
        self.assertContains(formulario, 'id="confirmacao-envio" class="confirmacao-envio" hidden')
        self.assertContains(formulario, 'Confirmar envio')
        self.assertContains(formulario, 'Corrigir')
        self.assertContains(formulario, 'data-salvar-envio')
        self.assertNotContains(formulario, '<img')

        resposta = self.client.post(reverse('core:digitalizacao_upload'), {
            'paciente': self.paciente_a.pk,
            'imagem': _png('confirmada.png'),
            'tipo': 'cadastro',
        })
        nova = DigitalizacaoFicha.objects.exclude(pk__in=[
            self.minha.pk, self.da_outra.pk, self.para_refazer.pk,
            self.conferida.pk, self.antiga.pk,
        ]).get()
        self.assertRedirects(
            resposta,
            f"{reverse('core:digitalizacao_upload')}?enviada={nova.pk}",
        )
        pagina = self.client.get(reverse('core:digitalizacao_upload'), {'enviada': nova.pk})
        self.assertContains(
            pagina,
            f'<strong class="nome-paciente">{self.paciente_a.nome_completo}</strong>',
        )
        self.assertContains(pagina, reverse('core:foto_digitalizacao', args=[nova.pk]))
        self.assertContains(pagina, 'Enviar outra folha deste paciente')
        self.assertContains(
            pagina,
            f'paciente={self.paciente_a.pk}&amp;tipo=cadastro',
        )
        self.assertContains(pagina, 'Enviar ficha de outro paciente')
        self.assertNotContains(pagina, nova.imagem.name)
        self.assertNotContains(pagina, '/media/')
        self.assertTrue(nova.imagem.storage.exists(nova.imagem.name))

        self._entrar(self.outra_secretaria)
        alheia = self.client.get(
            reverse('core:digitalizacao_upload'), {'enviada': nova.pk},
        )
        self.assertIsNone(alheia.context['ficha_enviada'])
        self.assertNotContains(alheia, '<img')

    def test_secretaria_marca_engano_so_na_propria_e_so_pendente(self):
        arquivo = self.minha.imagem.name
        self._entrar(self.secretaria)
        self.assertContains(
            self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk])),
            'Enviada por engano',
        )
        longo = self.client.post(
            reverse('core:marcar_engano_digitalizacao', args=[self.minha.pk]),
            {'motivo_engano': 'y' * 2001},
        )
        self.assertEqual(longo.status_code, 302)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

        self.assertEqual(
            self.client.post(
                reverse('core:marcar_engano_digitalizacao', args=[self.para_refazer.pk]),
                {'motivo_engano': 'tarde'},
            ).status_code,
            403,
        )
        self.para_refazer.refresh_from_db()
        self.assertEqual(self.para_refazer.status, DigitalizacaoFicha.Status.REFAZER)

        self.assertEqual(
            self.client.post(
                reverse('core:marcar_engano_digitalizacao', args=[self.da_outra.pk]),
                {},
            ).status_code,
            404,
        )
        self.da_outra.refresh_from_db()
        self.assertEqual(self.da_outra.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)

        self.assertEqual(self.client.get(
            reverse('core:marcar_engano_digitalizacao', args=[self.minha.pk]),
        ).status_code, 405)
        resposta = self.client.post(
            reverse('core:marcar_engano_digitalizacao', args=[self.minha.pk]),
            {'motivo_engano': '  folha de outra pessoa  '},
        )
        self.assertRedirects(resposta, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.status, DigitalizacaoFicha.Status.ENGANO)
        self.assertEqual(self.minha.motivo_engano, 'folha de outra pessoa')
        self.assertEqual(self.minha.imagem.name, arquivo)
        self.assertTrue(self.minha.imagem.storage.exists(arquivo))
        self.assertTrue(DigitalizacaoFicha.objects.filter(pk=self.minha.pk).exists())

        lista = self.client.get(reverse('core:listar_digitalizacoes'))
        self.assertContains(lista, 'Enviada por engano')
        self.assertContains(lista, 'Pendentes: 1. Para refazer: 1.')
        filtrada = self.client.get(reverse('core:listar_digitalizacoes'), {'situacao': 'engano'})
        self.assertContains(filtrada, 'folha de outra pessoa')
        self.assertNotContains(filtrada, 'Foto escura demais')

        self._entrar(self.admin)
        pagina = self.client.get(reverse('core:editar_paciente', args=[self.paciente_a.pk]))
        self.assertNotContains(pagina, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.assertContains(pagina, reverse('core:detalhe_digitalizacao', args=[self.da_outra.pk]))

        self._entrar(self.dentista_user)
        self.assertEqual(
            self.client.post(
                reverse('core:marcar_engano_digitalizacao', args=[self.da_outra.pk]),
                {'motivo_engano': ''},
            ).status_code,
            302,
        )
        self.da_outra.refresh_from_db()
        self.assertEqual(self.da_outra.status, DigitalizacaoFicha.Status.ENGANO)
        self.assertEqual(self.da_outra.motivo_engano, '')
        self.assertTrue(self.da_outra.imagem.storage.exists(self.da_outra.imagem.name))
        self._entrar(self.admin)
        pagina = self.client.get(reverse('core:editar_paciente', args=[self.paciente_a.pk]))
        self.assertNotContains(pagina, reverse('core:detalhe_digitalizacao', args=[self.da_outra.pk]))

    def test_troca_de_paciente_grava_historico_e_nega_quem_nao_pode(self):
        arquivo = self.minha.imagem.name
        self._entrar(self.secretaria)
        self.assertNotContains(
            self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk])),
            'Trocar paciente',
        )
        self.assertEqual(
            self.client.post(
                reverse('core:trocar_paciente_digitalizacao', args=[self.minha.pk]),
                {'paciente': self.paciente_b.pk, 'motivo': 'era outra'},
            ).status_code,
            403,
        )
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.paciente, self.paciente_a)
        self.assertEqual(self.minha.imagem.name, arquivo)
        self.assertFalse(TrocaPacienteDigitalizacao.objects.exists())

        self._entrar(self.dentista_user)
        negada = self.client.post(
            reverse('core:trocar_paciente_digitalizacao', args=[self.minha.pk]),
            {'paciente': self.paciente_b.pk, 'motivo': 'sem acesso'},
        )
        self.assertEqual(negada.status_code, 403)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.paciente, self.paciente_a)
        self.assertFalse(TrocaPacienteDigitalizacao.objects.exists())
        self.assertTrue(self.minha.imagem.storage.exists(arquivo))

        destino = self._paciente('Paciente segundo da Ana')
        self._consulta(destino, self.dentista_a)
        sem_motivo = self.client.post(
            reverse('core:trocar_paciente_digitalizacao', args=[self.minha.pk]),
            {'paciente': destino.pk, 'motivo': '   '},
        )
        self.assertEqual(sem_motivo.status_code, 302)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.paciente, self.paciente_a)
        self.assertFalse(TrocaPacienteDigitalizacao.objects.exists())

        resposta = self.client.post(
            reverse('core:trocar_paciente_digitalizacao', args=[self.minha.pk]),
            {'paciente': destino.pk, 'motivo': 'Foto era da outra pessoa'},
        )
        self.assertRedirects(resposta, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.paciente, destino)
        self.assertEqual(self.minha.imagem.name, arquivo)
        self.assertTrue(self.minha.imagem.storage.exists(arquivo))
        troca = TrocaPacienteDigitalizacao.objects.get()
        self.assertEqual(troca.ficha, self.minha)
        self.assertEqual(troca.paciente_anterior, self.paciente_a)
        self.assertEqual(troca.paciente_novo, destino)
        self.assertEqual(troca.trocado_por, self.dentista_user)
        self.assertEqual(troca.motivo, 'Foto era da outra pessoa')
        self.assertIsNotNone(troca.trocado_em)
        detalhe = self.client.get(reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        self.assertContains(detalhe, 'Foto era da outra pessoa')
        self.assertContains(detalhe, destino.nome_completo)
        self.assertContains(detalhe, self.paciente_a.nome_completo)

        self._entrar(self.admin)
        origem = self.client.get(reverse('core:editar_paciente', args=[self.paciente_a.pk]))
        self.assertNotContains(origem, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))
        novo = self.client.get(reverse('core:editar_paciente', args=[destino.pk]))
        self.assertContains(novo, reverse('core:detalhe_digitalizacao', args=[self.minha.pk]))

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(
            reverse('core:marcar_engano_digitalizacao', args=[self.antiga.pk]),
            {'motivo_engano': 'x'},
        ).status_code, 403)
        self.assertEqual(cliente.post(
            reverse('core:trocar_paciente_digitalizacao', args=[self.minha.pk]),
            {'paciente': self.paciente_b.pk, 'motivo': 'csrf'},
        ).status_code, 403)
        self.antiga.refresh_from_db()
        self.minha.refresh_from_db()
        self.assertEqual(self.antiga.status, DigitalizacaoFicha.Status.PENDENTE_REVISAO)
        self.assertEqual(self.minha.paciente, destino)
        self.assertEqual(TrocaPacienteDigitalizacao.objects.count(), 1)
        self.assertTrue(self.minha.imagem.storage.exists(arquivo))
