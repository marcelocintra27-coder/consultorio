"""Anamnese de harmonização orofacial (HOF): mesma ficha, outro tipo e outras perguntas."""
import json
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from locacao.models import Dentista, PerfilUsuario, Sala

from .anamnese import texto_para_hash
from .integridade_documentos import verificar_integridade
from .models import AssinaturaEletronica, Consulta, FichaCadastroAnamnese, Paciente
from .tests import PNG_1PX, _payload_anamnese


def _payload_hof(**extra):
    dados = {
        'nome_completo': 'Paciente HOF',
        'data_nascimento': '1990-01-01',
        'cpf': '333.333.333-33',
        'telefone': '11933334444',
        'whatsapp': '',
        'email': '',
        'endereco': 'Rua A, 1',
        'cidade': 'Goiânia',
        'uf': 'GO',
        'profissao': 'Professora',
        'nome_responsavel': '',
        'saude_condicoes': ['herpes'],
        'usa_medicamento': 'nao',
        'medicamento_nome': '',
        'alergia': 'nao',
        'alergia_qual': '',
        'hof_situacoes': ['nenhuma'],
        'hof_situacoes_detalhes': '',
        'isotretinoina': 'sim',
        'isotretinoina_quando': 'parei em março de 2026',
        'fuma': 'nao',
        'hof_procedimentos': ['toxina'],
        'hof_ultimo_procedimento': 'toxina na testa, 01/2026',
        'hof_intercorrencias': '',
        'o_que_incomoda': 'rugas na testa',
        'o_que_espera': 'aspecto natural',
        'aceitou_declaracao': 'on',
        'assinatura_paciente_base64': PNG_1PX,
        'acao': 'enviar',
    }
    dados.update(extra)
    return dados


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AnamneseHOFTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_hof', password='x')
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente HOF',
            cpf='333.333.333-33',
            data_nascimento=date(1990, 1, 1),
            telefone='11933334444',
        )
        self.lista = f'/pacientes/{self.paciente.pk}/anamnese/'
        self.nova = f'/pacientes/{self.paciente.pk}/anamnese/nova/'

    def _abrir(self, tipo):
        self.client.force_login(self.admin)
        resposta = self.client.post(self.nova, {'tipo': tipo})
        self.assertEqual(resposta.status_code, 302)
        return FichaCadastroAnamnese.objects.filter(
            paciente=self.paciente, tipo=tipo
        ).latest('pk')

    def test_lista_oferece_os_dois_tipos(self):
        self.client.force_login(self.admin)
        html = self.client.get(self.lista).content.decode()
        self.assertIn('Nova anamnese odontológica', html)
        self.assertIn('Nova anamnese HOF (rosto)', html)

    def test_hof_e_odontologica_ficam_abertas_ao_mesmo_tempo(self):
        odonto = self._abrir('odontologica')
        hof = self._abrir('hof')
        self.assertNotEqual(odonto.pk, hof.pk)
        self.assertEqual(hof.tipo, 'hof')
        # Pedir outra HOF reaproveita a que está aberta.
        self.assertEqual(self._abrir('hof').pk, hof.pk)
        html = self.client.get(self.lista).content.decode()
        self.assertNotIn('Nova anamnese HOF (rosto)', html)
        self.assertNotIn('Nova anamnese odontológica', html)
        self.assertIn(f'/f/a/{hof.token}/', html)
        self.assertIn(f'/f/a/{odonto.token}/', html)

    def test_sem_tipo_continua_abrindo_odontologica(self):
        self.client.force_login(self.admin)
        self.client.post(self.nova)
        ficha = FichaCadastroAnamnese.objects.get(paciente=self.paciente)
        self.assertEqual(ficha.tipo, 'odontologica')

    def test_tipo_invalido_e_recusado(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(self.nova, {'tipo': 'qualquer'})
        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(FichaCadastroAnamnese.objects.exists())

    def test_link_publico_mostra_perguntas_hof(self):
        ficha = self._abrir('hof')
        self.client.logout()
        html = self.client.get(f'/f/a/{ficha.token}/').content.decode()
        self.assertIn('Roacutan', html)
        self.assertIn('toxina botulínica', html)
        self.assertIn('paralisia facial prévia', html)
        self.assertNotIn('sua saúde bucal', html)

    def test_paciente_envia_hof_e_dentista_conclui_com_integridade(self):
        ficha = self._abrir('hof')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_hof())
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA)
        self.assertEqual(ficha.isotretinoina, 'sim')
        self.assertEqual(ficha.hof_procedimentos, ['toxina'])
        conteudo = json.loads(texto_para_hash(ficha))
        self.assertEqual(conteudo['tipo'], 'hof')
        self.assertEqual(conteudo['isotretinoina_quando'], 'parei em março de 2026')

        self.client.force_login(self.admin)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/',
            {'assinatura_dentista_base64': PNG_1PX},
        )
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.CONCLUIDA)
        self.assertEqual(
            AssinaturaEletronica.objects.filter(
                tipo_documento='anamnese', documento_id=ficha.pk
            ).count(),
            2,
        )
        self.assertTrue(verificar_integridade(ficha).integra)

        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/'
        ).content.decode()
        self.assertIn('Anamnese de harmonização orofacial (HOF)', html)
        self.assertIn('herpes recorrente', html)
        self.assertIn('parei em março de 2026', html)
        self.assertIn('toxina botulínica', html)

    def test_hof_exige_respostas_principais(self):
        ficha = self._abrir('hof')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_hof(
            isotretinoina='',
            hof_situacoes=[],
        ))
        self.assertEqual(resposta.status_code, 200)
        erros = resposta.context['form'].errors
        self.assertIn('isotretinoina', erros)
        self.assertIn('hof_situacoes', erros)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.RASCUNHO)

    def test_hof_exige_detalhes_quando_responde_sim(self):
        ficha = self._abrir('hof')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_hof(
            isotretinoina_quando='',
            hof_ultimo_procedimento='',
        ))
        erros = resposta.context['form'].errors
        self.assertIn('isotretinoina_quando', erros)
        self.assertIn('hof_ultimo_procedimento', erros)

    def test_nenhum_procedimento_dispensa_ultimo_procedimento(self):
        ficha = self._abrir('hof')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_hof(
            hof_procedimentos=['nenhuma'],
            hof_ultimo_procedimento='',
        ))
        self.assertEqual(resposta.status_code, 302)

    def test_opcao_da_ficha_odontologica_nao_vale_na_hof(self):
        ficha = self._abrir('hof')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_hof(
            saude_condicoes=['osteoporose'],
            hof_procedimentos=['nenhuma', 'toxina'],
        ))
        erros = resposta.context['form'].errors
        self.assertIn('saude_condicoes', erros)
        self.assertIn('hof_procedimentos', erros)

    def test_ficha_odontologica_assina_com_o_mesmo_conteudo_de_antes(self):
        ficha = self._abrir('odontologica')
        self.client.logout()
        resposta = self.client.post(f'/f/a/{ficha.token}/', _payload_anamnese(
            nome_completo='Paciente HOF', cpf='333.333.333-33',
            telefone='11933334444',
        ))
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        conteudo = json.loads(texto_para_hash(ficha))
        # Nenhuma chave nova entra na ficha odontológica: as assinaturas antigas
        # continuam conferindo depois desta mudança.
        self.assertNotIn('tipo', conteudo)
        self.assertFalse([chave for chave in conteudo if 'hof' in chave or 'isotretinoina' in chave])
        self.assertTrue(verificar_integridade(ficha, exigir_completude=False).integra)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AnamneseHOFPermissaoTests(TestCase):
    def test_secretaria_nao_abre_hof_e_dentista_do_paciente_abre(self):
        sala = Sala.objects.create(nome='Sala HOF')
        dentista = Dentista.objects.create(nome_completo='Dra. HOF', sala=sala)
        paciente = Paciente.objects.create(
            nome_completo='Paciente Permissão HOF', cpf=None,
            data_nascimento=date(1985, 5, 5), telefone='11955556666',
        )
        Consulta.objects.create(
            paciente=paciente, dentista=dentista, data=date(2026, 10, 9),
            hora_inicio=time(9), hora_fim=time(10),
        )
        secretaria = User.objects.create_user('sec_hof', password='x')
        PerfilUsuario.objects.create(usuario=secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        usuario_dentista = User.objects.create_user('dent_hof', password='x')
        PerfilUsuario.objects.create(
            usuario=usuario_dentista, papel=PerfilUsuario.Papel.DENTISTA, dentista=dentista,
        )
        url = f'/pacientes/{paciente.pk}/anamnese/nova/'

        self.client.force_login(secretaria)
        self.assertEqual(self.client.post(url, {'tipo': 'hof'}).status_code, 403)
        self.assertFalse(FichaCadastroAnamnese.objects.exists())

        self.client.force_login(usuario_dentista)
        self.assertEqual(self.client.post(url, {'tipo': 'hof'}).status_code, 302)
        self.assertEqual(FichaCadastroAnamnese.objects.get(paciente=paciente).tipo, 'hof')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AnamneseAproveitaFichaAnteriorTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin_pre', password='x'))
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente HOF', cpf='333.333.333-33',
            data_nascimento=date(1990, 1, 1), telefone='11933334444',
        )
        self.nova = f'/pacientes/{self.paciente.pk}/anamnese/nova/'

    def _enviar(self, tipo, payload):
        self.client.post(self.nova, {'tipo': tipo})
        ficha = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo=tipo)
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{ficha.pk}/editar/', payload,
        )
        self.assertEqual(resposta.status_code, 302)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.AGUARDANDO_DENTISTA)
        return ficha

    def test_hof_nova_traz_respostas_da_odontologica(self):
        self._enviar('odontologica', _payload_anamnese(
            nome_completo='Paciente HOF', cpf='333.333.333-33', telefone='11933334444',
            cidade='Anápolis', profissao='Bancária',
            saude_condicoes=['pressao_alta', 'osteoporose'],
            alergia='sim', alergia_qual='dipirona',
            usa_medicamento='sim', medicamento_nome='losartana',
            fuma='sim',
        ))
        self.client.post(self.nova, {'tipo': 'hof'})
        hof = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='hof')
        self.assertEqual(hof.cidade, 'Anápolis')
        self.assertEqual(hof.profissao, 'Bancária')
        self.assertEqual(hof.alergia_qual, 'dipirona')
        self.assertEqual(hof.medicamento_nome, 'losartana')
        self.assertEqual(hof.fuma, 'sim')
        # Pressão alta vira hipertensão; osteoporose não existe na ficha HOF.
        self.assertEqual(hof.saude_condicoes, ['hipertensao'])
        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/anamnese/{hof.pk}/editar/'
        ).content.decode()
        self.assertIn('dipirona', html)

    def test_odontologica_nova_traz_respostas_da_hof(self):
        self._enviar('hof', _payload_hof(
            saude_condicoes=['hipertensao', 'herpes'],
            usa_medicamento='sim', medicamento_nome='enalapril',
        ))
        self.client.post(self.nova, {'tipo': 'odontologica'})
        odonto = FichaCadastroAnamnese.objects.get(
            paciente=self.paciente, tipo='odontologica'
        )
        self.assertEqual(odonto.saude_condicoes, ['pressao_alta'])
        self.assertEqual(odonto.medicamento_nome, 'enalapril')

    def test_ficha_assinada_tem_preferencia_sobre_rascunho(self):
        self._enviar('hof', _payload_hof(alergia='sim', alergia_qual='assinada'))
        self.client.post(self.nova, {'tipo': 'odontologica'})
        odonto = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='odontologica')
        self.assertEqual(odonto.alergia_qual, 'assinada')

    def test_hof_aberta_antes_mostra_o_que_foi_digitado_na_odontologica(self):
        # Caso real: a HOF já estava aberta quando a equipe preencheu a
        # odontológica (ainda sem assinatura). Ao abrir a HOF, os dados aparecem.
        self.client.post(self.nova, {'tipo': 'hof'})
        hof = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='hof')
        self.client.post(self.nova, {'tipo': 'odontologica'})
        odonto = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='odontologica')
        resposta = self.client.post(
            f'/pacientes/{self.paciente.pk}/anamnese/{odonto.pk}/editar/',
            _payload_anamnese(
                nome_completo='Paciente HOF', cpf='333.333.333-33', telefone='11933334444',
                acao='rascunho', assinatura_paciente_base64='',
                profissao='Arquiteta', alergia='sim', alergia_qual='penicilina',
                saude_condicoes=['diabetes'],
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        tela = self.client.get(f'/pacientes/{self.paciente.pk}/anamnese/{hof.pk}/editar/')
        form = tela.context['form']
        self.assertEqual(form.initial['profissao'], 'Arquiteta')
        self.assertEqual(form.initial['alergia_qual'], 'penicilina')
        self.assertEqual(form.initial['saude_condicoes'], ['diabetes'])
        # Só mostra; a HOF continua sem esses dados até alguém salvar.
        hof.refresh_from_db()
        self.assertEqual(hof.alergia_qual, '')

    def test_nao_apaga_o_que_ja_foi_digitado(self):
        self._enviar('odontologica', _payload_anamnese(
            nome_completo='Paciente HOF', cpf='333.333.333-33', telefone='11933334444',
            profissao='Bancária',
        ))
        self.client.post(self.nova, {'tipo': 'hof'})
        hof = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='hof')
        FichaCadastroAnamnese.objects.filter(pk=hof.pk).update(profissao='Professora')
        tela = self.client.get(f'/pacientes/{self.paciente.pk}/anamnese/{hof.pk}/editar/')
        self.assertEqual(tela.context['form'].initial['profissao'], 'Professora')

    def test_bruxismo_e_gravidez_da_odontologica_vao_para_a_hof(self):
        self._enviar('odontologica', _payload_anamnese(
            nome_completo='Paciente HOF', cpf='333.333.333-33', telefone='11933334444',
            range_dentes='sim', gravidez='sim',
        ))
        self.client.post(self.nova, {'tipo': 'hof'})
        hof = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='hof')
        self.assertEqual(sorted(hof.hof_situacoes), ['bruxismo', 'gestante_lactante'])

    def test_bruxismo_da_hof_vai_para_a_odontologica_mas_lactante_nao(self):
        self._enviar('hof', _payload_hof(hof_situacoes=['bruxismo', 'gestante_lactante']))
        self.client.post(self.nova, {'tipo': 'odontologica'})
        odonto = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='odontologica')
        self.assertEqual(odonto.range_dentes, 'sim')
        self.assertEqual(odonto.gravidez, '')

    def test_tela_de_preenchimento_tem_um_quadro_e_dois_botoes(self):
        self.client.post(self.nova, {'tipo': 'hof'})
        hof = FichaCadastroAnamnese.objects.get(paciente=self.paciente, tipo='hof')
        html = self.client.get(
            f'/pacientes/{self.paciente.pk}/anamnese/{hof.pk}/editar/'
        ).content.decode()
        self.assertIn('Salvar e terminar depois', html)
        self.assertIn('Salvar e assinar', html)
        self.assertNotIn('assinatura_dentista_base64-canvas', html)
        self.assertNotIn('Concluir com as duas assinaturas', html)

    def test_tela_separa_os_tipos_e_mostra_a_situacao(self):
        self._enviar('hof', _payload_hof())
        self.client.post(self.nova, {'tipo': 'odontologica'})
        html = self.client.get(f'/pacientes/{self.paciente.pk}/anamnese/').content.decode()
        self.assertIn('anamnese-tipo-odontologica', html)
        self.assertIn('anamnese-tipo-hof', html)
        self.assertIn('Em preenchimento', html)
        self.assertIn('Falta a assinatura do dentista', html)
        self.assertIn('Ver e concluir', html)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AvisoDoQueFaltaTests(TestCase):
    def test_topo_avisa_que_nao_salvou_e_o_que_falta(self):
        self.client.force_login(User.objects.create_superuser('admin_aviso', password='x'))
        paciente = Paciente.objects.create(
            nome_completo='Paciente HOF', cpf='333.333.333-33',
            data_nascimento=date(1990, 1, 1), telefone='11933334444',
        )
        self.client.post(f'/pacientes/{paciente.pk}/anamnese/nova/', {'tipo': 'hof'})
        ficha = FichaCadastroAnamnese.objects.get(paciente=paciente)
        resposta = self.client.post(
            f'/pacientes/{paciente.pk}/anamnese/{ficha.pk}/editar/',
            _payload_hof(isotretinoina='', assinatura_paciente_base64=''),
        )
        html = resposta.content.decode()
        self.assertIn('A ficha ainda não foi salva.', html)
        self.assertIn('href="#id_isotretinoina"', html)
        self.assertIn('Assinatura do paciente', html)
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, FichaCadastroAnamnese.Status.RASCUNHO)
