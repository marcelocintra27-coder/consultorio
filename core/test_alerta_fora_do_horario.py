"""Alerta de entrada da funcionária fora do horário da clínica."""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import RegistroAcesso

SP = ZoneInfo('America/Sao_Paulo')


def _quando(ano, mes, dia, hora, minuto):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=SP)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AlertaForaDoHorarioTests(TestCase):
    def setUp(self):
        self.sala_adriana = Sala.objects.create(nome='Sala Adriana')
        self.sala_simone = Sala.objects.create(nome='Sala Simone')
        self.adriana = Dentista.objects.create(
            nome_completo='Dra. Adriana', sala=self.sala_adriana,
        )
        self.simone = Dentista.objects.create(
            nome_completo='Dra. Simone', sala=self.sala_simone,
        )
        self.dra_adriana = self._usuario(
            'adriana', 'Adriana', 'Costa', PerfilUsuario.Papel.DENTISTA, self.adriana,
        )
        self.dra_simone = self._usuario(
            'simone', 'Simone', 'Lima', PerfilUsuario.Papel.DENTISTA, self.simone,
        )
        self.emilly = self._usuario(
            'emilly', 'Emilly', 'Souza', PerfilUsuario.Papel.AUXILIAR, self.adriana,
        )
        self.bruna = self._usuario(
            'bruna', 'Bruna', 'Alves', PerfilUsuario.Papel.AUXILIAR, self.simone,
        )
        self.amanda = self._usuario(
            'amanda', 'Amanda', 'Nunes', PerfilUsuario.Papel.SECRETARIA, None,
        )
        self.admin = User.objects.create_superuser('admin_horario', password='x')
        self.admin.first_name = 'Admin'
        self.admin.last_name = 'Geral'
        self.admin.save(update_fields=['first_name', 'last_name'])
        self.lista = reverse('core:listar_entradas_fora_do_horario')
        self.agora = _quando(2026, 10, 7, 12, 0)

    def _usuario(self, username, nome, sobrenome, papel, dentista):
        usuario = User.objects.create_user(
            username, password='x', first_name=nome, last_name=sobrenome,
        )
        PerfilUsuario.objects.create(usuario=usuario, papel=papel, dentista=dentista)
        return usuario

    def _login(self, usuario, momento):
        self.client.logout()
        with patch('django.utils.timezone.now', return_value=momento):
            resposta = self.client.post(reverse('entrar'), {
                'username': usuario.username,
                'password': 'x',
            })
        self.assertEqual(resposta.status_code, 302, momento)
        return RegistroAcesso.objects.filter(
            usuario=usuario,
            tipo=RegistroAcesso.Tipo.ENTROU,
        ).order_by('-pk').first()

    def _gravar(self, usuario, momento):
        registro = RegistroAcesso.objects.create(
            usuario=usuario,
            tipo=RegistroAcesso.Tipo.ENTROU,
            fora_do_horario=True,
        )
        RegistroAcesso.objects.filter(pk=registro.pk).update(criado_em=momento)
        return registro

    def test_dentro_do_horario_nao_alerta_e_nao_bloqueia(self):
        for momento in (
            _quando(2026, 10, 5, 10, 0),
            _quando(2026, 10, 5, 7, 30),
            _quando(2026, 10, 5, 18, 0),
        ):
            entrada = self._login(self.amanda, momento)
            self.assertFalse(entrada.fora_do_horario, momento)
        self.assertEqual(self.client.get(reverse('core:inicio')).status_code, 200)

    def test_limites_e_fim_de_semana_alertam_sem_bloquear(self):
        casos = (
            (self.amanda, _quando(2026, 10, 5, 7, 29)),
            (self.amanda, _quando(2026, 10, 5, 18, 1)),
            (self.emilly, _quando(2026, 10, 10, 10, 0)),
            (self.bruna, _quando(2026, 10, 11, 15, 0)),
        )
        for usuario, momento in casos:
            entrada = self._login(usuario, momento)
            self.assertTrue(entrada.fora_do_horario, momento)
            self.assertEqual(self.client.get(reverse('core:inicio')).status_code, 200)
            self.assertEqual(self.client.get(self.lista).status_code, 403)

    def test_dentista_e_admin_nunca_alertam(self):
        sabado = _quando(2026, 10, 10, 22, 0)
        for usuario in (self.dra_adriana, self.admin):
            entrada = self._login(usuario, sabado)
            self.assertFalse(entrada.fora_do_horario)
        super_secretaria = User.objects.create_superuser('super_sec', password='x')
        PerfilUsuario.objects.create(
            usuario=super_secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        entrada = self._login(super_secretaria, sabado)
        self.assertFalse(entrada.fora_do_horario)

    def test_dentista_ve_so_as_proprias_e_admin_ve_todas(self):
        self._gravar(self.emilly, self.agora - timedelta(days=1))
        self._gravar(self.bruna, self.agora - timedelta(days=2))
        self._gravar(self.amanda, self.agora - timedelta(hours=3))
        self._gravar(self.emilly, self.agora - timedelta(days=8))
        RegistroAcesso.objects.create(
            usuario=self.amanda,
            tipo=RegistroAcesso.Tipo.ENTROU,
            fora_do_horario=False,
        )

        self.client.force_login(self.dra_adriana)
        with patch('django.utils.timezone.now', return_value=self.agora):
            lista = self.client.get(self.lista)
            inicio = self.client.get(reverse('core:inicio'))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Emilly Souza')
        self.assertContains(lista, 'terça-feira')
        self.assertContains(lista, '06/10/2026')
        self.assertContains(lista, '12:00')
        self.assertContains(lista, '29/09/2026')
        self.assertNotContains(lista, 'Bruna Alves')
        self.assertNotContains(lista, 'Amanda Nunes')
        html = lista.content.decode()
        self.assertLess(html.find('06/10/2026'), html.find('29/09/2026'))
        self.assertContains(inicio, '1 entrada fora do horário nos últimos 7 dias')
        self.assertContains(inicio, self.lista)

        self.client.force_login(self.dra_simone)
        with patch('django.utils.timezone.now', return_value=self.agora):
            lista = self.client.get(self.lista)
            inicio = self.client.get(reverse('core:inicio'))
        self.assertContains(lista, 'Bruna Alves')
        self.assertNotContains(lista, 'Emilly Souza')
        self.assertNotContains(lista, 'Amanda Nunes')
        self.assertContains(inicio, '1 entrada fora do horário nos últimos 7 dias')

        self.client.force_login(self.admin)
        with patch('django.utils.timezone.now', return_value=self.agora):
            lista = self.client.get(self.lista)
            inicio = self.client.get(reverse('core:inicio'))
        self.assertContains(lista, 'Emilly Souza')
        self.assertContains(lista, 'Bruna Alves')
        self.assertContains(lista, 'Amanda Nunes')
        self.assertContains(inicio, '3 entradas fora do horário nos últimos 7 dias')
        admin_html = lista.content.decode()
        self.assertLess(admin_html.find('07/10/2026'), admin_html.find('06/10/2026'))
        self.assertLess(admin_html.find('06/10/2026'), admin_html.find('05/10/2026'))
        self.assertLess(admin_html.find('05/10/2026'), admin_html.find('29/09/2026'))

    def test_funcionaria_nao_ve_lista_nem_aviso(self):
        self._gravar(self.emilly, self.agora - timedelta(hours=1))
        self._gravar(self.amanda, self.agora - timedelta(hours=2))
        for usuario in (self.amanda, self.emilly):
            self.client.force_login(usuario)
            with patch('django.utils.timezone.now', return_value=self.agora):
                inicio = self.client.get(reverse('core:inicio'))
            self.assertEqual(self.client.get(self.lista).status_code, 403)
            self.assertNotContains(inicio, 'fora do horário')
            self.assertNotContains(inicio, self.lista)
