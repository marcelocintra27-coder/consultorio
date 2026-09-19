"""Segurança e operação em banco/arquivos exclusivamente descartáveis."""
from datetime import date, time
from io import BytesIO
from pathlib import Path
import hashlib
import json
import shutil
import tempfile
import subprocess
from unittest.mock import patch, MagicMock
from PIL import Image
from pypdf import PdfWriter
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, SimpleTestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from core.models import Paciente, Consulta
from locacao.models import Dentista, PerfilUsuario, Sala
from .models import Exame, EventoExame
from . import storage, antivirus
from .services import BloqueioTransitorioEsgotado, evento, invalidar


def imagem(nome='exame.png', formato='PNG', tamanho=(20, 20)):
    saida = BytesIO()
    Image.new('RGB', tamanho, 'white').save(saida, format=formato)
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


def pdf(paginas=1, senha=False, js=False, anexo=False):
    saida = BytesIO()
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=100, height=100)
    if senha:
        writer.encrypt('teste')
    if js:
        writer.add_js('app.alert("teste")')
    if anexo:
        writer.add_attachment('teste.txt', b'ficticio')
    writer.write(saida)
    return SimpleUploadedFile('exame.pdf', saida.getvalue(), 'application/pdf')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ExamesTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'privado'
        cfg = override_settings(EXAMES_ROOT=self.root, MEDIA_ROOT=Path(self.tmp.name) / 'media', EXAMES_RESERVA_BYTES=1)
        cfg.enable()
        self.addCleanup(cfg.disable)
        self.scan = patch('exames.antivirus.inspecionar', return_value='liberado').start()
        self.addCleanup(patch.stopall)
        self.paciente = Paciente.objects.create(nome_completo='Paciente fictício', cpf=None, data_nascimento=date(1990, 1, 1), telefone='123')
        self.outro = Paciente.objects.create(nome_completo='Outro fictício', cpf=None, data_nascimento=date(1991, 1, 1), telefone='123')
        sala = Sala.objects.create(nome='Sala fictícia')
        self.dentista = Dentista.objects.create(nome_completo='Dentista teste', sala=sala)
        self.user = User.objects.create_user('dentista_exames', password='teste')
        PerfilUsuario.objects.create(usuario=self.user, papel='dentista', dentista=self.dentista)
        self.consulta = Consulta.objects.create(paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 16), hora_inicio=time(10), hora_fim=time(11))
        self.admin = User.objects.create_superuser('admin_exames', password='teste')
        self.client.force_login(self.user)

    def url(self, acao, obj=None, paciente=None):
        kwargs = {'paciente_pk': (paciente or self.paciente).pk}
        if obj:
            kwargs['pk'] = obj.pk
        return reverse('core:exames:' + acao, kwargs=kwargs)

    def enviar(self, arquivo=None, acao='novo', obj=None, **dados):
        payload = {'categoria': 'foto', 'titulo': 'Arquivo fictício', 'arquivo': arquivo or imagem()}
        payload.update(dados)
        return self.client.post(self.url(acao, obj), payload)

    def criar(self, **dados):
        resposta = self.enviar(**dados)
        self.assertEqual(resposta.status_code, 302, resposta.content[:3000])
        return Exame.objects.latest('criado_em')

    def test_inclusao_integridade_download_auditoria(self):
        original = imagem()
        conteudo = original.read(); original.seek(0)
        exame = self.criar(arquivo=original, consulta=self.consulta.pk)
        self.assertEqual(exame.sha256, hashlib.sha256(conteudo).hexdigest())
        self.assertEqual(exame.criado_por, self.user)
        self.assertContains(self.client.get(self.url('detalhe', exame)), 'Disponível')
        resposta = self.client.get(self.url('download', exame))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b''.join(resposta.streaming_content), conteudo)
        resposta.close()
        self.assertIn('attachment;', resposta['Content-Disposition'])
        self.assertIn('no-store', resposta['Cache-Control'])
        self.assertEqual(resposta['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(list(exame.eventos.order_by('id').values_list('acao', flat=True)), ['incluido', 'liberado', 'consulta', 'download_iniciado'])
        self.assertFalse(list((self.root / 'temporarios').iterdir()))

    def test_jpeg_e_pdf_validos(self):
        self.assertEqual(self.criar(arquivo=imagem('teste.jpg', 'JPEG')).tipo, 'image/jpeg')
        self.assertEqual(self.criar(arquivo=pdf()).tipo, 'application/pdf')

    def test_roles_negados_em_todas_rotas(self):
        exame = self.criar()
        for papel in ('secretaria', 'auxiliar', 'sem_perfil', 'dentista_sem_vinculo', 'staff'):
            user = User.objects.create_user(papel, is_staff=papel == 'staff')
            if papel in ('secretaria', 'auxiliar'):
                PerfilUsuario.objects.create(usuario=user, papel=papel, dentista=self.dentista if papel == 'auxiliar' else None)
            if papel == 'dentista_sem_vinculo':
                dent = Dentista.objects.create(nome_completo='Outro', sala=Sala.objects.create(nome='Outra sala'))
                PerfilUsuario.objects.create(usuario=user, papel='dentista', dentista=dent)
            self.client.force_login(user)
            for acao in ('lista', 'novo', 'detalhe', 'download', 'corrigir', 'invalidar', 'inspecionar'):
                url = self.url(acao, exame if acao not in ('lista', 'novo') else None)
                resposta = self.client.post(url, {'justificativa': 'teste'}) if acao in ('invalidar', 'inspecionar') else self.client.get(url)
                self.assertEqual(resposta.status_code, 403, (papel, acao))
        self.assertTrue(EventoExame.objects.filter(acao='acesso_negado').exists())

    def test_anonimo_redirecionado(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url('lista')).status_code, 302)

    def test_admin_inclui_consulta_e_corrige_com_autoria_real(self):
        self.client.force_login(self.admin)
        exame = self.criar(criado_por=self.user.pk)
        self.assertEqual(exame.criado_por, self.admin)
        self.assertEqual(self.client.get(self.url('detalhe', exame)).status_code, 200)
        self.assertEqual(self.client.post(self.url('invalidar', exame), {'justificativa': 'Inclusão equivocada'}).status_code, 302)
        self.assertTrue(exame.invalidado)

    def test_outro_dentista_vinculado_le_sem_corrigir_autoria(self):
        exame = self.criar()
        user = User.objects.create_user('segunda_conta')
        PerfilUsuario.objects.create(usuario=user, papel='dentista', dentista=self.dentista)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url('detalhe', exame)).status_code, 200)
        self.assertEqual(self.client.get(self.url('corrigir', exame)).status_code, 403)
        self.assertEqual(self.client.post(self.url('invalidar', exame), {'justificativa': 'teste'}).status_code, 403)

    def test_perda_vinculo_e_dentista_inativo(self):
        exame = self.criar()
        self.dentista.ativo = False; self.dentista.save()
        self.assertEqual(self.client.get(self.url('download', exame)).status_code, 403)
        self.dentista.ativo = True; self.dentista.save()
        outra_consulta = Consulta.objects.create(paciente=self.outro, dentista=self.dentista, data=date(2026, 9, 17), hora_inicio=time(10), hora_fim=time(11))
        Consulta.objects.filter(pk=self.consulta.pk).update(dentista=None)
        self.assertEqual(self.client.get(self.url('detalhe', exame)).status_code, 403)

    def test_idor_paciente_arquivo_e_consulta(self):
        exame = self.criar()
        self.assertEqual(self.client.get(self.url('detalhe', exame, self.outro)).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url('detalhe', exame, self.outro)).status_code, 404)
        consulta = Consulta.objects.create(paciente=self.outro, dentista=self.dentista, data=date(2026, 9, 17), hora_inicio=time(10), hora_fim=time(11))
        self.assertEqual(self.enviar(consulta=consulta.pk).status_code, 200)
        self.assertEqual(Exame.objects.count(), 1)

    def test_csrf_upload_invalidacao_inspecao(self):
        exame = self.criar()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for acao in ('novo', 'invalidar', 'inspecionar'):
            resposta = client.post(self.url(acao, None if acao == 'novo' else exame), {'arquivo': imagem()})
            self.assertEqual(resposta.status_code, 403)
        self.assertFalse(list((self.root / 'temporarios').iterdir()))

    def test_upload_csrf_valido(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.user)
        client.get(self.url('novo'))
        resposta = client.post(self.url('novo'), {'csrfmiddlewaretoken': client.cookies['csrftoken'].value, 'titulo': 'Teste', 'categoria': 'foto', 'arquivo': imagem()})
        self.assertEqual(resposta.status_code, 302)

    def test_formatos_falsos_vazios_corrompidos(self):
        for nome, dados in [('x.svg', b'<svg/>'), ('x.png', b''), ('x.png', b'not png'), ('x.pdf', b'%PDF-broken'), ('x.exe', b'MZ123')]:
            resposta = self.enviar(SimpleUploadedFile(nome, dados))
            self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Exame.objects.exists())
        self.assertFalse(list((self.root / 'temporarios').iterdir()))

    def test_pdf_senha_javascript_anexo_e_paginas(self):
        for arquivo in (pdf(senha=True), pdf(js=True), pdf(anexo=True)):
            self.assertEqual(self.enviar(arquivo).status_code, 200)
        with override_settings(EXAMES_MAX_PAGES=1):
            self.assertEqual(self.enviar(pdf(paginas=2)).status_code, 200)
        self.assertFalse(Exame.objects.exists())

    def test_limite_pixels(self):
        with override_settings(EXAMES_MAX_PIXELS=100):
            self.assertEqual(self.enviar(imagem(tamanho=(11, 10))).status_code, 200)
        self.assertFalse(Exame.objects.exists())

    def test_limite_bytes_durante_upload_e_multiplos(self):
        with override_settings(EXAMES_MAX_BYTES=20):
            self.assertEqual(self.enviar().status_code, 200)
        resposta = self.client.post(self.url('novo'), {'titulo': 'Teste', 'categoria': 'foto', 'arquivo': [imagem(), imagem()]})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Exame.objects.exists())
        self.assertFalse(list((self.root / 'temporarios').iterdir()))

    def test_nome_malicioso_e_html_escapado(self):
        exame = self.criar(arquivo=imagem('../../x.png'), titulo='<script>alert(1)</script>', observacao='<img src=x onerror=alert(1)>')
        self.assertEqual(storage.caminho(exame.chave).name, str(exame.chave)+'.bin')
        resposta = self.client.get(self.url('detalhe', exame))
        self.assertContains(resposta, '&lt;script&gt;')
        self.assertNotContains(resposta, '<img src=x')

    def test_quarentena_reinspecao_e_malware(self):
        self.scan.return_value = 'quarentena'
        exame = self.criar()
        self.assertEqual(self.client.get(self.url('download', exame)).status_code, 409)
        self.scan.return_value = 'liberado'
        self.client.post(self.url('inspecionar', exame))
        self.assertEqual(exame.seguranca, 'liberado')
        self.scan.return_value = 'rejeitado'
        outro = self.criar()
        self.assertEqual(self.client.get(self.url('download', outro)).status_code, 409)
        self.client.post(self.url('inspecionar', outro))
        self.assertEqual(outro.seguranca, 'rejeitado')

    def test_adulteracao_ausencia_e_quarentena_adulterada(self):
        exame = self.criar()
        storage.caminho(exame.chave).write_bytes(b'adulterado')
        self.assertEqual(self.client.get(self.url('download', exame)).status_code, 409)
        self.assertEqual(exame.seguranca, 'integridade_falhou')
        outro = self.criar()
        storage.caminho(outro.chave).unlink()
        self.assertEqual(self.client.get(self.url('download', outro)).status_code, 409)
        self.scan.return_value = 'quarentena'
        terceiro = self.criar()
        storage.caminho(terceiro.chave).write_bytes(b'x')
        self.client.post(self.url('inspecionar', terceiro))
        self.assertEqual(terceiro.seguranca, 'integridade_falhou')

    def test_correcao_preserva_original_e_historico(self):
        exame = self.criar()
        original = storage.caminho(exame.chave).read_bytes()
        novo = self.criar(acao='corrigir', obj=exame, justificativa='Correção fictícia')
        self.assertEqual(novo.anterior, exame)
        self.assertTrue(exame.invalidado)
        self.assertEqual(storage.caminho(exame.chave).read_bytes(), original)
        resposta = self.client.get(self.url('download', exame))
        self.assertEqual(resposta.status_code, 200); resposta.close()
        self.assertEqual(self.enviar(acao='corrigir', obj=exame, justificativa='Reenvio').status_code, 200)
        self.assertEqual(Exame.objects.count(), 2)

    def test_justificativa_obrigatoria_invalidacao_unica(self):
        exame = self.criar()
        self.assertEqual(self.enviar(acao='corrigir', obj=exame).status_code, 200)
        self.client.post(self.url('invalidar', exame), {'justificativa': ' '})
        self.assertFalse(exame.invalidado)
        for _ in range(2):
            self.client.post(self.url('invalidar', exame), {'justificativa': 'Teste'})
        self.assertEqual(exame.eventos.filter(acao='invalidado').count(), 1)

    def test_invalidacao_repete_bloqueio_transitorio(self):
        exame = self.criar()
        tentativas = 0

        def evento_com_bloqueio(*args, **kwargs):
            nonlocal tentativas
            tentativas += 1
            if tentativas < 3:
                raise OperationalError('database is locked')
            return evento(*args, **kwargs)

        with patch('exames.services.evento', side_effect=evento_com_bloqueio), patch('exames.services.sleep') as espera:
            invalidar(self.user, exame, 'Invalidação fictícia')
        self.assertEqual(tentativas, 3)
        self.assertEqual(espera.call_count, 2)
        self.assertEqual(exame.eventos.filter(acao='invalidado').count(), 1)

    def test_invalidacao_bloqueio_esgota_cinco_tentativas(self):
        exame = self.criar()
        with patch('exames.services.evento', side_effect=OperationalError('database is locked')) as gravar, \
                patch('exames.services.sleep') as espera:
            with self.assertRaises(BloqueioTransitorioEsgotado):
                invalidar(self.user, exame, 'Invalidação fictícia')
        self.assertEqual(gravar.call_count, 5)
        self.assertEqual(espera.call_count, 4)
        self.assertEqual(exame.eventos.filter(acao='invalidado').count(), 0)

    def test_view_trata_apenas_bloqueio_transitorio_esgotado(self):
        exame = self.criar()
        url = self.url('invalidar', exame)
        with patch('exames.views.invalidar', side_effect=BloqueioTransitorioEsgotado('bloqueio')):
            resposta = self.client.post(url, {'justificativa': 'Teste'})
        self.assertEqual(resposta.status_code, 302)
        with patch('exames.views.invalidar', side_effect=OperationalError('erro inesperado')):
            with self.assertRaises(OperationalError):
                self.client.post(url, {'justificativa': 'Teste'})

    def test_imutabilidade_orm_cascata_e_auditoria(self):
        exame = self.criar()
        for func in [lambda: exame.save(), lambda: exame.delete(), lambda: Exame.objects.filter(pk=exame.pk).update(titulo='x'),
                     lambda: Exame.objects.all().delete(), lambda: Exame.objects.bulk_update([exame], ['titulo']),
                     lambda: Exame.objects.bulk_create([exame]), lambda: exame.eventos.first().delete(),
                     lambda: EventoExame.objects.all().update(resultado='x')]:
            with self.assertRaises(ValidationError):
                func()
        for obj in (self.paciente, self.user):
            with self.assertRaises(ProtectedError):
                obj.delete()

    def test_admin_somente_leitura_e_staff_negado(self):
        exame = self.criar()
        for modelo in (Exame, EventoExame):
            ma = admin.site._registry[modelo]
            req = RequestFactory().get('/'); req.user = self.admin
            self.assertTrue(ma.has_view_permission(req))
            self.assertFalse(ma.has_change_permission(req))
            self.assertFalse(ma.has_add_permission(req))
            self.assertFalse(ma.has_delete_permission(req))
            req.user = self.user
            self.assertFalse(ma.has_view_permission(req))

    def test_sem_acesso_publico_e_raiz_invalida(self):
        exame = self.criar()
        self.assertEqual(self.client.get('/media/originais/'+str(exame.chave)+'.bin').status_code, 404)
        with override_settings(EXAMES_ROOT=Path(self.tmp.name)/'media'/'exames'):
            with self.assertRaises(ImproperlyConfigured):
                storage.caminho(exame.chave)

    def test_espaco_insuficiente(self):
        with patch('exames.storage.shutil.disk_usage', return_value=type('Disk', (), {'free': 0})()):
            resposta = self.enviar()
        self.assertIn(resposta.status_code, (200, 503))
        self.assertFalse(Exame.objects.exists())

    def test_timeout_worker_e_falha_gravacao(self):
        with patch('exames.storage.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            self.assertEqual(self.enviar().status_code, 200)
        with patch('exames.storage.os.fsync', side_effect=OSError('sem espaço')):
            self.assertEqual(self.enviar().status_code, 503)
        self.assertFalse(Exame.objects.exists())
        self.assertFalse(list(storage.pasta_privada('originais').iterdir()))

    def test_rollback_auditoria_remove_novo_arquivo(self):
        with patch('exames.services.evento', side_effect=ValidationError('falha simulada')):
            self.assertEqual(self.enviar().status_code, 200)
        self.assertFalse(Exame.objects.exists())
        self.assertFalse(list(storage.pasta_privada('originais').iterdir()))

    def test_backup_restauracao_bytes_e_metadados(self):
        exame = self.criar()
        backup = Path(self.tmp.name) / 'backup'
        shutil.copytree(self.root, backup)
        restaurado = Path(self.tmp.name) / 'restaurado'
        shutil.copytree(backup, restaurado)
        with override_settings(EXAMES_ROOT=restaurado):
            with storage.abrir_verificado(Exame.objects.get(pk=exame.pk)) as arquivo:
                self.assertEqual(hashlib.sha256(arquivo.read()).hexdigest(), exame.sha256)

    def test_rejeicoes_nao_registram_conteudo_clinico(self):
        self.enviar(SimpleUploadedFile('nome-sensivel.svg', b'<svg>segredo</svg>'), titulo='Segredo clínico')
        dados = json.dumps(list(EventoExame.objects.values('acao', 'resultado', 'justificativa')))
        self.assertNotIn('segredo', dados.lower())
        self.assertNotIn('nome-sensivel', dados)

    def test_links_integrados_sem_alterar_prescricoes(self):
        self.assertContains(self.client.get(reverse('core:editar_paciente', args=[self.paciente.pk])), self.url('lista'))
        self.assertContains(self.client.get(reverse('core:ficha_consulta', args=[self.consulta.pk])), self.url('lista'))

    def test_limite_exato_e_mime_declarado_nao_confiavel(self):
        arquivo = imagem(); tamanho = arquivo.size
        arquivo.content_type = 'application/octet-stream'
        with override_settings(EXAMES_MAX_BYTES=tamanho):
            self.criar(arquivo=arquivo)
        with override_settings(EXAMES_MAX_BYTES=tamanho-1):
            self.assertEqual(self.enviar().status_code, 200)
        self.assertEqual(Exame.objects.count(), 1)

    def test_comandos_inventario_limpeza_apenas_temporarios_antigos(self):
        import os
        import time as clock
        from io import StringIO
        from django.core.management import call_command
        exame = self.criar()
        pasta = storage.pasta_privada('temporarios')
        antigo = pasta / 'recebimento-antigo'; antigo.write_bytes(b'temporario')
        recente = pasta / 'recebimento-recente'; recente.write_bytes(b'temporario')
        os.utime(antigo, (clock.time()-90000, clock.time()-90000))
        saida = StringIO()
        call_command('verificar_exames', stdout=saida)
        dados = json.loads(saida.getvalue())
        self.assertEqual(dados['integros'], 1)
        self.assertEqual(dados['temporarios'], 2)
        call_command('limpar_temporarios_exames', stdout=StringIO())
        self.assertTrue(antigo.exists())
        call_command('limpar_temporarios_exames', executar=True, stdout=StringIO())
        self.assertFalse(antigo.exists()); self.assertTrue(recente.exists())
        self.assertTrue(storage.caminho(exame.chave).exists())

    def test_colisao_arquivo_nao_sobrescreve(self):
        exame = self.criar()
        antes = storage.caminho(exame.chave).read_bytes()
        with self.assertRaises(FileExistsError):
            storage.gravar(imagem(), exame.chave)
        self.assertEqual(storage.caminho(exame.chave).read_bytes(), antes)

    def test_falha_auditoria_impede_download(self):
        exame = self.criar()
        with patch('exames.views.evento', side_effect=RuntimeError('auditoria indisponível')):
            with self.assertRaises(RuntimeError):
                self.client.get(self.url('download', exame))

    def test_consulta_mesmo_paciente_de_outro_dentista_negada(self):
        dent = Dentista.objects.create(nome_completo='Outro dentista', sala=Sala.objects.create(nome='Outra sala'))
        consulta = Consulta.objects.create(paciente=self.paciente, dentista=dent, data=date(2026, 9, 17), hora_inicio=time(10), hora_fim=time(11))
        self.assertEqual(self.enviar(consulta=consulta.pk).status_code, 200)
        self.assertFalse(Exame.objects.exists())


class AntivirusTests(SimpleTestCase):
    def test_protocolo_aprovacao_rejeicao_erro(self):
        for resposta, esperado in [(b'stream: OK\0', 'liberado'), (b'stream: Test FOUND\0', 'rejeitado'), (b'stream: ERROR\0', 'quarentena'), (b'OK', 'quarentena')]:
            sock = MagicMock(); sock.__enter__.return_value = sock
            sock.recv.side_effect = [resposta, b'']
            with patch('exames.antivirus.socket.create_connection', return_value=sock) as conn:
                self.assertEqual(antivirus.inspecionar(BytesIO(b'teste')), esperado)
                self.assertEqual(conn.call_args.args[0][0], '127.0.0.1')
                self.assertEqual(sock.sendall.call_args_list[0].args[0], b'zINSTREAM\0')

    def test_indisponibilidade_e_timeout_bloqueiam(self):
        for exc in (OSError('indisponível'), TimeoutError()):
            with patch('exames.antivirus.socket.create_connection', side_effect=exc):
                self.assertEqual(antivirus.inspecionar(BytesIO(b'teste')), 'quarentena')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConcorrenciaTests(TransactionTestCase):
    def test_invalidacoes_simultaneas_preservam_evento_unico(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections, IntegrityError, OperationalError
        from .services import invalidar
        user = User.objects.create_superuser('concorrencia', password='teste')
        paciente = Paciente.objects.create(nome_completo='Fictício', cpf=None, data_nascimento=date(1990, 1, 1), telefone='123')
        exame = Exame.objects.create(paciente=paciente, criado_por=user, categoria='foto', titulo='Fictício', tamanho=1, tipo='image/png', sha256='0'*64)
        barreira = Barrier(2)
        def executar():
            try:
                usuario = User.objects.get(pk=user.pk)
                obj = Exame.objects.get(pk=exame.pk)
                barreira.wait(timeout=10)
                invalidar(usuario, obj, 'Teste de concorrência')
                return 'ok'
            except (ValidationError, IntegrityError, OperationalError) as exc:
                return type(exc).__name__
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: executar(), range(2)))
        self.assertEqual(resultados.count('ok'), 1, resultados)
        self.assertNotIn('OperationalError', resultados)
        self.assertEqual(EventoExame.objects.filter(exame=exame, acao='invalidado').count(), 1)

    def test_gravacoes_simultaneas_nao_sobrescrevem(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        import uuid
        chave = uuid.uuid4(); barreira = Barrier(2)
        with tempfile.TemporaryDirectory() as tmp, override_settings(EXAMES_ROOT=Path(tmp)/'privado', EXAMES_RESERVA_BYTES=1):
            def executar():
                barreira.wait(timeout=10)
                try:
                    storage.gravar(imagem(), chave)
                    return 'ok'
                except FileExistsError:
                    return 'conflito'
            with ThreadPoolExecutor(max_workers=2) as executor:
                resultados = list(executor.map(lambda _: executar(), range(2)))
            self.assertEqual(resultados.count('ok'), 1)
            self.assertEqual(len(list(storage.pasta_privada('originais').iterdir())), 1)
