import base64
import tempfile
from datetime import date, time
from pathlib import Path

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings, RequestFactory
from django.urls import reverse

from locacao.models import Sala, Dentista, PerfilUsuario
from . import models as m
from .assinatura import gravar_assinatura_manuscrita
from .integridade_documentos import (
    verificar_integridade, texto_documento, tipo_documento,
    assinaturas_documento, url_documento,
)
from .test_security import PNG


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DocumentosIntegridadeTests(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.pasta.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        self.paciente = m.Paciente.objects.create(nome_completo='Paciente áé ç', cpf='123', data_nascimento=date(1990, 1, 1), telefone='123')
        sala = Sala.objects.create(nome='Sala')
        self.dentista = Dentista.objects.create(nome_completo='Dentista', sala=sala)
        self.admin = User.objects.create_superuser('admin', password='x')
        self.clinico = User.objects.create_user('clinico', password='x', is_staff=True)
        PerfilUsuario.objects.create(usuario=self.clinico, papel='dentista', dentista=self.dentista)
        self.consulta = m.Consulta.objects.create(paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 14), hora_inicio=time(9), hora_fim=time(10))
        self.negados = []
        for papel in ('secretaria', 'auxiliar', 'dentista', 'staff'):
            user = User.objects.create_user(papel, password='x', is_staff=True)
            if papel != 'staff':
                outro = self.dentista if papel == 'auxiliar' else None
                if papel == 'dentista':
                    outro = Dentista.objects.create(nome_completo='Dentista sem vínculo', sala=Sala.objects.create(nome='Sala sem vínculo'))
                PerfilUsuario.objects.create(usuario=user, papel=papel, dentista=outro)
            user.user_permissions.set(Permission.objects.filter(content_type__app_label='core'))
            self.negados.append(user)
        self.clinico.user_permissions.set(Permission.objects.filter(content_type__app_label='core'))
        self.client.force_login(self.clinico)

    def criar(self, tipo='evolucao', profissional_m2m=None):
        if tipo == 'evolucao':
            doc = m.RegistroEvolucaoClinica.objects.create(paciente=self.paciente, data=date.today(), procedimento_etapa='Exame', descricao_clinica='Conteúdo original ç', nome_profissional='Dentista', cro='123', criado_por=self.clinico)
        else:
            modelo = {'anamnese': m.FichaCadastroAnamnese, 'plano_tratamento': m.FichaPlanoTratamento, 'autorizacao_custo': m.FichaAutorizacaoCusto}[tipo]
            doc = modelo.objects.create(paciente=self.paciente, nome_completo='Paciente', data_nascimento=date(1990, 1, 1), cpf='123', status='concluida')
        alvos = [(tipo, doc.pk, 'dentista' if tipo == 'evolucao' else 'paciente')]
        if tipo == 'anamnese':
            alvos.append((tipo, doc.pk, 'dentista'))
        if tipo == 'plano_tratamento':
            item = m.ItemConsentimentoProcedimento.objects.create(ficha=doc, procedimento='Exame')
            item.dentistas.add(profissional_m2m or self.dentista)
            prof = m.ResponsavelPlanoTratamento.objects.create(ficha=doc, nome='Dentista', cro='123', dentista=self.dentista)
            alvos += [('plano_procedimento', item.pk, 'paciente'), ('plano_profissional', prof.pk, 'dentista')]
        if tipo == 'autorizacao_custo':
            m.ItemAutorizacaoCusto.objects.create(ficha=doc, tipo='outros_exames', descricao='Exame', quantidade=1, valor='80.00')
        for tipo_sig, pk, papel in alvos:
            gravar_assinatura_manuscrita(
                tipo_documento=tipo_sig, documento_id=pk, papel=papel,
                nome_assinante='Assinante', imagem_data_url='data:image/png;base64,' + base64.b64encode(PNG).decode(),
                conteudo_para_hash=texto_documento(doc), paciente=self.paciente, usuario=self.clinico,
            )
        return doc

    def adulterar(self, obj, campo, valor):
        # Simula dados históricos já corrompidos, sem contornar as proteções
        # no código de produção. Somente no banco descartável de testes.
        tabela = connection.ops.quote_name(obj._meta.db_table)
        coluna = connection.ops.quote_name(obj._meta.get_field(campo).column)
        with connection.cursor() as cursor:
            cursor.execute(f'UPDATE {tabela} SET {coluna} = %s WHERE id = %s', [valor, obj.pk])
        obj.refresh_from_db()

    def payload(self):
        return {'nome_profissional': 'Dentista', 'cro': '123', 'justificativa': 'Esclarecimento necessário', 'conteudo': 'Anotação complementar á ç <script>alert(1)</script>', 'assinatura_base64': 'data:image/png;base64,' + base64.b64encode(PNG).decode()}

    def url_retificar(self, doc):
        return reverse('core:retificar_documento', args=[tipo_documento(doc), doc.pk])

    def test_hashes_historicos_e_telas_dos_quatro_tipos(self):
        for tipo in ('evolucao', 'anamnese', 'plano_tratamento', 'autorizacao_custo'):
            doc = self.criar(tipo)
            antes = list(assinaturas_documento(doc).values())
            self.assertTrue(verificar_integridade(doc).integra, tipo)
            self.assertContains(self.client.get(url_documento(doc)), 'Integridade conferida')
            self.assertEqual(antes, list(assinaturas_documento(doc).values()))

    def test_conteudo_divergente_alerta_e_bloqueia_retificacao(self):
        doc = self.criar()
        assinatura = assinaturas_documento(doc).get()
        hash_original = assinatura.hash_conteudo
        self.adulterar(doc, 'descricao_clinica', 'Adulterado')
        self.assertFalse(verificar_integridade(doc).integra)
        self.assertContains(self.client.get(url_documento(doc)), 'conteúdo divergente')
        self.client.post(self.url_retificar(doc), self.payload())
        self.assertFalse(m.RetificacaoDocumento.objects.exists())
        resposta = self.client.get(reverse('core:ver_imagem_assinatura', args=[assinatura.pk]))
        self.assertContains(resposta, 'Integridade não confirmada', status_code=409)
        assinatura.refresh_from_db()
        self.assertEqual(hash_original, assinatura.hash_conteudo)

    def test_hashes_ausentes_nao_sao_integros(self):
        doc = self.criar()
        assinatura = assinaturas_documento(doc).get()
        for campo in ('hash_conteudo', 'hash_imagem'):
            self.adulterar(assinatura, campo, '')
            self.assertFalse(verificar_integridade(doc).integra)
        self.assertIn('hash do conteúdo ausente', ' '.join(verificar_integridade(doc).ocorrencias))

    def test_arquivo_alterado_ou_indisponivel(self):
        doc = self.criar()
        assinatura = assinaturas_documento(doc).get()
        arquivo = Path(assinatura.imagem.path)
        arquivo.write_bytes(b'imagem adulterada')
        self.assertIn('imagem divergente', ' '.join(verificar_integridade(doc).ocorrencias))
        arquivo.unlink()
        self.assertIn('arquivo de assinatura indisponível', ' '.join(verificar_integridade(doc).ocorrencias))
        self.assertEqual(self.client.get(reverse('core:ver_imagem_assinatura', args=[assinatura.pk])).status_code, 409)

    def test_documento_sem_assinatura_nao_e_integro(self):
        doc = m.RegistroEvolucaoClinica.objects.create(paciente=self.paciente, data=date.today(), procedimento_etapa='Legítimo pendente', descricao_clinica='texto', nome_profissional='D', cro='123')
        self.assertFalse(verificar_integridade(doc).integra)

    def test_imutabilidade_save_update_delete_e_cascata(self):
        doc = self.criar()
        doc.descricao_clinica = 'Tentativa'
        with self.assertRaises(ValidationError):
            doc.save()
        with self.assertRaises(ValidationError):
            type(doc).objects.filter(pk=doc.pk).update(descricao_clinica='Tentativa')
        for alvo in (doc, assinaturas_documento(doc).get(), self.paciente, self.clinico):
            with self.assertRaises((ValidationError, ProtectedError)), transaction.atomic():
                alvo.delete()
        with self.assertRaises(ValidationError), transaction.atomic():
            type(doc).objects.filter(pk=doc.pk).delete()
        doc.refresh_from_db()
        self.assertEqual(doc.descricao_clinica, 'Conteúdo original ç')

    def test_assinatura_nao_pode_ser_alterada(self):
        sig = assinaturas_documento(self.criar()).get()
        with self.assertRaises(ValidationError):
            m.AssinaturaEletronica.objects.filter(pk=sig.pk).update(hash_conteudo='0' * 64)
        sig.documento_id += 100
        with self.assertRaises(ValidationError):
            sig.save()

    def test_itens_e_profissionais_assinados_imutaveis(self):
        plano = self.criar('plano_tratamento')
        item = plano.itens.get()
        for alvo, campo in ((item, 'procedimento'), (plano.profissionais.get(), 'nome')):
            setattr(alvo, campo, 'Alterado')
            with self.assertRaises(ValidationError):
                alvo.save()
            with self.assertRaises(ValidationError), transaction.atomic():
                alvo.delete()
        for operacao in (lambda: item.dentistas.clear(), lambda: self.dentista.itens_consentimento_plano.clear(), lambda: item.dentistas.remove(self.dentista)):
            with self.assertRaises(ValidationError), transaction.atomic():
                operacao()
        with self.assertRaises(ValidationError):
            m.ItemConsentimentoProcedimento.objects.create(ficha=plano, procedimento='Novo indevido')
        self.assertTrue(verificar_integridade(plano).integra)

    def test_reparentear_item_para_documento_assinado_bloqueado(self):
        plano = self.criar('plano_tratamento')
        rascunho = m.FichaPlanoTratamento.objects.create(paciente=self.paciente, nome_completo='P', data_nascimento=date.today(), cpf='123')
        item = m.ItemConsentimentoProcedimento.objects.create(ficha=rascunho, procedimento='Rascunho')
        with self.assertRaises(ValidationError):
            type(item).objects.filter(pk=item.pk).update(ficha_id=plano.pk)

    def test_rascunho_continua_editavel(self):
        doc = m.FichaAutorizacaoCusto.objects.create(paciente=self.paciente, nome_completo='P', data_nascimento=date.today(), cpf='123')
        doc.nome_completo = 'Corrigido'
        doc.save()
        item = m.ItemAutorizacaoCusto.objects.create(ficha=doc, tipo='outros_exames', descricao='rascunho', quantidade=1, valor=1)
        item.delete()
        self.assertEqual(type(doc).objects.get(pk=doc.pk).nome_completo, 'Corrigido')

    def test_admin_nega_edicao_exclusao_e_acao_em_lote(self):
        doc = self.criar()
        self.client.force_login(self.admin)
        for obj in (doc, assinaturas_documento(doc).get()):
            prefixo = 'admin:core_' + obj._meta.model_name
            self.assertEqual(self.client.get(reverse(prefixo + '_change', args=[obj.pk])).status_code, 200)
            self.assertEqual(self.client.post(reverse(prefixo + '_change', args=[obj.pk]), {'descricao_clinica': 'Alterar'}).status_code, 403)
            self.assertEqual(self.client.post(reverse(prefixo + '_delete', args=[obj.pk]), {'post': 'yes'}).status_code, 403)
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        with self.assertRaises(Exception) as erro:
            admin.site._registry[type(doc)].delete_queryset(request, type(doc).objects.all())
        from django.core.exceptions import PermissionDenied
        self.assertIsInstance(erro.exception, PermissionDenied)

    def test_retificacao_quatro_tipos_preserva_original_e_hash(self):
        for tipo in ('evolucao', 'anamnese', 'plano_tratamento', 'autorizacao_custo'):
            doc = self.criar(tipo)
            antes = type(doc).objects.values().get(pk=doc.pk)
            hashes = list(assinaturas_documento(doc).values())
            resposta = self.client.post(self.url_retificar(doc), self.payload())
            self.assertEqual(resposta.status_code, 302, resposta.content)
            ret = doc.retificacoes.get()
            self.assertEqual(ret.autor, self.clinico)
            self.assertTrue(verificar_integridade(ret).integra)
            self.assertEqual(antes, type(doc).objects.values().get(pk=doc.pk))
            self.assertEqual(hashes, list(assinaturas_documento(doc).values()))
            html = self.client.get(url_documento(doc))
            self.assertContains(html, 'Anotação complementar á ç &lt;script&gt;')
        self.assertFalse(m.MovimentoCaixa.objects.exists())
        self.assertFalse(m.RecebimentoPaciente.objects.exists())

    def test_retificacao_imutavel_e_original_protegido(self):
        doc = self.criar()
        self.client.post(self.url_retificar(doc), self.payload())
        ret = doc.retificacoes.get()
        ret.conteudo = 'Mudança'
        with self.assertRaises(ValidationError):
            ret.save()
        with self.assertRaises((ValidationError, ProtectedError)), transaction.atomic():
            doc.delete()
        with self.assertRaises(ValidationError), transaction.atomic():
            ret.delete()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('admin:core_retificacaodocumento_change', args=[ret.pk]), self.payload()).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:core_retificacaodocumento_delete', args=[ret.pk]), {'post': 'yes'}).status_code, 403)

    def test_multiplas_retificacoes_preservadas_e_auditaveis(self):
        doc = self.criar()
        for texto in ('Primeira correção', 'Segunda correção'):
            self.client.post(self.url_retificar(doc), dict(self.payload(), conteudo=texto))
        self.assertEqual(doc.retificacoes.count(), 2)
        resposta = self.client.get(url_documento(doc))
        self.assertContains(resposta, 'Primeira correção')
        self.assertContains(resposta, 'Segunda correção')

    def test_retificacao_exige_assinatura_e_campos(self):
        doc = self.criar()
        for campo in ('assinatura_base64', 'justificativa', 'conteudo', 'cro', 'nome_profissional'):
            dados = dict(self.payload(), **{campo: ''})
            self.assertEqual(self.client.post(self.url_retificar(doc), dados).status_code, 200)
        self.assertFalse(doc.retificacoes.exists())

    def test_retificacao_exatamente_um_original_no_banco(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.RetificacaoDocumento.objects.create(autor=self.clinico, nome_profissional='D', cro='1', justificativa='Motivo', conteudo='Texto')

    def test_perfis_negados_mesmo_com_staff_e_permissoes_admin(self):
        doc = self.criar()
        for user in self.negados:
            self.client.force_login(user)
            for url in (self.url_retificar(doc), url_documento(doc)):
                self.assertEqual(self.client.get(url).status_code, 403, user.username)
                self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
            url_admin = reverse('admin:core_registroevolucaoclinica_changelist')
            resposta = self.client.get(url_admin)
            self.assertNotContains(resposta, 'Conteúdo original', status_code=resposta.status_code)
        self.assertFalse(m.RetificacaoDocumento.objects.exists())

    def test_legado_preservado_leitura_clinica_e_sem_novos_no_admin(self):
        legado = m.Evolucao.objects.create(paciente=self.paciente, data=date(2000, 1, 1), descricao='Legado original á ç')
        antes = m.Evolucao.objects.values().get(pk=legado.pk)
        self.assertContains(self.client.get(reverse('core:ficha_evolucao_clinica', args=[self.paciente.pk])), 'Legado original á ç')
        with self.assertRaises(ValidationError):
            m.Evolucao.objects.filter(pk=legado.pk).update(descricao='Converter')
        with self.assertRaises(ValidationError), transaction.atomic():
            legado.delete()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('admin:core_evolucao_add')).status_code, 403)
        self.assertEqual(antes, m.Evolucao.objects.values().get(pk=legado.pk))
        self.assertFalse(m.AssinaturaEletronica.objects.exists())

    def test_anexo_preservado_e_fora_do_formulario(self):
        from .forms import FichaAutorizacaoCustoForm
        self.assertNotIn('arquivo', FichaAutorizacaoCustoForm().fields)
        doc = self.criar('autorizacao_custo')
        self.adulterar(doc, 'arquivo', 'autorizacoes/legado.pdf')
        self.client.post(self.url_retificar(doc), self.payload())
        doc.refresh_from_db()
        self.assertEqual(doc.arquivo.name, 'autorizacoes/legado.pdf')

    def test_anamnese_com_assinatura_paciente_adulterada_nao_conclui(self):
        doc = self.criar('anamnese')
        self.adulterar(doc, 'status', 'aguardando_dentista')
        self.adulterar(doc, 'nome_completo', 'Alterado fora da aplicação')
        antes = list(assinaturas_documento(doc).values())
        resposta = self.client.post(url_documento(doc), {'assinatura_dentista_base64': self.payload()['assinatura_base64']})
        self.assertContains(resposta, 'Integridade não confirmada')
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'aguardando_dentista')
        self.assertEqual(antes, list(assinaturas_documento(doc).values()))

    def test_assinatura_duplicada_nao_substitui_original(self):
        doc = self.criar()
        antes = list(assinaturas_documento(doc).values())
        with self.assertRaises(ValidationError):
            gravar_assinatura_manuscrita(tipo_documento='evolucao', documento_id=doc.pk, papel='dentista', nome_assinante='Outro', imagem_data_url=self.payload()['assinatura_base64'], conteudo_para_hash=texto_documento(doc), paciente=self.paciente)
        self.assertEqual(antes, list(assinaturas_documento(doc).values()))

    def test_itens_da_autorizacao_e_admin_inline_protegidos(self):
        doc = self.criar('autorizacao_custo')
        item = doc.itens.get()
        with self.assertRaises(ValidationError):
            type(item).objects.filter(pk=item.pk).update(valor=999)
        with self.assertRaises(ValidationError), transaction.atomic():
            item.delete()
        request = RequestFactory().get('/admin/')
        request.user = self.admin
        inline = admin.site._registry[type(doc)].get_inline_instances(request, doc)[0]
        self.assertFalse(inline.has_add_permission(request, doc))
        self.assertFalse(inline.has_change_permission(request, doc))
        self.assertFalse(inline.has_delete_permission(request, doc))
        self.assertTrue(verificar_integridade(doc).integra)

    def test_imagem_retificacao_permissoes_e_hash(self):
        doc = self.criar()
        self.client.post(self.url_retificar(doc), self.payload())
        ret = doc.retificacoes.get()
        assinatura = assinaturas_documento(ret).get()
        url = reverse('core:ver_imagem_assinatura', args=[assinatura.pk])
        for user in (self.clinico, self.admin):
            self.client.force_login(user)
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200)
            for fechar in resposta._resource_closers:
                fechar()
        for user in self.negados:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.clinico)
        self.adulterar(ret, 'conteudo', 'Retificação adulterada')
        self.assertEqual(self.client.get(url).status_code, 409)
        self.assertContains(self.client.get(url_documento(doc)), 'Integridade da retificação não confirmada')

    def test_administrador_pode_retificar_sem_mudar_permissoes(self):
        doc = self.criar()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url_retificar(doc), self.payload()).status_code, 302)
        self.assertEqual(doc.retificacoes.get().autor, self.admin)

    def test_exclusao_de_profissional_apenas_no_m2m_e_bloqueada(self):
        profissional = Dentista.objects.create(nome_completo='Somente no item', sala=Sala.objects.create(nome='Outra sala'))
        doc = self.criar('plano_tratamento', profissional_m2m=profissional)
        with self.assertRaises(ValidationError), transaction.atomic():
            profissional.delete()
        self.assertTrue(verificar_integridade(doc).integra)
