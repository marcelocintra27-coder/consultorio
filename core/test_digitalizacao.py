"""Regressões de digitalização: banco de testes e mídia descartável."""
from contextlib import contextmanager
from datetime import date, time
from io import BytesIO
from pathlib import Path
import os
import tempfile
from unittest.mock import patch, MagicMock
from PIL import Image
from PIL.ExifTags import Base, GPS, IFD
from PIL.PngImagePlugin import PngInfo
from PIL.TiffImagePlugin import IFDRational
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from core.models import Paciente, Consulta, DigitalizacaoFicha
from locacao.models import Dentista, PerfilUsuario, Sala


def imagem(nome='ficha.png', formato='PNG', tamanho=(20, 20)):
    saida = BytesIO()
    Image.new('RGB', tamanho, 'white').save(saida, format=formato)
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


@contextmanager
def clamav(valor):
    with patch.dict(os.environ) as ambiente:
        if valor is None:
            ambiente.pop('CLAMAV_ATIVO', None)
        else:
            ambiente['CLAMAV_ATIVO'] = valor
        yield


def jpeg_com_exif():
    """JPEG deitado, com GPS, comentário e perfil de cor."""
    foto = Image.new('RGB', (48, 16), (255, 0, 0))
    for x in range(24, 48):
        for y in range(16):
            foto.putpixel((x, y), (0, 0, 255))
    exif = foto.getexif()
    exif[Base.Orientation] = 6
    gps = exif.get_ifd(IFD.GPSInfo)
    gps[GPS.GPSLatitudeRef] = 'S'
    gps[GPS.GPSLatitude] = (IFDRational(23, 1), IFDRational(33, 1), IFDRational(45, 100))
    gps[GPS.GPSLongitudeRef] = 'W'
    gps[GPS.GPSLongitude] = (IFDRational(46, 1), IFDRational(38, 1), IFDRational(12, 100))
    saida = BytesIO()
    foto.save(saida, format='JPEG', quality=95, exif=exif.tobytes(),
              icc_profile=b'perfil-icc-secreto', comment=b'comentario-secreto')
    dados = saida.getvalue()
    return SimpleUploadedFile('ficha.jpg', dados, 'image/jpeg'), dados


