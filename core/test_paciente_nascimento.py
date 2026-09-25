from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locacao.models import PerfilUsuario

from .forms import PacienteForm
from .models import Paciente


def _dados(**extra):
    dados = {
        'nome_completo': 'Paciente Antigo',
        'telefone': '11900000099',
        'data_nascimento': '12/05/1940',
    }
    dados.update(extra)
    return dados


class DataNascimentoPacienteTests(TestCase):
    def setUp(self):
        self.secretaria = User.objects.create_user('secretaria_nasc', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.client.force_login(self.secretaria)

    def test_campo_continua_obrigatorio(self):
        self.assertTrue(PacienteForm.base_fields['data_nascimento'].required)
        self.assertFalse(Paciente._meta.get_field('data_nascimento').blank)
        form = PacienteForm(data=_dados(data_nascimento=''))
        self.assertFalse(form.is_valid())
        self.assertIn('data_nascimento', form.errors)

    def test_aceita_data_antiga_em_formato_brasileiro(self):
        form = PacienteForm(data=_dados())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['data_nascimento'], date(1940, 5, 12))

    def test_edicao_exibe_dd_mm_aaaa_sem_calendario(self):
        paciente = Paciente.objects.create(
            nome_completo='Já cadastrado',
            data_nascimento=date(1940, 5, 12),
            telefone='11900000098',
        )
        html = str(PacienteForm(instance=paciente)['data_nascimento'])
        self.assertIn('value="12/05/1940"', html)
        self.assertIn('inputmode="numeric"', html)
        self.assertNotIn('type="date"', html)

    def test_recusa_data_inexistente_iso_ano_curto_antigo_e_futuro(self):
        invalidos = {
            '31/02/1940': 'Data inexistente. Confira o dia e o mês.',
            '1940-05-12': 'Digite a data completa com 8 números. Exemplo: 12/05/1940.',
            '12/05/40': 'Digite a data completa com 8 números. Exemplo: 12/05/1940.',
            '1/5/1940': 'Digite a data completa com 8 números. Exemplo: 12/05/1940.',
            '01/01/1899': 'O ano não pode ser antes de 1900.',
            '01/01/2099': 'A data de nascimento não pode ser no futuro.',
        }
        for texto, trecho in invalidos.items():
            form = PacienteForm(data=_dados(data_nascimento=texto))
            self.assertFalse(form.is_valid(), texto)
            self.assertIn('data_nascimento', form.errors)
            if trecho:
                self.assertIn(trecho, form.errors['data_nascimento'][0])
        self.assertGreater(date(2099, 1, 1), timezone.localdate())

    def test_post_cadastra_e_edita_em_dd_mm_aaaa(self):
        resposta = self.client.post(
            reverse('core:cadastrar_paciente'),
            _dados(cpf='701.000.000-40'),
        )
        self.assertEqual(resposta.status_code, 302)
        paciente = Paciente.objects.get(cpf='701.000.000-40')
        self.assertEqual(paciente.data_nascimento, date(1940, 5, 12))

        resposta = self.client.post(
            reverse('core:editar_paciente', args=[paciente.pk]),
            _dados(cpf='701.000.000-40', data_nascimento='13/05/1940'),
        )
        self.assertEqual(resposta.status_code, 302)
        paciente.refresh_from_db()
        self.assertEqual(paciente.data_nascimento, date(1940, 5, 13))

    def test_cadastro_renderiza_script_da_mascara(self):
        resposta = self.client.get(reverse('core:cadastrar_paciente'))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        script = html.split('<script>', 1)[-1]
        self.assertIn('id_data_nascimento', script)
        self.assertIn("replace(/\\D/g, '')", script)

    def test_agenda_permanece_com_calendario(self):
        resposta = self.client.get(reverse('core:agendar_consulta'))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'type="date"')
        self.assertNotContains(resposta, 'DD/MM/AAAA')
