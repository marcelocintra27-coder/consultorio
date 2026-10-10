"""Entrar sem exigir acento ou maiúscula iguais no nome de acesso."""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import PerfilUsuario

SENHA = 'Clinica#2026x'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginFlexivelTests(TestCase):
    def setUp(self):
        self.usuaria = User.objects.create_user('recepcao', password=SENHA)
        PerfilUsuario.objects.create(usuario=self.usuaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.entrar = reverse('entrar')

    def tentar(self, nome, senha=SENHA):
        self.client.logout()
        self.client.post(self.entrar, {'username': nome, 'password': senha})
        return '_auth_user_id' in self.client.session

    def test_aceita_acento_maiuscula_e_espaco_nas_pontas(self):
        for nome in ('recepcao', 'Recepcao', 'recepção', 'RECEPÇÃO', '  recepcao  '):
            with self.subTest(nome=nome):
                self.assertTrue(self.tentar(nome))

    def test_senha_continua_exata(self):
        self.assertFalse(self.tentar('recepcao', 'clinica#2026x'))
        self.assertFalse(self.tentar('Recepção', 'outra'))

    def test_nome_que_serve_para_duas_contas_nao_entra(self):
        User.objects.create_user('Recepcao', password=SENHA)
        self.assertTrue(self.tentar('recepcao'))   # exato continua valendo
        self.assertTrue(self.tentar('Recepcao'))
        self.assertFalse(self.tentar('recepção'))  # ambíguo: não adivinha

    def test_conta_desligada_nao_entra(self):
        self.usuaria.is_active = False
        self.usuaria.save()
        self.assertFalse(self.tentar('Recepção'))

    def test_novo_funcionario_guarda_nome_sem_acento_e_minusculo(self):
        admin = User.objects.create_superuser('admin_lf', password='x')
        self.client.force_login(admin)
        self.client.post(reverse('core:novo_funcionario'), {
            'nome': 'Teste Recepção', 'funcao': 'secretaria', 'usuario': 'Recepção.Dois',
            'senha': SENHA, 'confirmar_senha': SENHA,
        })
        self.assertTrue(User.objects.filter(username='recepcao.dois').exists())
        resposta = self.client.post(reverse('core:novo_funcionario'), {
            'nome': 'Outra', 'funcao': 'secretaria', 'usuario': 'RECEPCAO',
            'senha': SENHA, 'confirmar_senha': SENHA,
        })
        self.assertContains(resposta, 'Esse nome já é usado')

    def test_tela_de_troca_obrigatoria_explica_o_passo(self):
        self.usuaria.perfil.deve_trocar_senha = True
        self.usuaria.perfil.save()
        self.client.post(self.entrar, {'username': 'Recepção', 'password': SENHA})
        resposta = self.client.get(reverse('core:trocar_senha'))
        self.assertContains(resposta, 'Você entrou.')
        self.assertContains(resposta, 'digite a senha provisória')