def png_com_texto(modo='RGBA'):
    if modo == 'RGBA':
        foto = Image.new('RGBA', (6, 4), (0, 0, 0, 0))
        foto.putpixel((1, 2), (9, 8, 7, 64))
    elif modo == 'LA':
        foto = Image.new('LA', (8, 5), (10, 255))
        foto.putpixel((2, 3), (10, 0))
    elif modo == 'L':
        foto = Image.new('L', (8, 5), 40)
        foto.putpixel((1, 1), 200)
    elif modo == 'P':
        foto = Image.new('P', (5, 5), 1)
        foto.putpalette([255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 6))
        foto.putpixel((0, 0), 0)
        foto.info['transparency'] = 0
    else:
        foto = Image.new(modo, (6, 4), 'white')
    meta = PngInfo()
    meta.add_text('Comment', 'segredo-texto-ficha')
    meta.add_itxt('Description', 'segredo-itxt-ficha', zip=False)
    saida = BytesIO()
    foto.save(saida, format='PNG', pnginfo=meta, icc_profile=b'perfil-icc-png')
    dados = saida.getvalue()
    return SimpleUploadedFile('ficha.png', dados, 'image/png'), dados, foto


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
        ambiente = patch.dict(os.environ, {'CLAMAV_ATIVO': '1'})
        ambiente.start()
        self.addCleanup(ambiente.stop)
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
        self.secretaria = User.objects.create_user('secretaria_digitalizacao', password='teste')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel='secretaria')
        self.negados = []
        auxiliar = User.objects.create_user('auxiliar_digitalizacao', password='teste')
        PerfilUsuario.objects.create(
            usuario=auxiliar, papel='auxiliar', dentista=self.dentista)
        self.negados.append(auxiliar)
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

    def temporarios(self):
        prefixos = ('validacao-digitalizacao-', 'reencode-digitalizacao-', 'digitalizacao-')
        return [p for p in self.arquivos() if p.name.startswith(prefixos)]

    def test_formulario_exclui_paciente_sem_vinculo(self):
        resposta = self.client.get('/digitalizacao/nova/')
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, self.outro.nome_completo)
        self.assertEqual(list(resposta.context['form'].fields['paciente'].queryset),
                         [self.paciente])
        self.assertContains(resposta, 'data-remover-arquivo hidden')
        self.assertContains(resposta, 'type="file"')

    def test_secretaria_envia_paciente_ativo_e_recebe_403_na_ia(self):
        inativo = Paciente.objects.create(
            nome_completo='Paciente inativo fictício', cpf=None,
            data_nascimento=date(1992, 1, 1), telefone='123', ativo=False)
        self.client.force_login(self.secretaria)
        resposta = self.client.get('/digitalizacao/nova/')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.paciente.nome_completo)
        self.assertContains(resposta, self.outro.nome_completo)
        self.assertNotContains(resposta, inativo.nome_completo)
        self.assertNotContains(resposta, '<img')
        self.assertEqual(self.enviar(paciente='').status_code, 200)
        self.assertEqual(self.enviar(paciente=inativo.pk).status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.enviar(paciente=self.outro.pk).status_code, 302)
        registro = DigitalizacaoFicha.objects.get()
        self.assertEqual(registro.paciente, self.outro)
        self.assertEqual(registro.digitalizado_por, self.secretaria)
        self.scan.assert_called()
        pagina = self.client.get('/digitalizacao/nova/')
        self.assertNotContains(pagina, registro.imagem.name)
        self.assertNotContains(pagina, '<img')
        with patch('core.views.processar_digitalizacao_com_ia') as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()

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
        self.assertLess(registro.imagem.size, MAX_BYTES)
        with Image.open(registro.imagem.path) as aberta:
            aberta.load()
            self.assertEqual((aberta.format, aberta.size), ('PNG', (20, 20)))
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
            recebido = base64.b64decode(origem['data'])
            self.assertNotEqual(recebido, original)
            with Image.open(BytesIO(recebido)) as aberta:
                aberta.load()
                self.assertEqual((aberta.format, aberta.size), ('JPEG', (20, 20)))
        registro.refresh_from_db()
        self.assertEqual(registro.texto_bruto_ia['nome_paciente']['valor'], 'Fictício')
        self.assertEqual(self.arquivos(), antes)

    def test_antivirus_ligado_somente_com_valor_1(self):
        from .digitalizacao_uploads import antivirus_ligado
        with clamav(None):
            self.assertFalse(antivirus_ligado())
        for valor in ('0', '', 'true', 'True', 'yes'):
            with clamav(valor):
                self.assertFalse(antivirus_ligado(), valor)
        with clamav('1'):
            self.assertTrue(antivirus_ligado())

    def test_jpg_png_sem_antivirus_nao_chamam_inspecionar(self):
        from .digitalizacao_uploads import validar_imagem
        for valor in (None, '0', '', 'true'):
            for nome, formato, media in (
                    ('ficha.jpg', 'JPEG', 'image/jpeg'),
                    ('ficha.jpeg', 'JPEG', 'image/jpeg'),
                    ('ficha.png', 'PNG', 'image/png')):
                with self.subTest(valor=valor, nome=nome):
                    self.scan.reset_mock()
                    if formato == 'JPEG':
                        arquivo = imagem(nome, 'JPEG')
                        original = arquivo.read()
                        arquivo.seek(0)
                    else:
                        arquivo, original, _foto = png_com_texto()
                        arquivo.name = nome
                    with clamav(valor):
                        dados, tipo = validar_imagem(arquivo, nome)
                    self.scan.assert_not_called()
                    self.assertEqual(tipo, media)
                    self.assertNotEqual(dados, original)
                    with Image.open(BytesIO(dados)) as aberta:
                        aberta.load()
                        self.assertEqual(aberta.format, 'JPEG' if formato == 'JPEG' else 'PNG')
                    self.assertEqual(self.temporarios(), [])

    def test_antivirus_ligado_inspeciona_original_e_recusa_sem_liberacao(self):
        from .digitalizacao_uploads import validar_imagem
        arquivo, original = jpeg_com_exif()
        capturado = {}

        def inspecionar(enviado):
            enviado.seek(0)
            capturado['dados'] = enviado.read()
            return 'liberado'

        self.scan.side_effect = inspecionar
        with clamav('1'):
            dados, tipo = validar_imagem(arquivo, 'ficha.jpg')
        self.assertEqual(capturado['dados'], original)
        self.assertEqual(tipo, 'image/jpeg')
        self.assertNotEqual(dados, original)
        with Image.open(BytesIO(dados)) as aberta:
            aberta.load()
        self.assertEqual(self.temporarios(), [])
        for estado in ('rejeitado', 'quarentena'):
            with self.subTest(estado=estado):
                self.scan.side_effect = None
                self.scan.return_value = estado
                recusado, _bruto = jpeg_com_exif()
                with clamav('1'):
                    with self.assertRaises(ValidationError) as ctx:
                        validar_imagem(recusado, 'ficha.jpg')
                self.assertIn('Imagem não liberada pela inspeção de segurança.',
                              ctx.exception.messages)
                self.assertEqual(self.temporarios(), [])

    def test_jpeg_salvo_sem_exif_gps_e_com_orientacao_aplicada(self):
        arquivo, original = jpeg_com_exif()
        with clamav(None):
            self.scan.reset_mock()
            self.assertEqual(self.enviar(arquivo).status_code, 302)
        self.scan.assert_not_called()
        registro = DigitalizacaoFicha.objects.get()
        salvo = Path(registro.imagem.path).read_bytes()
        self.assertNotEqual(salvo, original)
        self.assertNotIn(b'Exif\x00\x00', salvo)
        self.assertNotIn(b'comentario-secreto', salvo)
        self.assertNotIn(b'perfil-icc-secreto', salvo)
        with Image.open(BytesIO(salvo)) as aberta:
            aberta.load()
            self.assertEqual(aberta.format, 'JPEG')
            self.assertEqual(aberta.size, (16, 48))
            self.assertEqual(len(aberta.getexif()), 0)
            self.assertEqual(aberta.getexif().get_ifd(IFD.GPSInfo), {})
            self.assertNotIn('icc_profile', aberta.info)
            self.assertNotIn('comment', aberta.info)
            canto = aberta.getpixel((0, 0))
            self.assertGreater(canto[0], 200)
            self.assertLess(canto[2], 40)
        self.assertEqual(self.temporarios(), [])

    def test_png_salvo_sem_texto_e_transparencia_preservada(self):
        from .digitalizacao_uploads import validar_imagem
        arquivo, original, _foto = png_com_texto('RGBA')
        self.assertIn(b'segredo-texto-ficha', original)
        self.assertIn(b'segredo-itxt-ficha', original)
        with clamav('0'):
            self.scan.reset_mock()
            dados, tipo = validar_imagem(arquivo, 'ficha.png')
        self.scan.assert_not_called()
        self.assertEqual(tipo, 'image/png')
        self.assertNotEqual(dados, original)
        self.assertNotIn(b'segredo-texto-ficha', dados)
        self.assertNotIn(b'segredo-itxt-ficha', dados)
        with Image.open(BytesIO(dados)) as aberta:
            aberta.load()
            self.assertEqual(aberta.format, 'PNG')
            self.assertEqual(aberta.mode, 'RGBA')
            self.assertEqual(aberta.getpixel((1, 2)), (9, 8, 7, 64))
            self.assertFalse(aberta.text)
            self.assertNotIn('icc_profile', aberta.info)
        self.assertEqual(self.temporarios(), [])

    def test_png_p_l_la_convertidos_sem_texto(self):
        from .digitalizacao_uploads import validar_imagem
        esperados = {
            'P': 'RGBA',
            'L': 'RGB',
            'LA': 'RGBA',
        }
        for modo, saida in esperados.items():
            with self.subTest(modo=modo):
                arquivo, original, _foto = png_com_texto(modo)
                with clamav(''):
                    dados, _tipo = validar_imagem(arquivo, 'ficha.png')
                self.scan.assert_not_called()
                self.scan.reset_mock()
                self.assertNotEqual(dados, original)
                self.assertNotIn(b'segredo-texto-ficha', dados)
                self.assertNotIn(b'segredo-itxt-ficha', dados)
                with Image.open(BytesIO(dados)) as aberta:
                    aberta.load()
                    self.assertEqual(aberta.mode, saida)
                    self.assertFalse(getattr(aberta, 'text', {}))
                with Image.open(BytesIO(original)) as origem:
                    convertido = origem.convert(saida)
                    with Image.open(BytesIO(dados)) as aberta:
                        self.assertEqual(list(aberta.getdata()), list(convertido.getdata()))
                self.assertEqual(self.temporarios(), [])

    def test_gif_webp_sem_antivirus_recusados(self):
        from .digitalizacao_uploads import validar_imagem
        mensagem = 'Com o antivírus desligado, envie a foto da ficha em JPG ou PNG.'
        for valor in (None, '0', '', 'true'):
            for formato, extensao in (('GIF', 'gif'), ('WEBP', 'webp')):
                with self.subTest(valor=valor, formato=formato):
                    self.scan.reset_mock()
                    arquivo = imagem(f'ficha.{extensao}', formato)
                    with clamav(valor):
                        with self.assertRaises(ValidationError) as ctx:
                            validar_imagem(arquivo, arquivo.name)
                    self.assertIn(mensagem, ctx.exception.messages)
                    self.scan.assert_not_called()
                    self.assertEqual(self.temporarios(), [])
        with clamav(None):
            resposta = self.enviar(imagem('ficha.gif', 'GIF'))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, mensagem)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.temporarios(), [])

    def test_nao_imagem_renomeada_para_jpg_recusada_sem_temporario(self):
        from .digitalizacao_uploads import validar_imagem
        arquivo = SimpleUploadedFile('foto.jpg', b'isto nao e uma imagem')
        with self.assertRaises(ValidationError) as ctx:
            validar_imagem(arquivo, 'foto.jpg')
        self.assertIn('Imagem inválida', ctx.exception.messages[0])
        self.scan.assert_not_called()
        self.assertEqual(self.temporarios(), [])
        resposta = self.enviar(SimpleUploadedFile('foto.jpg', b'isto nao e uma imagem'))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DigitalizacaoFicha.objects.exists())
        self.assertEqual(self.temporarios(), [])
        self.assertEqual(self.arquivos(), set())

    def test_secretaria_envia_jpg_sem_antivirus_e_continua_sem_prontuario(self):
        self.client.force_login(self.secretaria)
        with clamav('0'):
            self.scan.reset_mock()
            self.assertEqual(self.enviar(
                imagem('ficha.jpg', 'JPEG'), paciente=self.outro.pk).status_code, 302)
        self.scan.assert_not_called()
        registro = DigitalizacaoFicha.objects.get()
        self.assertEqual(registro.digitalizado_por, self.secretaria)
        pagina = self.client.get('/digitalizacao/nova/')
        self.assertNotContains(pagina, registro.imagem.name)
        self.assertNotContains(pagina, '<img')
        with patch('core.views.processar_digitalizacao_com_ia') as processar:
            self.assertEqual(self.client.post(self.url_ia(registro)).status_code, 403)
            processar.assert_not_called()
        self.assertEqual(self.temporarios(), [])

    def test_ia_funciona_com_antivirus_desligado(self):
        import base64
        from .ia_digitalizacao import processar_digitalizacao_com_ia
        arquivo = imagem('legado.png', 'PNG')
        registro = self.registro(self.paciente, arquivo)
        with patch.dict(os.environ, {
                'ANTHROPIC_API_KEY': 'chave-ficticia-teste', 'CLAMAV_ATIVO': '0'}), patch(
                'core.ia_digitalizacao.Anthropic') as cliente:
            cliente.return_value.messages.create.return_value = MagicMock(
                content=[MagicMock(type='text', text='{"nome_paciente":{"valor":"Fictício"}}')])
            self.scan.reset_mock()
            self.assertTrue(processar_digitalizacao_com_ia(registro))
            self.scan.assert_not_called()
            cliente.assert_called_once()
            origem = cliente.return_value.messages.create.call_args.kwargs[
                'messages'][0]['content'][0]['source']
            self.assertEqual(origem['media_type'], 'image/png')
            recebido = base64.b64decode(origem['data'])
            with Image.open(BytesIO(recebido)) as aberta:
                aberta.load()
                self.assertEqual(aberta.format, 'PNG')
        registro.refresh_from_db()
        self.assertEqual(registro.texto_bruto_ia['nome_paciente']['valor'], 'Fictício')
        self.assertEqual(self.temporarios(), [])


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ExameSemAntivirusDigitalizacaoTests(TestCase):
    """O envio de exame continua indo para quarentena sem o clamd."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        cfg = override_settings(
            EXAMES_ROOT=raiz / 'privado', MEDIA_ROOT=raiz / 'media',
            FILE_UPLOAD_TEMP_DIR=raiz / 'tmp', EXAMES_RESERVA_BYTES=1)
        cfg.enable()
        self.addCleanup(cfg.disable)
        (raiz / 'tmp').mkdir()
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente exame fictício', cpf=None,
            data_nascimento=date(1990, 1, 1), telefone='123')
        dentista = Dentista.objects.create(
            nome_completo='Dentista exame fictício',
            sala=Sala.objects.create(nome='Sala exame fictícia'))
        self.user = User.objects.create_user('dentista_exame_ficha', password='teste')
        PerfilUsuario.objects.create(usuario=self.user, papel='dentista', dentista=dentista)
        Consulta.objects.create(
            paciente=self.paciente, dentista=dentista, data=date(2026, 9, 21),
            hora_inicio=time(10), hora_fim=time(11))
        self.client.force_login(self.user)

    def test_exame_vai_para_quarentena_quando_antivirus_indisponivel(self):
        from django.urls import reverse
        from exames.models import Exame
        from .digitalizacao_uploads import antivirus_ligado
        url = reverse('core:exames:novo', kwargs={'paciente_pk': self.paciente.pk})
        with clamav(''), patch(
                'exames.antivirus.socket.create_connection',
                side_effect=OSError('clamd ausente')) as conexao:
            self.assertFalse(antivirus_ligado())
            resposta = self.client.post(url, {
                'categoria': 'foto', 'titulo': 'Exame fictício', 'arquivo': imagem()})
        self.assertEqual(resposta.status_code, 302, resposta.content[:500])
        self.assertTrue(conexao.called)
        exame = Exame.objects.get()
        self.assertEqual(exame.seguranca, 'quarentena')
        self.assertEqual(
            list(exame.eventos.order_by('id').values_list('acao', flat=True)),
            ['incluido', 'quarentena'])
