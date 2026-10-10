"""Troca da própria senha e obrigação no primeiro acesso."""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import RegistroAcesso

SP = ZoneInfo('America/Sao_Paulo')
SENHA_ATUAL = 'SenhaAtual#1'
SENHA_NOVA = 'NovaSenha#2026'
SENHA_ADMIN = 'AdminAtual#1'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TrocarSenhaTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Senha')
        self.dentista_modelo = Dentista.objects.create(
            nome_completo='Dra. Helena', sala=self.sala,
        )
        self.usuaria, self.perfil = self._secretaria('amanda')
        self.admin = User.objects.create_superuser('admin_senha', password=SENHA_ADMIN)
        self.troca = reverse('core:trocar_senha')
        self.inicio = reverse('core:inicio')
        self.pacientes = reverse('core:listar_pacientes')
        self.agenda = reverse('core:listar_consultas')

    def _secretaria(self, username, senha=SENHA_ATUAL):
        usuario = User.objects.create_user(
            username,
            password=senha,
            first_name=username.capitalize(),
            last_name='Nunes',
        )
        perfil = PerfilUsuario.objects.create(
            usuario=usuario, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        return usuario, perfil

    def _dados(self, atual=SENHA_ATUAL, nova=SENHA_NOVA, repetir=None):
        return {
            'old_password': atual,
            'new_password1': nova,
            'new_password2': nova if repetir is None else repetir,
        }

    def test_troca_com_sucesso_mantem_login_e_avisa_na_inicio(self):
        self.client.force_login(self.usuaria)
        resposta = self.client.post(self.troca, self._dados(), follow=True)
        self.assertContains(resposta, 'Senha alterada com sucesso.')
        self.assertEqual(resposta.wsgi_request.path, self.inicio)
        self.assertTrue(resposta.wsgi_request.user.is_authenticated)
        self.assertEqual(resposta.wsgi_request.user.pk, self.usuaria.pk)
        self.usuaria.refresh_from_db()
        self.assertTrue(self.usuaria.check_password(SENHA_NOVA))
        self.assertFalse(self.usuaria.check_password(SENHA_ATUAL))
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.deve_trocar_senha)
        self.assertEqual(self.client.get(self.pacientes).status_code, 200)

    def test_senha_atual_errada_recusa(self):
        self.client.force_login(self.usuaria)
        resposta = self.client.post(self.troca, self._dados(atual='Errada#1234'))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'A senha atual está incorreta.')
        self.usuaria.refresh_from_db()
        self.assertTrue(self.usuaria.check_password(SENHA_ATUAL))
        self.assertTrue(self.client.get(self.inicio).wsgi_request.user.is_authenticated)

    def test_senhas_novas_diferentes_recusam(self):
        self.client.force_login(self.usuaria)
        resposta = self.client.post(
            self.troca, self._dados(repetir='OutraSenha#2026'),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'As senhas novas não são iguais.')
        self.usuaria.refresh_from_db()
        self.assertTrue(self.usuaria.check_password(SENHA_ATUAL))

    def test_validacao_do_django_em_portugues(self):
        self.client.force_login(self.usuaria)
        casos = (
            ('abc12', 'A senha nova é curta demais.'),
            ('12345678', 'A senha nova não pode ter só números.'),
            ('password', 'Essa senha é muito comum.'),
            ('amanda123', 'A senha nova é parecida demais com os seus dados.'),
        )
        for senha, aviso in casos:
            resposta = self.client.post(self.troca, self._dados(nova=senha))
            self.assertContains(resposta, aviso, msg_prefix=senha)
        self.usuaria.refresh_from_db()
        self.assertTrue(self.usuaria.check_password(SENHA_ATUAL))

    def test_link_no_menu_perto_de_sair(self):
        self.client.force_login(self.usuaria)
        resposta = self.client.get(self.inicio)
        html = resposta.content.decode()
        self.assertContains(resposta, 'Trocar minha senha')
        self.assertIn(self.troca, html)
        self.assertLess(html.find('Trocar minha senha'), html.find('>Sair<'))
        pagina = self.client.get(self.troca)
        self.assertContains(pagina, 'senha atual')
        self.assertContains(pagina, 'senha nova')
        self.assertContains(pagina, 'repetir senha nova')
        self.assertContains(pagina, 'Salvar nova senha')
        self.assertNotContains(pagina, 'Falta só um passo: criar a sua senha')

    def test_admin_redefine_senha_de_outro_marca_obrigacao(self):
        self.assertFalse(self.perfil.deve_trocar_senha)
        self.client.force_login(self.admin)
        url = reverse('admin:auth_user_password_change', args=[self.usuaria.pk])
        recusa = self.client.post(url, {
            'password1': SENHA_NOVA,
            'password2': 'OutraSenha#2026',
            'usable_password': 'true',
        })
        self.assertEqual(recusa.status_code, 200)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.deve_trocar_senha)

        resposta = self.client.post(url, {
            'password1': 'Temporaria#2026',
            'password2': 'Temporaria#2026',
            'usable_password': 'true',
        })
        self.assertEqual(resposta.status_code, 302)
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.deve_trocar_senha)
        self.usuaria.refresh_from_db()
        self.assertTrue(self.usuaria.check_password('Temporaria#2026'))

    def test_admin_nao_marca_a_propria_senha(self):
        perfil_admin = PerfilUsuario.objects.create(
            usuario=self.admin, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.client.force_login(self.admin)
        url = reverse('admin:auth_user_password_change', args=[self.admin.pk])
        resposta = self.client.post(url, {
            'password1': 'Temporaria#2026',
            'password2': 'Temporaria#2026',
            'usable_password': 'true',
        })
        self.assertEqual(resposta.status_code, 302)
        perfil_admin.refresh_from_db()
        self.assertFalse(perfil_admin.deve_trocar_senha)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.deve_trocar_senha)

    def test_admin_pode_marcar_a_mao(self):
        self.client.force_login(self.admin)
        url = reverse('admin:locacao_perfilusuario_change', args=[self.perfil.pk])
        pagina = self.client.get(url)
        self.assertContains(pagina, 'Obrigar a trocar a senha no próximo acesso')
        self.assertContains(pagina, 'name="deve_trocar_senha"')
        resposta = self.client.post(url, {
            'usuario': self.usuaria.pk,
            'dentista': '',
            'papel': PerfilUsuario.Papel.SECRETARIA,
            'deve_trocar_senha': 'on',
        })
        self.assertEqual(resposta.status_code, 302, resposta.content.decode())
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.deve_trocar_senha)

    def test_usuario_marcado_so_acessa_troca_e_sair(self):
        self.perfil.deve_trocar_senha = True
        self.perfil.save(update_fields=['deve_trocar_senha'])
        self.client.force_login(self.usuaria)
        for url in (self.pacientes, self.agenda, self.inicio):
            resposta = self.client.get(url, follow=True)
            self.assertEqual(
                resposta.redirect_chain,
                [(self.troca, 302)],
            )
            self.assertContains(
                resposta,
                'Falta só um passo: criar a sua senha.',
            )
        pagina = self.client.get(self.troca)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Salvar nova senha')
        saida = self.client.get(reverse('sair'))
        self.assertRedirects(saida, reverse('entrar'))
        self.assertEqual(self.client.get(reverse('entrar')).status_code, 200)

        self.client.force_login(self.usuaria)
        self.assertEqual(self.client.get(self.troca).status_code, 200)
        estatico = self.client.get('/static/core/css/app.css')
        if estatico.status_code == 302:
            self.assertNotIn('trocar-senha', estatico.url)
        entrada = self.client.get(reverse('entrar'), follow=True)
        self.assertEqual(entrada.status_code, 200)
        self.assertContains(entrada, 'Trocar minha senha')

    def test_depois_de_trocar_acessa_normalmente(self):
        self.perfil.deve_trocar_senha = True
        self.perfil.save(update_fields=['deve_trocar_senha'])
        self.client.force_login(self.usuaria)
        resposta = self.client.post(self.troca, self._dados(), follow=True)
        self.assertContains(resposta, 'Senha alterada com sucesso.')
        self.assertEqual(resposta.wsgi_request.path, self.inicio)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.deve_trocar_senha)
        self.assertEqual(self.client.get(self.pacientes).status_code, 200)
        self.assertEqual(self.client.get(self.agenda).status_code, 200)
        self.assertNotContains(
            self.client.get(self.inicio),
            'Falta só um passo: criar a sua senha.',
        )

    def test_usuario_nao_marcado_nao_e_afetado(self):
        outra, perfil = self._secretaria('bruna')
        self.assertFalse(perfil.deve_trocar_senha)
        self.client.force_login(outra)
        self.assertEqual(self.client.get(self.pacientes).status_code, 200)
        self.assertEqual(self.client.get(self.agenda).status_code, 200)
        self.assertEqual(self.client.get(self.inicio).status_code, 200)
        self.assertNotContains(
            self.client.get(self.inicio),
            'Falta só um passo: criar a sua senha.',
        )

    def test_registro_de_acesso_e_alerta_fora_do_horario_continuam(self):
        self.perfil.deve_trocar_senha = True
        self.perfil.save(update_fields=['deve_trocar_senha'])
        momento = datetime(2026, 10, 10, 10, 0, tzinfo=SP)
        with patch('django.utils.timezone.now', return_value=momento):
            resposta = self.client.post(reverse('entrar'), {
                'username': self.usuaria.username,
                'password': SENHA_ATUAL,
            })
        self.assertEqual(resposta.status_code, 302)
        entrada = RegistroAcesso.objects.get(
            usuario=self.usuaria, tipo=RegistroAcesso.Tipo.ENTROU,
        )
        self.assertTrue(entrada.fora_do_horario)
        self.assertEqual(self.client.get(self.pacientes).status_code, 302)

        self.client.post(self.troca, self._dados())
        entrada.refresh_from_db()
        self.assertTrue(entrada.fora_do_horario)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.deve_trocar_senha)

        livre, _perfil = self._secretaria('carla')
        with patch('django.utils.timezone.now', return_value=momento):
            livre_login = self.client.post(reverse('entrar'), {
                'username': livre.username,
                'password': SENHA_ATUAL,
            })
            self.assertEqual(livre_login.status_code, 302)
            inicio = self.client.get(self.inicio)
        self.assertEqual(inicio.status_code, 200)
        registro_livre = RegistroAcesso.objects.get(
            usuario=livre, tipo=RegistroAcesso.Tipo.ENTROU,
        )
        self.assertTrue(registro_livre.fora_do_horario)

        self.client.force_login(self.admin)
        with patch('django.utils.timezone.now', return_value=momento):
            painel = self.client.get(self.inicio)
            lista = self.client.get(reverse('core:listar_entradas_fora_do_horario'))
        self.assertContains(painel, '2 entradas fora do horário nos últimos 7 dias')
        self.assertContains(lista, 'Amanda Nunes')
        self.assertContains(lista, 'Carla')
