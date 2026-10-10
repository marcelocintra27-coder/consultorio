"""Equipe: novo funcionário numa tela só, senha provisória e desligar acesso."""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

SENHA = 'Clinica#2026x'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EquipeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_equipe', password='x')
        self.titular = Dentista.objects.create(
            nome_completo='Dra. Titular Equipe', sala=Sala.objects.create(nome='Sala Eq'),
        )
        self.locataria = Dentista.objects.create(
            nome_completo='Dra. Locataria Equipe', tipo=Dentista.Tipo.LOCATARIA,
        )
        self.client.force_login(self.admin)
        self.novo = reverse('core:novo_funcionario')

    def dados(self, **extra):
        dados = {
            'nome': 'Renata Souza', 'funcao': 'secretaria', 'dentista': '',
            'usuario': 'renata', 'senha': SENHA, 'confirmar_senha': SENHA,
        }
        dados.update(extra)
        return dados

    def test_cria_usuario_e_perfil_de_uma_vez_com_troca_obrigatoria(self):
        resposta = self.client.post(self.novo, self.dados())
        self.assertRedirects(resposta, reverse('core:equipe'))
        usuario = User.objects.get(username='renata')
        self.assertEqual(usuario.first_name, 'Renata')
        self.assertEqual(usuario.last_name, 'Souza')
        self.assertTrue(usuario.check_password(SENHA))
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(usuario.perfil.papel, 'secretaria')
        self.assertIsNone(usuario.perfil.dentista)
        self.assertTrue(usuario.perfil.deve_trocar_senha)

    def test_secretaria_ignora_dentista_escolhida(self):
        self.client.post(self.novo, self.dados(dentista=self.titular.pk))
        self.assertIsNone(User.objects.get(username='renata').perfil.dentista)

    def test_auxiliar_precisa_de_dentista(self):
        resposta = self.client.post(self.novo, self.dados(funcao='auxiliar'))
        self.assertContains(resposta, 'Escolha a dentista com quem a auxiliar trabalha.')
        self.assertContains(resposta, 'O acesso ainda não foi criado.')
        self.assertFalse(User.objects.filter(username='renata').exists())
        self.client.post(self.novo, self.dados(funcao='auxiliar', dentista=self.titular.pk))
        self.assertEqual(User.objects.get(username='renata').perfil.dentista, self.titular)

    def test_nome_de_acesso_repetido_ou_com_espaco_e_recusado(self):
        User.objects.create_user('Renata')
        resposta = self.client.post(self.novo, self.dados())
        self.assertContains(resposta, 'Esse nome já é usado')
        resposta = self.client.post(self.novo, self.dados(usuario='renata silva'))
        self.assertContains(resposta, 'Não use espaço')

    def test_senha_fraca_ou_diferente_e_recusada_em_portugues(self):
        resposta = self.client.post(self.novo, self.dados(senha='123', confirmar_senha='123'))
        self.assertContains(resposta, 'curta demais')
        resposta = self.client.post(self.novo, self.dados(confirmar_senha='OutraSenha#99'))
        self.assertContains(resposta, 'As duas senhas não são iguais')
        self.assertFalse(User.objects.filter(username='renata').exists())

    def test_criar_acesso_da_dentista_vem_preenchido(self):
        resposta = self.client.get(self.novo, {'funcao': 'dentista', 'dentista': self.locataria.pk})
        self.assertContains(resposta, 'value="Dra. Locataria Equipe"')
        self.assertContains(resposta, f'<option value="{self.locataria.pk}" selected>')

    def test_lista_da_equipe_mostra_dentistas_e_acessos(self):
        self.client.post(self.novo, self.dados())
        sem_funcao = User.objects.create_user('sem_funcao')
        resposta = self.client.get(reverse('core:equipe'))
        self.assertContains(resposta, 'Dra. Titular Equipe')
        self.assertContains(resposta, 'Locatária')
        self.assertContains(resposta, 'Renata Souza')
        self.assertContains(resposta, 'Ainda não criou a senha própria')
        self.assertContains(resposta, 'Sem função')
        self.assertContains(resposta, reverse('core:editar_funcionario', args=[sem_funcao.pk]))
        self.assertNotContains(resposta, reverse('core:editar_funcionario', args=[self.admin.pk]))

    def test_editar_funcao_senha_provisoria_e_desligar(self):
        self.client.post(self.novo, self.dados())
        usuario = User.objects.get(username='renata')
        PerfilUsuario.objects.filter(usuario=usuario).update(deve_trocar_senha=False)
        url = reverse('core:editar_funcionario', args=[usuario.pk])

        self.client.post(url, {
            'acao': 'dados', 'nome': 'Renata S.', 'funcao': 'auxiliar', 'dentista': self.titular.pk,
        })
        usuario.refresh_from_db()
        self.assertEqual(usuario.perfil.papel, 'auxiliar')
        self.assertEqual(usuario.perfil.dentista, self.titular)

        nova = 'NovaSenha#2026'
        self.client.post(url, {'acao': 'senha', 'senha': nova, 'confirmar_senha': nova})
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(nova))
        self.assertTrue(usuario.perfil.deve_trocar_senha)

        self.client.post(url, {'acao': 'desligar'})
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.client.post(url, {'acao': 'religar'})
        usuario.refresh_from_db()
        self.assertTrue(usuario.is_active)

    def test_usuario_sem_perfil_ganha_perfil_ao_salvar(self):
        sem = User.objects.create_user('sem_perfil')
        self.client.post(reverse('core:editar_funcionario', args=[sem.pk]), {
            'acao': 'dados', 'nome': 'Fulana', 'funcao': 'secretaria',
        })
        self.assertEqual(PerfilUsuario.objects.get(usuario=sem).papel, 'secretaria')

    def test_nao_mexe_em_administrador_nem_na_propria_conta(self):
        outro_admin = User.objects.create_superuser('outro_admin', password='x')
        for pk in (outro_admin.pk, self.admin.pk):
            url = reverse('core:editar_funcionario', args=[pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {'acao': 'desligar'}).status_code, 403)

    def test_so_administrador_acessa(self):
        secretaria = User.objects.create_user('sec_eq')
        PerfilUsuario.objects.create(usuario=secretaria, papel='secretaria')
        self.client.force_login(secretaria)
        for url in (reverse('core:equipe'), self.novo,
                    reverse('core:editar_funcionario', args=[secretaria.pk])):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.novo, self.dados()).status_code, 403)
        self.assertFalse(User.objects.filter(username='renata').exists())

    def test_menu_e_administracao_levam_para_equipe(self):
        resposta = self.client.get(reverse('core:administracao'))
        self.assertContains(resposta, reverse('core:equipe'))
        self.assertContains(resposta, 'Abrir equipe')
