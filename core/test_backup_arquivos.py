"""Cópia dos arquivos do disco: só administrador, .zip completo e sem temporários."""
import io
import os
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import PerfilUsuario


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BackupArquivosTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.media = raiz / 'media'
        self.exames = raiz / 'private_exames'
        (self.media / 'fichas_legado' / '2026' / '10').mkdir(parents=True)
        (self.media / 'assinaturas').mkdir(parents=True)
        (self.exames / 'originais').mkdir(parents=True)
        (self.exames / 'temporarios').mkdir(parents=True)
        (self.media / 'fichas_legado' / '2026' / '10' / 'folha1.jpg').write_bytes(b'foto-1' * 1000)
        (self.media / 'assinaturas' / 'a.png').write_bytes(b'assinatura')
        (self.exames / 'originais' / 'abc.bin').write_bytes(b'exame')
        (self.exames / 'temporarios' / 'pela-metade').write_bytes(b'nao-entra')
        fora = raiz / 'fora.txt'
        fora.write_bytes(b'segredo')
        try:
            os.symlink(fora, self.media / 'atalho.txt')
        except OSError:
            pass
        self.cfg = override_settings(MEDIA_ROOT=self.media, EXAMES_ROOT=self.exames)
        self.cfg.enable()
        self.url = reverse('core:backup_arquivos')
        self.admin = User.objects.create_superuser('admin_backup', password='x')
        self.secretaria = User.objects.create_user('sec_backup', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)

    def tearDown(self):
        self.cfg.disable()
        self.tmp.cleanup()

    def _baixar(self):
        resposta = self.client.post(self.url)
        self.assertEqual(resposta.status_code, 200)
        conteudo = b''.join(resposta.streaming_content)
        return resposta, zipfile.ZipFile(io.BytesIO(conteudo))

    def test_secretaria_nao_acessa(self):
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_anonimo_vai_para_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_pagina_mostra_resumo(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Baixar cópia (.zip)')
        self.assertContains(resposta, '<strong>3</strong> arquivos')

    def test_zip_tem_os_arquivos_certos(self):
        self.client.force_login(self.admin)
        resposta, arquivo = self._baixar()
        self.assertEqual(resposta['Content-Type'], 'application/zip')
        self.assertIn('attachment;', resposta['Content-Disposition'])
        self.assertIsNone(arquivo.testzip())
        self.assertEqual(sorted(arquivo.namelist()), [
            'arquivos/assinaturas/a.png',
            'arquivos/fichas_legado/2026/10/folha1.jpg',
            'exames/originais/abc.bin',
        ])
        self.assertEqual(arquivo.read('arquivos/fichas_legado/2026/10/folha1.jpg'), b'foto-1' * 1000)
        self.assertEqual(arquivo.read('exames/originais/abc.bin'), b'exame')

    def test_disco_vazio_gera_zip_valido(self):
        self.cfg.disable()
        vazio = Path(self.tmp.name) / 'vazio'
        cfg = override_settings(MEDIA_ROOT=vazio / 'media', EXAMES_ROOT=vazio / 'exames')
        cfg.enable()
        try:
            self.client.force_login(self.admin)
            _, arquivo = self._baixar()
            self.assertEqual(arquivo.namelist(), [])
        finally:
            cfg.disable()
            self.cfg.enable()

    def test_card_aparece_na_administracao(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('core:administracao'))
        self.assertContains(resposta, self.url)
