from datetime import date, time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import AssinaturaEletronica, AuditoriaConsulta, Consulta, Paciente


PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT\x08\x1dc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\xff\xf4\xad\xcf\x00\x00\x00\x00IEND\xaeB`\x82'
)


class ProntuarioEAssinaturaSegurancaTests(TestCase):
    def setUp(self):
        sala_1 = Sala.objects.create(nome='Sala Prontuário 1')
        sala_2 = Sala.objects.create(nome='Sala Prontuário 2')
        self.dentista = Dentista.objects.create(nome_completo='Dra. Vinculada', sala=sala_1)
        outro_dentista = Dentista.objects.create(nome_completo='Dr. Sem Vínculo', sala=sala_2)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente Assinatura', cpf='900.000.000-02',
            data_nascimento=date(1980, 1, 1), telefone='11900000001',
        )
        self.consulta = Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista, data=date(2026, 9, 10),
            hora_inicio=time(10), hora_fim=time(11),
        )
        self.dentista_user = User.objects.create_user('dentista_assinatura', password='x')
        PerfilUsuario.objects.create(
            usuario=self.dentista_user, dentista=self.dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.outro_dentista_user = User.objects.create_user('outro_assinatura', password='x')
        PerfilUsuario.objects.create(
            usuario=self.outro_dentista_user, dentista=outro_dentista,
            papel=PerfilUsuario.Papel.DENTISTA,
        )
        self.secretaria = User.objects.create_user('secretaria_assinatura', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.auxiliar = User.objects.create_user('auxiliar_agenda', password='x')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            dentista=self.dentista,
            papel=PerfilUsuario.Papel.AUXILIAR,
        )
        self.admin = User.objects.create_user(
            'admin_assinatura', password='x', is_staff=True, is_superuser=True
        )
        from .models import RegistroEvolucaoClinica
        from .assinatura import gravar_assinatura_manuscrita
        from .evolucao import texto_para_hash_evolucao
        import base64
        registro = RegistroEvolucaoClinica.objects.create(
            paciente=self.paciente, data=date(2026, 9, 10),
            procedimento_etapa='Avaliação', descricao_clinica='Registro para teste de acesso.',
            nome_profissional='Dentista', cro='123',
        )
        self.assinatura = gravar_assinatura_manuscrita(
            tipo_documento='evolucao', documento_id=registro.pk,
            paciente=self.paciente, papel='dentista', nome_assinante='Dentista',
            imagem_data_url='data:image/png;base64,' + base64.b64encode(PNG).decode(),
            conteudo_para_hash=texto_para_hash_evolucao(registro),
        )

    def test_a3_assinatura_so_e_disponivel_a_dentista_vinculado_ou_admin(self):
        url = f'/fichas/assinatura/{self.assinatura.pk}/imagem/'
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.outro_dentista_user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_a4_secretaria_nao_acessa_prontuario_e_dentista_sem_vinculo_tambem_nao(self):
        url = f'/pacientes/{self.paciente.pk}/evolucao/'
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.outro_dentista_user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.dentista_user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_a5_configuracao_de_producao_tem_origem_csrf_e_flags_condicionais(self):
        self.assertIn('https://consultorio-a7um.onrender.com', settings.CSRF_TRUSTED_ORIGINS)
        if settings.EM_PRODUCAO:
            self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))
            self.assertTrue(settings.SESSION_COOKIE_SECURE)
            self.assertTrue(settings.CSRF_COOKIE_SECURE)
            self.assertTrue(settings.SECURE_SSL_REDIRECT)
            self.assertGreaterEqual(settings.SECURE_HSTS_SECONDS, 31_536_000)

    def test_is_staff_sem_superusuario_nao_herda_administracao_clinica(self):
        staff_operacional = User.objects.create_user(
            'staff_operacional', password='x', is_staff=True
        )
        self.client.force_login(staff_operacional)
        resposta = self.client.get(f'/pacientes/{self.paciente.pk}/evolucao/')
        self.assertEqual(resposta.status_code, 403)
        resposta = self.client.get('/convenios/')
        self.assertEqual(resposta.status_code, 403)

    def test_status_da_consulta_exige_perfil_de_agenda_e_conclusao_clinica(self):
        url = f'/consultas/{self.consulta.pk}/status/'
        self.client.force_login(self.auxiliar)
        resposta = self.client.post(url, {'status': Consulta.Status.REALIZADA})
        self.assertEqual(resposta.status_code, 403)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.AGENDADA)

        self.client.force_login(self.secretaria)
        resposta = self.client.post(url, {'status': Consulta.Status.REALIZADA})
        self.assertEqual(resposta.status_code, 403)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.AGENDADA)

        resposta = self.client.post(url, {'status': Consulta.Status.CONFIRMADA})
        self.assertEqual(resposta.status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.CONFIRMADA)
        self.assertTrue(
            AuditoriaConsulta.objects.filter(
                consulta=self.consulta,
                usuario=self.secretaria,
                descricao__contains='confirmada',
            ).exists()
        )

        resposta = self.client.post(url, {'status': Consulta.Status.PRESENTE})
        self.assertEqual(resposta.status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.PRESENTE)

        self.client.force_login(self.dentista_user)
        resposta = self.client.post(url, {'status': Consulta.Status.REALIZADA})
        self.assertEqual(resposta.status_code, 302)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, Consulta.Status.REALIZADA)


class TelaTecnicaAssinaturaTests(TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from django.test import override_settings
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        cfg = override_settings(MEDIA_ROOT=self.raiz)
        cfg.enable()
        self.addCleanup(cfg.disable)
        self.admin = User.objects.create_superuser('admin_tecnica', password='teste')
        self.negados = []
        for papel in ('dentista', 'secretaria', 'auxiliar'):
            usuario = User.objects.create_user(papel + '_tecnica', password='teste')
            PerfilUsuario.objects.create(usuario=usuario, papel=papel)
            self.negados.append(usuario)
        self.negados.append(User.objects.create_user('sem_perfil_tecnica', password='teste'))
        self.negados.append(User.objects.create_user('staff_tecnica', password='teste', is_staff=True))

    def payload(self):
        import base64
        return {'papel': 'dentista', 'nome_assinante': 'Nome restrito fictício',
                'imagem_base64': 'data:image/png;base64,' + base64.b64encode(PNG).decode()}

    def test_get_post_negados_sem_metadados_ou_gravacao(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/fichas/assinatura/', self.payload()).status_code, 302)
        antes = set(self.raiz.rglob('*.png'))
        for usuario in self.negados:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                resposta = self.client.get('/fichas/assinatura/')
                self.assertEqual(resposta.status_code, 403)
                self.assertNotContains(resposta, 'Nome restrito fictício', status_code=403)
                self.assertEqual(self.client.post('/fichas/assinatura/', self.payload()).status_code, 403)
        self.assertEqual(AssinaturaEletronica.objects.count(), 1)
        self.assertEqual(set(self.raiz.rglob('*.png')), antes)

    def test_administrador_preserva_get_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/fichas/assinatura/').status_code, 200)
        self.assertEqual(self.client.post('/fichas/assinatura/', self.payload()).status_code, 302)
        self.assertEqual(AssinaturaEletronica.objects.count(), 1)

    def test_anonimo_redirecionado(self):
        self.assertEqual(self.client.get('/fichas/assinatura/').status_code, 302)
        self.assertEqual(self.client.post('/fichas/assinatura/', self.payload()).status_code, 302)
        self.assertFalse(AssinaturaEletronica.objects.exists())
