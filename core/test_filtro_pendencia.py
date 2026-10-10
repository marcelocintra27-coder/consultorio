"""Lista de pacientes: filtro "Com pendência" e marcas em cada linha."""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, MaterialUsado, Paciente


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FiltroPendenciaTests(TestCase):
    def setUp(self):
        self.dentista = Dentista.objects.create(
            nome_completo='Dra. Filtro', sala=Sala.objects.create(nome='Sala Filtro'),
        )
        self.admin = User.objects.create_superuser('admin_filtro', password='x')
        self.secretaria = User.objects.create_user('sec_filtro', password='x')
        PerfilUsuario.objects.create(usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA)
        self.lista = reverse('core:listar_pacientes')
        ontem = timezone.localdate() - timedelta(days=1)

        self.em_dia = self.criar('Paciente Em Dia', cpf='111.111.111-11', whatsapp='62999990001')
        self.sem_whats = self.criar('Paciente Sem Whats', cpf='222.222.222-22', whatsapp='')
        self.devendo = self.criar('Paciente Devendo', cpf='333.333.333-33', whatsapp='62999990003')
        consulta = Consulta.objects.create(
            paciente=self.devendo, dentista=self.dentista, data=ontem,
            hora_inicio=time(9), hora_fim=time(10),
        )
        MaterialUsado.objects.create(consulta=consulta, descricao='Resina', valor=150)
        self.pago = self.criar('Paciente Pago', cpf='444.444.444-44', whatsapp='62999990004')
        paga = Consulta.objects.create(
            paciente=self.pago, dentista=self.dentista, data=ontem,
            hora_inicio=time(11), hora_fim=time(12), pago=True,
        )
        MaterialUsado.objects.create(consulta=paga, descricao='Resina', valor=150)
        self.anamnese = self.criar('Paciente Anamnese', cpf='555.555.555-55', whatsapp='62999990005')
        self.client.force_login(self.admin)
        self.client.post(
            reverse('core:nova_ficha_anamnese', args=[self.anamnese.pk]), {'tipo': 'odontologica'},
        )

    def criar(self, nome, **extra):
        return Paciente.objects.create(
            nome_completo=nome, data_nascimento=date(1990, 1, 1), telefone='62900000000', **extra,
        )

    def test_filtro_mostra_so_quem_tem_pendencia(self):
        html = self.client.get(self.lista, {'filtro': 'pendencia'}).content.decode()
        self.assertIn('Paciente Sem Whats', html)
        self.assertIn('Paciente Devendo', html)
        self.assertIn('Paciente Anamnese', html)
        self.assertNotIn('Paciente Em Dia', html)
        self.assertNotIn('Paciente Pago', html)
        self.assertIn('aria-current="page">Com pendência', html)

    def test_marcas_aparecem_na_lista_normal(self):
        html = self.client.get(self.lista).content.decode()
        self.assertIn('Paciente Em Dia', html)
        self.assertIn('Valor em aberto', html)
        self.assertIn('Anamnese aberta', html)
        self.assertIn('Cadastro incompleto', html)

    def test_secretaria_nao_ve_valor_nem_anamnese(self):
        self.client.force_login(self.secretaria)
        html = self.client.get(self.lista, {'filtro': 'pendencia'}).content.decode()
        self.assertIn('Paciente Sem Whats', html)
        self.assertNotIn('Paciente Devendo', html)
        self.assertNotIn('Paciente Anamnese', html)
        self.assertNotIn('Valor em aberto', html)

    def test_filtro_combina_com_busca_e_lista_vazia(self):
        resposta = self.client.get(self.lista, {'filtro': 'pendencia', 'q': 'Em Dia'})
        self.assertContains(resposta, 'Nenhum paciente com pendência')
        self.assertContains(resposta, 'name="filtro" value="pendencia"')

    def test_paginacao_mantem_o_filtro(self):
        for i in range(30):
            self.criar(f'Sem Whats {i:02d}', whatsapp='')
        resposta = self.client.get(self.lista, {'filtro': 'pendencia'})
        self.assertContains(resposta, 'filtro=pendencia&amp;pagina=2')
