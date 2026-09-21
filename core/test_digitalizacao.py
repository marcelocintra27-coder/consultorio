"""Regressões de digitalização: banco de testes e mídia descartável."""
from datetime import date, time
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from core.models import Paciente, Consulta, DigitalizacaoFicha
from locacao.models import Dentista, PerfilUsuario, Sala


def imagem(nome='ficha.png', formato='PNG', tamanho=(20, 20)):
    saida = BytesIO()
    Image.new('RGB', tamanho, 'white').save(saida, format=formato)
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DigitalizacaoTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        cfg = override_settings(MEDIA_ROOT=self.raiz / 'media',
                                FILE_UPLOAD_TEMP_DIR=self.raiz)
        cfg.enable()
        self.addCleanup(cfg.disable)
        scanner = patch('exames.antivirus.inspecionar', return_value='liberado')
        self.scan = scanner.start()
        self.addCleanup(scanner.stop)
        self.paciente = Paciente.objects.create(nome_completo='Paciente vinculado fictício',
            cpf=None, data_nascimento=date(1990, 1, 1), telefone='123')
        self.outro = Paciente.objects.create(nome_completo='Paciente alheio fictício',
            cpf=None, data_nascimento=date(1991, 1, 1), telefone='123')
        self.dentista = Dentista.objects.create(nome_completo='Dentista fictício',
            sala=Sala.objects.create(nome='Sala fictícia'))
        self.user = User.objects.create_user('dentista_digitalizacao', password='teste')
        PerfilUsuario.objects.create(usuario=self.user, papel='dentista', dentista=self.dentista)
        self.consulta = Consulta.objects.create(paciente=self.paciente, dentista=self.dentista,
            data=date(2026, 9, 21), hora_inicio=time(10), hora_fim=time(11))
        self.admin = User.objects.create_superuser('admin_digitalizacao', password='teste')
        self.negados = []
        for papel in ('secretaria', 'auxiliar'):
            usuario = User.objects.create_user(papel + '_digitalizacao', password='teste')
            PerfilUsuario.objects.create(usuario=usuario, papel=papel,
                dentista=self.dentista if papel == 'auxiliar' else None)
            self.negados.append(usuario)
        self.negados.append(User.objects.create_user('sem_perfil_digitalizacao', password='teste'))
        self.negados.append(User.objects.create_user('staff_digitalizacao', password='teste', is_staff=True))
        self.client.force_login(self.user)

    def enviar(self, arquivo=None, paciente=None, **extra):
        dados = {'paciente': self.paciente.pk if paciente is None else paciente,
                 'imagem': arquivo if arquivo is not None else imagem(), 'tipo': 'cadastro'}
        dados.update(extra)
        return self.client.post('/digitalizacao/nova/', dados)

    def registro(self, paciente=None, arquivo=None):
        return DigitalizacaoFicha.objects.create(
            paciente=paciente, imagem=arquivo if arquivo is not None else imagem(),
            digitalizado_por=self.admin)

    def url_ia(self, registro):
        return f'/digitalizacao/{registro.pk}/processar-ia/'

    def arquivos(self):
        return {p for p in self.raiz.rglob('*') if p.is_file()}

    def test_formulario_exclui_paciente_sem_vinculo(self):
        resposta = self.client.get('/digitalizacao/nova/')
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, self.outro.nome_completo)
        self.assertEqual(list(resposta.context['form'].fields['paciente'].queryset),
                         [self.paciente])

    def test_perfis_negados_get_post_sem_gravacao(self):
        for usuario in self.negados:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get('/digitalizacao/nova/').status_code, 403)
                self.assertEqual(self.enviar().status_code, 403)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()

    def test_ia_alheia_negada_antes_da_integracao(self):
        registro = self.registro(self.outro)
        with patch('core.views.processar_digitalizacao_com_ia') as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()

    def test_post_paciente_forjado_nao_grava(self):
        self.assertEqual(self.enviar(paciente=self.outro.pk).status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_dentista_sem_paciente_nao_grava(self):
        self.assertEqual(self.enviar(paciente='').status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_admin_sem_paciente_e_dentista_vinculado_incluem(self):
        self.assertEqual(self.enviar().status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.enviar(paciente='').status_code, 302)
        self.assertEqual(DigitalizacaoFicha.objects.count(), 2)

    def test_ia_sem_paciente_apenas_admin(self):
        registro = self.registro()
        with patch('core.views.processar_digitalizacao_com_ia', return_value=True) as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()
            self.client.force_login(self.admin)
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 302)
            processar.assert_called_once_with(registro)

    def test_ia_vinculo_atual_independe_autoria(self):
        registro = self.registro(self.paciente)
        with patch('core.views.processar_digitalizacao_com_ia', return_value=True) as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 302)
            processar.assert_called_once_with(registro)
            self.consulta.delete()
            processar.reset_mock()
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()

    def test_dentista_inativo_e_perfis_negados_nao_processam(self):
        registro = self.registro(self.paciente)
        self.dentista.ativo = False
        self.dentista.save(update_fields=['ativo'])
        for usuario in [self.user, *self.negados]:
            self.client.force_login(usuario)
            with patch('core.views.processar_digitalizacao_com_ia') as processar:
                self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
                processar.assert_not_called()
        self.client.force_login(self.user)
        self.assertEqual(self.enviar().status_code, 403)

    def test_anonimo_e_metodo_ia(self):
        registro = self.registro(self.paciente)
        self.assertEqual(self.client.get(self.url_ia(registro)).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get('/digitalizacao/nova/').status_code, 302)
        self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 302)

    def test_csrf_upload_e_ia(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.user)
        self.assertEqual(cliente.post('/digitalizacao/nova/',
            {'imagem': imagem(), 'paciente': self.paciente.pk, 'tipo': 'cadastro'}).status_code, 403)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        cliente.get('/digitalizacao/nova/')
        token = cliente.cookies['csrftoken'].value
        resposta = cliente.post('/digitalizacao/nova/',
            {'imagem': imagem(), 'paciente': self.paciente.pk, 'tipo': 'cadastro',
             'csrfmiddlewaretoken': token})
        self.assertEqual(resposta.status_code, 302)
        registro = DigitalizacaoFicha.objects.get()
        with patch('core.views.processar_digitalizacao_com_ia', return_value=True) as processar:
            self.assertEqual(cliente.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()
            self.assertEqual(cliente.post(self.url_ia(registro),
                {'csrfmiddlewaretoken': token}).status_code, 302)

    def test_formatos_estaticos_validos_nome_controlado(self):
        for formato, extensao in [('JPEG', 'jpg'), ('PNG', 'png'), ('GIF', 'gif'), ('WEBP', 'webp')]:
            with self.subTest(formato=formato):
                self.assertEqual(self.enviar(imagem('nome-paciente.' + extensao, formato)).status_code, 302)
                registro = DigitalizacaoFicha.objects.latest('pk')
                self.assertNotIn('nome-paciente', registro.imagem.name)
                self.assertTrue(Path(registro.imagem.path).is_file())

    def test_falsos_vazios_corrompidos_extensao_incompativel(self):
        arquivos = [SimpleUploadedFile('ficha.png', b''),
            SimpleUploadedFile('ficha.png', b'<html>nao imagem</html>'),
            SimpleUploadedFile('ficha.pdf', b'%PDF-1.4'),
            imagem('ficha.jpg', 'PNG'),
            SimpleUploadedFile('ficha.png', imagem().read()[:35])]
        for arquivo in arquivos:
            with self.subTest(nome=arquivo.name):
                self.assertEqual(self.enviar(arquivo).status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()

    def test_malware_indisponibilidade_nao_persistem(self):
        for estado in ('rejeitado', 'quarentena'):
            self.scan.return_value = estado
            with self.subTest(estado=estado):
                self.assertEqual(self.enviar().status_code, 200)
                self.assertFalse(DigitalizacaoFicha.objects.exists())
                self.assertEqual(self.arquivos(), set())

    def test_multiplos_arquivos_rejeitados(self):
        resposta = self.enviar([imagem(), imagem('outra.png')])
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()


    def test_outro_dentista_vinculado_pode_processar(self):
        segundo = Dentista.objects.create(nome_completo='Segundo dentista',
            sala=Sala.objects.create(nome='Outra sala'))
        usuario = User.objects.create_user('segundo_digitalizacao', password='teste')
        PerfilUsuario.objects.create(usuario=usuario, papel='dentista', dentista=segundo)
        Consulta.objects.create(paciente=self.paciente, dentista=segundo,
            data=date(2026, 9, 21), hora_inicio=time(11), hora_fim=time(12))
        registro = self.registro(self.paciente)
        self.client.force_login(usuario)
        with patch('core.views.processar_digitalizacao_com_ia', return_value=True) as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 302)
            processar.assert_called_once_with(registro)

    def test_limite_real_20_mib_e_excesso_no_recebimento(self):
        from .digitalizacao_uploads import MAX_BYTES
        self.assertEqual(MAX_BYTES, 20 * 1024 * 1024)
        original = imagem().read()
        limite = original + b'0' * (MAX_BYTES - len(original))
        self.assertEqual(self.enviar(SimpleUploadedFile('limite.png', limite)).status_code, 302)
        registro = DigitalizacaoFicha.objects.get()
        self.assertEqual(registro.imagem.size, MAX_BYTES)
        antes = self.arquivos()
        self.scan.reset_mock()
        self.assertEqual(self.enviar(SimpleUploadedFile('excesso.png', limite + b'0')).status_code, 200)
        self.assertEqual(DigitalizacaoFicha.objects.count(), 1)
        self.assertEqual(self.arquivos(), antes)
        self.scan.assert_not_called()

    def test_animacoes_rejeitadas(self):
        for formato, extensao in [('GIF', 'gif'), ('WEBP', 'webp')]:
            saida = BytesIO()
            Image.new('RGB', (20, 20), 'red').save(saida, format=formato, save_all=True,
                append_images=[Image.new('RGB', (20, 20), 'blue')], duration=100, loop=0)
            with self.subTest(formato=formato):
                self.assertEqual(self.enviar(SimpleUploadedFile('animada.' + extensao,
                    saida.getvalue())).status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()

    def test_dimensoes_acima_limite_rejeitadas(self):
        self.assertEqual(self.enviar(imagem(tamanho=(6400, 6400))).status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()

    def test_falhas_worker_nao_persistem_e_limpam_temporarios(self):
        import subprocess
        falhas = [subprocess.TimeoutExpired('worker', 15), OSError('worker indisponível')]
        for falha in falhas:
            with self.subTest(falha=type(falha).__name__), patch(
                    'core.digitalizacao_uploads.subprocess.run', side_effect=falha) as executar:
                self.assertEqual(self.enviar().status_code, 200)
                self.assertEqual(executar.call_args.kwargs['timeout'], 15)
            self.assertEqual(self.arquivos(), set())
            self.assertFalse(DigitalizacaoFicha.objects.exists())
        for retorno in (MagicMock(returncode=1, stdout=b'{}'),
                        MagicMock(returncode=0, stdout=b'nao-json'),
                        MagicMock(returncode=0, stdout=b'{"tipo":"application/pdf"}')):
            with patch('core.digitalizacao_uploads.subprocess.run', return_value=retorno):
                self.assertEqual(self.enviar().status_code, 200)
            self.assertEqual(self.arquivos(), set())
            self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.scan.assert_not_called()

    def test_scanner_timeout_nao_persiste(self):
        self.scan.side_effect = TimeoutError('tempo esgotado')
        self.assertEqual(self.enviar().status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_falha_banco_remove_arquivo_novo_e_reverte_registro(self):
        from django.db import IntegrityError
        from django.db.models.signals import post_save
        def falhar(sender, instance, **kwargs):
            self.assertTrue(Path(instance.imagem.path).exists())
            raise IntegrityError('falha simulada após gravação')
        post_save.connect(falhar, sender=DigitalizacaoFicha)
        try:
            self.assertEqual(self.enviar().status_code, 503)
        finally:
            post_save.disconnect(falhar, sender=DigitalizacaoFicha)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_falha_storage_nao_cria_registro(self):
        with patch('django.core.files.storage.FileSystemStorage._save',
                   side_effect=OSError('falha simulada de armazenamento')):
            self.assertEqual(self.enviar().status_code, 503)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_falha_temporario_retorna_indisponivel(self):
        with patch('core.digitalizacao_uploads.tempfile.NamedTemporaryFile',
                   side_effect=OSError('sem espaço temporário')):
            self.assertEqual(self.enviar().status_code, 503)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())

    def test_sucesso_nao_deixa_temporarios(self):
        self.assertEqual(self.enviar().status_code, 302)
        registro = DigitalizacaoFicha.objects.get()
        self.assertEqual(self.arquivos(), {Path(registro.imagem.path)})

    def test_campo_de_arquivo_inesperado_rejeitado(self):
        resposta = self.enviar(extra=imagem('extra.png'))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.arquivos(), set())
        self.scan.assert_not_called()

    def test_ia_revalida_legado_invalido_antes_de_chamar_fornecedor(self):
        import os
        from .ia_digitalizacao import processar_digitalizacao_com_ia
        registro = self.registro(self.paciente,
            SimpleUploadedFile('legado.png', b'conteudo ficticio invalido'))
        antes = self.arquivos()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'chave-ficticia-teste'}), patch(
                'core.ia_digitalizacao.Anthropic') as cliente, self.assertLogs(
                'core.ia_digitalizacao', level='ERROR'):
            self.assertFalse(processar_digitalizacao_com_ia(registro))
            cliente.assert_not_called()
        self.assertEqual(self.arquivos(), antes)
        self.scan.assert_not_called()

    def test_ia_legado_acima_limite_nao_chega_ao_worker(self):
        import os
        from .ia_digitalizacao import processar_digitalizacao_com_ia
        from .digitalizacao_uploads import MAX_BYTES
        registro = self.registro(self.paciente,
            SimpleUploadedFile('legado.png', b'0' * (MAX_BYTES + 1)))
        antes = self.arquivos()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'chave-ficticia-teste'}), patch(
                'core.ia_digitalizacao.Anthropic') as cliente, patch(
                'core.digitalizacao_uploads.subprocess.run') as worker, self.assertLogs(
                'core.ia_digitalizacao', level='ERROR'):
            self.assertFalse(processar_digitalizacao_com_ia(registro))
            cliente.assert_not_called()
            worker.assert_not_called()
        self.assertEqual(self.arquivos(), antes)

    def test_ia_legado_quarentena_nao_envia(self):
        import os
        from .ia_digitalizacao import processar_digitalizacao_com_ia
        registro = self.registro(self.paciente)
        self.scan.return_value = 'quarentena'
        antes = self.arquivos()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'chave-ficticia-teste'}), patch(
                'core.ia_digitalizacao.Anthropic') as cliente, self.assertLogs(
                'core.ia_digitalizacao', level='ERROR'):
            self.assertFalse(processar_digitalizacao_com_ia(registro))
            cliente.assert_not_called()
        self.assertEqual(self.arquivos(), antes)

    def test_ia_valida_envia_bytes_inspecionados_e_tipo_real(self):
        import os
        import base64
        from .ia_digitalizacao import processar_digitalizacao_com_ia
        arquivo = imagem('legado.jpg', 'JPEG')
        original = arquivo.read()
        arquivo.seek(0)
        registro = self.registro(self.paciente, arquivo)
        antes = self.arquivos()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'chave-ficticia-teste'}), patch(
                'core.ia_digitalizacao.Anthropic') as cliente:
            cliente.return_value.messages.create.return_value = MagicMock(
                content=[MagicMock(type='text', text='{"nome_paciente":{"valor":"Fictício"}}')])
            self.assertTrue(processar_digitalizacao_com_ia(registro))
            self.scan.assert_called_once()
            origem = cliente.return_value.messages.create.call_args.kwargs['messages'][0]['content'][0]['source']
            self.assertEqual(origem['media_type'], 'image/jpeg')
            self.assertEqual(base64.b64decode(origem['data']), original)
        registro.refresh_from_db()
        self.assertEqual(registro.texto_bruto_ia['nome_paciente']['valor'], 'Fictício')
        self.assertEqual(self.arquivos(), antes)
