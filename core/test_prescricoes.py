"""Regressões do fluxo de prescrições em banco e mídia descartáveis."""
import base64
from datetime import date, time
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from PIL import Image, ImageDraw
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings, Client, RequestFactory
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala
from . import models as m
from .integridade_documentos import verificar_integridade, assinaturas_documento


def assinatura_teste():
    imagem = Image.new('RGB', (640, 200), 'white')
    ImageDraw.Draw(imagem).line([(30, 140), (90, 45), (75, 135), (170, 70), (240, 140), (420, 65)], fill='black', width=4)
    saida = BytesIO()
    imagem.save(saida, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(saida.getvalue()).decode()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrescricoesTests(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        config = override_settings(MEDIA_ROOT=self.pasta.name)
        config.enable()
        self.addCleanup(config.disable)
        self.paciente = m.Paciente.objects.create(nome_completo='Paciente fictícia Ágata', cpf=None, data_nascimento=date(1990, 1, 2), telefone='123')
        self.outro_paciente = m.Paciente.objects.create(nome_completo='Outro paciente', cpf='999', data_nascimento=date(1990, 1, 2), telefone='123')
        self.dentista = Dentista.objects.create(nome_completo='Profissional de teste', sala=Sala.objects.create(nome='Sala teste'))
        self.usuario = User.objects.create_user('prescritor', password='teste')
        PerfilUsuario.objects.create(usuario=self.usuario, papel='dentista', dentista=self.dentista)
        m.Consulta.objects.create(paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 15), hora_inicio=time(9), hora_fim=time(10))
        self.client.force_login(self.usuario)

    def url(self, nome, ficha=None, paciente=None):
        args = [(paciente or self.paciente).pk]
        if ficha: args.append(ficha.pk)
        return reverse('core:' + nome, args=args)

    def payload(self, assinar=False, itens=1, **extras):
        dados = {'cro': 'TESTE/SP', 'texto_livre': '', 'orientacoes': 'Documento fictício para testes.', 'versao': 0,
                 'acao': 'assinar' if assinar else 'rascunho', 'assinatura_base64': assinatura_teste() if assinar else '',
                 'itens-TOTAL_FORMS': itens, 'itens-INITIAL_FORMS': 0, 'itens-MIN_NUM_FORMS': 0, 'itens-MAX_NUM_FORMS': 50}
        for i in range(itens):
            for campo, valor in {'medicamento': f'Medicamento fictício {i + 1}', 'concentracao_apresentacao': 'Apresentação de teste',
                                 'quantidade': '1 unidade fictícia', 'posologia': 'Posologia de teste — sem uso clínico.',
                                 'via': 'Via de teste', 'duracao': 'Duração de teste', 'orientacoes': 'Não utilizar.'}.items():
                dados[f'itens-{i}-{campo}'] = valor
        dados.update(extras)
        return dados

    def criar(self, assinar=True, **extras):
        resposta = self.client.post(self.url('nova_prescricao'), self.payload(assinar, **extras))
        self.assertEqual(resposta.status_code, 302, resposta.content[:2000])
        return m.Prescricao.objects.latest('pk')

    def adulterar(self, obj, campo, valor):
        # Corrupção simulada exclusivamente no banco de testes.
        with connection.cursor() as cursor:
            cursor.execute(f'UPDATE {connection.ops.quote_name(obj._meta.db_table)} SET {connection.ops.quote_name(obj._meta.get_field(campo).column)} = %s WHERE id = %s', [valor, obj.pk])
        obj.refresh_from_db()

    def retificar(self, ficha):
        return self.client.post(reverse('core:retificar_documento', args=['prescricao', ficha.pk]), {
            'nome_profissional': 'Nome forjado', 'cro': 'TESTE/SP', 'justificativa': 'Esclarecimento de teste',
            'conteudo': 'Anotação complementar fictícia á ç', 'assinatura_base64': assinatura_teste(),
        })

    def test_rascunho_sem_assinatura_cpf_opcional_e_auditoria(self):
        ficha = self.criar(False, cro='')
        self.assertEqual(ficha.status, 'rascunho')
        self.assertEqual(ficha.cpf_paciente, '')
        self.assertFalse(assinaturas_documento(ficha).exists())
        self.assertEqual(ficha.criado_por, self.usuario)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertContains(self.client.get(self.url('editar_prescricao', ficha)), 'data-assinatura-opcional="true"')

    def test_rascunho_edicao_exclusao_de_item_e_assinatura(self):
        ficha = self.criar(False, itens=2)
        antigos = list(ficha.itens.all())
        dados = self.payload(True, itens=3, versao=1)
        dados.update({'itens-INITIAL_FORMS': 2, 'itens-0-id': antigos[0].pk, 'itens-1-id': antigos[1].pk, 'itens-1-DELETE': 'on'})
        resposta = self.client.post(self.url('editar_prescricao', ficha), dados)
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, 'assinada')
        self.assertEqual(list(ficha.itens.values_list('ordem', flat=True)), [0, 1])
        self.assertTrue(verificar_integridade(ficha).integra)

    def test_multiplos_medicamentos_hash_assinatura_e_historico(self):
        ficha = self.criar(itens=3)
        self.assertEqual(ficha.itens.count(), 3)
        sig = assinaturas_documento(ficha).get()
        self.assertEqual(sig.usuario, self.usuario)
        self.assertTrue(verificar_integridade(ficha).integra)
        self.assertContains(self.client.get(self.url('ver_prescricao', ficha)), 'Prescrição assinada')
        resposta = self.client.get(reverse('core:ver_imagem_assinatura', args=[sig.pk]))
        self.assertEqual(resposta.status_code, 200)
        for fechar in resposta._resource_closers:
            fechar()

    def test_texto_livre_sem_medicamentos(self):
        ficha = self.criar(itens=0, texto_livre='Prescrição fictícia em texto livre.')
        self.assertEqual(ficha.itens.count(), 0)
        self.assertTrue(verificar_integridade(ficha).integra)

    def test_assinatura_exige_cro_conteudo_posologia_e_imagem(self):
        casos = [dict(cro=''), dict(assinatura_base64=''), dict(assinatura_base64='inválida'),
                 {'itens-0-posologia': ''}, {'itens-0-medicamento': ''}]
        for caso in casos:
            with self.subTest(caso=caso):
                self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True, **caso)).status_code, 200)
                self.assertFalse(m.Prescricao.objects.exists())
        self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True, itens=0)).status_code, 200)
        self.assertFalse(m.Prescricao.objects.exists())

    def test_formulario_obsoleto_nao_sobrescreve(self):
        ficha = self.criar(False)
        resposta = self.client.post(self.url('editar_prescricao', ficha), self.payload(False, versao=0))
        self.assertContains(resposta, 'Este rascunho foi atualizado')
        ficha.refresh_from_db()
        self.assertEqual(ficha.versao, 1)

    def test_png_com_cabecalho_mas_corrompido_nao_e_assinado(self):
        falso = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'x' * 80).decode()
        resposta = self.client.post(self.url('nova_prescricao'), self.payload(True, assinatura_base64=falso))
        self.assertContains(resposta, 'Assinatura PNG inválida')
        self.assertFalse(m.Prescricao.objects.exists())

    def test_ids_de_itens_de_outra_prescricao_sao_rejeitados(self):
        outra = self.criar(False)
        ficha = self.criar(False)
        dados = self.payload(False, versao=1)
        dados.update({'itens-INITIAL_FORMS': 1, 'itens-0-id': outra.itens.get().pk})
        resposta = self.client.post(self.url('editar_prescricao', ficha), dados)
        self.assertContains(resposta, 'Medicamento não pertence')
        self.assertEqual(ficha.itens.count(), 1)
        self.assertEqual(outra.itens.count(), 1)

    def test_limite_formset_e_acao_invalida(self):
        for extras in ({'itens-TOTAL_FORMS': 10000}, {'acao': 'apagar'}, {'versao': ''}):
            self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True, **extras)).status_code, 200)
            self.assertFalse(m.Prescricao.objects.exists())

    def test_autoria_e_paciente_nao_podem_ser_forjados(self):
        ficha = self.criar(dentista=999, criado_por=999, paciente=self.outro_paciente.pk, nome_profissional='Forjado', nome_paciente='Forjado')
        self.assertEqual(ficha.paciente, self.paciente)
        self.assertEqual(ficha.dentista, self.dentista)
        self.assertEqual(ficha.nome_profissional, self.dentista.nome_completo)

    def test_imutabilidade_orm_itens_assinatura_e_cascata(self):
        ficha = self.criar()
        item = ficha.itens.get()
        sig = assinaturas_documento(ficha).get()
        for obj, campo in [(ficha, 'texto_livre'), (item, 'posologia'), (sig, 'nome_assinante')]:
            with self.subTest(modelo=type(obj).__name__):
                setattr(obj, campo, 'Alterado')
                with self.assertRaises(ValidationError), transaction.atomic(): obj.save()
                with self.assertRaises(ValidationError), transaction.atomic(): type(obj).objects.filter(pk=obj.pk).update(**{campo: 'Alterado'})
                with self.assertRaises(ValidationError), transaction.atomic(): obj.delete()
        for obj in (self.paciente, self.dentista, self.usuario):
            with self.assertRaises((ValidationError, ProtectedError)), transaction.atomic(): obj.delete()
        with self.assertRaises(ValidationError), transaction.atomic():
            m.ItemPrescricao.objects.create(ficha=ficha, medicamento='Novo')
        ficha.refresh_from_db()
        self.assertTrue(verificar_integridade(ficha).integra)

    def test_reenvio_de_assinatura_nao_duplica(self):
        ficha = self.criar()
        resposta = self.client.post(self.url('editar_prescricao', ficha), self.payload(True, versao=1))
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(assinaturas_documento(ficha).count(), 1)

    def test_falha_na_assinatura_reverte_documento_e_itens(self):
        with patch('core.prescricoes.gravar_assinatura_manuscrita', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError): self.client.post(self.url('nova_prescricao'), self.payload(True))
        self.assertFalse(m.Prescricao.objects.exists())
        self.assertFalse(m.ItemPrescricao.objects.exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_admin_nao_edita_exclui_nem_emite(self):
        ficha = self.criar()
        usuario = User.objects.create_superuser('admin', password='teste')
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True)).status_code, 403)
        self.assertEqual(self.retificar(ficha).status_code, 403)
        self.assertEqual(self.client.get(self.url('ver_prescricao', ficha)).status_code, 200)
        request = RequestFactory().get('/')
        request.user = usuario
        modeladmin = admin.site._registry[m.Prescricao]
        self.assertFalse(modeladmin.has_add_permission(request))
        self.assertFalse(modeladmin.has_change_permission(request, ficha))
        self.assertFalse(modeladmin.has_delete_permission(request, ficha))
        self.assertEqual(self.client.post(reverse('admin:core_prescricao_change', args=[ficha.pk]), {'texto_livre': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:core_prescricao_delete', args=[ficha.pk]), {'post': 'yes'}).status_code, 403)

    def test_perfis_sem_acesso_clinico_nao_leem_emitem_retificam_ou_exportam(self):
        ficha = self.criar()
        for papel in ('secretaria', 'auxiliar', 'dentista', 'staff'):
            usuario = User.objects.create_user(papel, password='teste', is_staff=True)
            if papel != 'staff': PerfilUsuario.objects.create(usuario=usuario, papel=papel)
            self.client.force_login(usuario)
            with self.subTest(papel=papel):
                for nome in ('ver_prescricao', 'editar_prescricao', 'imprimir_prescricao', 'pdf_prescricao'):
                    self.assertEqual(self.client.get(self.url(nome, ficha)).status_code, 403)
                self.assertEqual(self.client.get(self.url('listar_prescricoes')).status_code, 403)
                self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True)).status_code, 403)
                self.assertEqual(self.retificar(ficha).status_code, 403)

    def test_outro_dentista_vinculado_le_mas_nao_edita_rascunho(self):
        ficha = self.criar(False)
        outro = Dentista.objects.create(nome_completo='Outro clínico', sala=Sala.objects.create(nome='Outra sala'))
        usuario = User.objects.create_user('outro', password='teste')
        PerfilUsuario.objects.create(usuario=usuario, papel='dentista', dentista=outro)
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(self.url('ver_prescricao', ficha)).status_code, 403)
        m.Consulta.objects.create(paciente=self.paciente, dentista=outro, data=date(2026, 9, 15), hora_inicio=time(10), hora_fim=time(11))
        self.assertEqual(self.client.get(self.url('ver_prescricao', ficha)).status_code, 200)
        self.assertEqual(self.client.post(self.url('editar_prescricao', ficha), self.payload(True, versao=1)).status_code, 403)

    def test_dentista_inativo_nao_emite(self):
        self.dentista.ativo = False
        self.dentista.save()
        self.assertEqual(self.client.post(self.url('nova_prescricao'), self.payload(True)).status_code, 403)

    def test_outra_conta_do_mesmo_profissional_pode_assinar_com_autoria_registrada(self):
        ficha = self.criar(False)
        usuario = User.objects.create_user('mesmo_profissional', password='teste')
        PerfilUsuario.objects.create(usuario=usuario, papel='dentista', dentista=self.dentista)
        self.client.force_login(usuario)
        dados = self.payload(True, versao=1)
        dados.update({'itens-INITIAL_FORMS': 1, 'itens-0-id': ficha.itens.get().pk})
        self.assertEqual(self.client.post(self.url('editar_prescricao', ficha), dados).status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.criado_por, self.usuario)
        self.assertEqual(assinaturas_documento(ficha).get().usuario, usuario)
        self.assertTrue(verificar_integridade(ficha).integra)

    def test_paciente_na_url_deve_corresponder_ao_documento(self):
        ficha = self.criar()
        m.Consulta.objects.create(paciente=self.outro_paciente, dentista=self.dentista, data=date(2026, 9, 15), hora_inicio=time(10), hora_fim=time(11))
        self.assertEqual(self.client.get(self.url('ver_prescricao', ficha, self.outro_paciente)).status_code, 404)

    def test_login_e_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url('listar_prescricoes')).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        self.assertEqual(client.post(self.url('nova_prescricao'), self.payload(True)).status_code, 403)

    def test_retificacao_preserva_original_identifica_autor_e_audita(self):
        ficha = self.criar()
        antes = list(m.Prescricao.objects.values())
        hashes = list(assinaturas_documento(ficha).values())
        self.assertEqual(self.retificar(ficha).status_code, 302)
        registro = ficha.retificacoes.get()
        self.assertEqual(registro.nome_profissional, self.dentista.nome_completo)
        self.assertEqual(registro.autor, self.usuario)
        self.assertTrue(verificar_integridade(registro).integra)
        self.assertEqual(list(m.Prescricao.objects.values()), antes)
        self.assertEqual(list(assinaturas_documento(ficha).values()), hashes)
        self.assertTrue(LogEntry.objects.filter(change_message__contains='Retificação').exists())
        with self.assertRaises(ValidationError), transaction.atomic(): registro.delete()
        with self.assertRaises(ValidationError):
            m.RetificacaoDocumento.objects.filter(pk=registro.pk).update(conteudo='alteração')

    def test_rascunho_nao_imprime_exporta_ou_retifica(self):
        ficha = self.criar(False)
        for nome in ('imprimir_prescricao', 'pdf_prescricao'):
            self.assertEqual(self.client.get(self.url(nome, ficha)).status_code, 409)
        self.assertEqual(self.retificar(ficha).status_code, 200)
        self.assertFalse(ficha.retificacoes.exists())

    def test_conteudo_adulterado_bloqueia_saida_e_retificacao(self):
        ficha = self.criar()
        self.adulterar(ficha.itens.get(), 'posologia', 'Alterada por SQL')
        self.assertFalse(verificar_integridade(ficha).integra)
        for nome in ('imprimir_prescricao', 'pdf_prescricao'):
            self.assertEqual(self.client.get(self.url(nome, ficha)).status_code, 409)
        self.retificar(ficha)
        self.assertFalse(ficha.retificacoes.exists())

    def test_imagem_ausente_e_adulterada_bloqueia_pdf(self):
        ficha = self.criar()
        imagem = Path(assinaturas_documento(ficha).get().imagem.path)
        imagem.write_bytes(b'adulterada')
        self.assertEqual(self.client.get(self.url('pdf_prescricao', ficha)).status_code, 409)
        imagem.unlink()
        self.assertEqual(self.client.get(self.url('pdf_prescricao', ficha)).status_code, 409)

    def test_retificacao_adulterada_bloqueia_impressao_e_pdf(self):
        ficha = self.criar()
        self.retificar(ficha)
        self.adulterar(ficha.retificacoes.get(), 'conteudo', 'Alterada')
        for nome in ('imprimir_prescricao', 'pdf_prescricao'):
            self.assertEqual(self.client.get(self.url(nome, ficha)).status_code, 409)

    def test_hash_ausente_e_autor_divergente_sao_detectados(self):
        ficha = self.criar()
        sig = assinaturas_documento(ficha).get()
        self.adulterar(sig, 'nome_assinante', 'Outra pessoa')
        self.assertFalse(verificar_integridade(ficha).integra)
        self.adulterar(sig, 'hash_conteudo', '')
        self.assertEqual(self.client.get(self.url('pdf_prescricao', ficha)).status_code, 409)

    def test_pdf_e_impressao_com_retificacao_e_texto_escapado(self):
        ficha = self.criar(itens=2, texto_livre='<script>exemplo</script> & orientação')
        self.retificar(ficha)
        resposta = self.client.get(self.url('imprimir_prescricao', ficha))
        self.assertContains(resposta, '&lt;script&gt;exemplo&lt;/script&gt;')
        self.assertContains(resposta, 'Anotação complementar fictícia')
        pdf = self.client.get(self.url('pdf_prescricao', ficha))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        self.assertIn('attachment;', pdf['Content-Disposition'])
        self.assertIn('no-store', pdf['Cache-Control'])

    def test_pdf_com_texto_longo(self):
        ficha = self.criar(itens=0, texto_livre=('Texto fictício para testar paginação e acentuação.\n' * 180))
        self.assertEqual(self.client.get(self.url('pdf_prescricao', ficha)).status_code, 200)
