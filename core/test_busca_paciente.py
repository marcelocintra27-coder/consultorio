"""Busca tolerante de paciente e aviso de cadastro parecido."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import PerfilUsuario

from .models import Paciente


def _dados(**extra):
    dados = {
        'nome_completo': 'Pessoa Nova Silva',
        'telefone': '11900001111',
        'data_nascimento': '01/04/1992',
        'whatsapp': '',
        'cpf': '',
    }
    dados.update(extra)
    return dados


class BuscaPacienteTests(TestCase):
    def setUp(self):
        self.secretaria = User.objects.create_user('secretaria_busca', password='x')
        PerfilUsuario.objects.create(
            usuario=self.secretaria, papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.client.force_login(self.secretaria)
        self.ruth = Paciente.objects.create(
            nome_completo='Ruth Gonçalves Souza',
            cpf='390.533.447-05',
            data_nascimento=date(1980, 2, 2),
            telefone='(11) 97777-6655',
            whatsapp='11 96666-5555',
            observacoes='alergia registrada no prontuário',
        )

    def test_busca_por_palavras_fora_de_ordem_e_sem_acento(self):
        lista = reverse('core:listar_pacientes')
        for termo in ('ruth souza', 'souza ruth', 'goncalves', 'GONÇALVES'):
            resposta = self.client.get(lista, {'q': termo})
            self.assertContains(resposta, self.ruth.nome_completo, msg_prefix=termo)
        outra = self.client.get(lista, {'q': 'pessoa inexistente'})
        self.assertNotContains(outra, self.ruth.nome_completo)

    def test_busca_por_cpf_e_telefone(self):
        lista = reverse('core:listar_pacientes')
        for termo in ('39053344705', '390.533.447-05', '11977776655', '11966665555'):
            resposta = self.client.get(lista, {'q': termo})
            self.assertContains(resposta, self.ruth.nome_completo, msg_prefix=termo)
        self.assertEqual(self.ruth.nome_busca, 'ruth goncalves souza')
        self.assertEqual(self.ruth.cpf_busca, '39053344705')

    def test_digitalizacao_usa_a_busca_tolerante(self):
        pagina = self.client.get(reverse('core:digitalizacao_upload'))
        self.assertContains(pagina, 'Buscar por nome, CPF ou telefone')
        self.assertContains(pagina, 'data-busca="ruth goncalves souza 39053344705 11977776655 11966665555"')

    def test_aviso_por_data_e_nome_sem_dado_clinico(self):
        resposta = self.client.post(reverse('core:cadastrar_paciente'), _dados(
            nome_completo='Souza Ruth de Oliveira',
            data_nascimento='02/02/1980',
            telefone='11922223333',
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Já existe paciente parecido')
        self.assertContains(resposta, self.ruth.nome_completo)
        self.assertContains(resposta, '02/02/1980')
        self.assertContains(resposta, self.ruth.telefone)
        self.assertContains(resposta, 'É este — abrir cadastro existente')
        self.assertContains(
            resposta, reverse('core:editar_paciente', args=[self.ruth.pk]),
        )
        self.assertNotContains(resposta, 'alergia registrada no prontuário')
        self.assertNotContains(resposta, 'Anamnese')
        self.assertNotContains(resposta, 'Evolução')
        self.assertEqual(Paciente.objects.count(), 1)

    def test_aviso_por_telefone_e_nome(self):
        resposta = self.client.post(reverse('core:cadastrar_paciente'), _dados(
            nome_completo='Carlos Souza',
            data_nascimento='03/03/1999',
            telefone='11966665555',
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Já existe paciente parecido')
        self.assertContains(resposta, self.ruth.nome_completo)
        self.assertNotContains(resposta, 'alergia registrada no prontuário')
        self.assertEqual(Paciente.objects.count(), 1)

    def test_cadastrar_mesmo_assim_exige_confirmacao(self):
        dados = _dados(
            nome_completo='Souza Ruth de Oliveira',
            data_nascimento='02/02/1980',
            telefone='11922223333',
        )
        sem_caixa = self.client.post(reverse('core:cadastrar_paciente'), {
            **dados, 'cadastrar_mesmo_assim': '1',
        })
        self.assertEqual(sem_caixa.status_code, 200)
        self.assertContains(sem_caixa, 'Marque a confirmação para cadastrar mesmo assim.')
        self.assertEqual(Paciente.objects.count(), 1)

        com_caixa = self.client.post(reverse('core:cadastrar_paciente'), {
            **dados,
            'cadastrar_mesmo_assim': '1',
            'confirmar_duplicado': 'on',
        })
        self.assertEqual(com_caixa.status_code, 302)
        self.assertEqual(Paciente.objects.count(), 2)

    def test_cpf_igual_continua_bloqueado(self):
        resposta = self.client.post(reverse('core:cadastrar_paciente'), {
            **_dados(nome_completo='Outra Ruth', cpf='39053344705'),
            'cadastrar_mesmo_assim': '1',
            'confirmar_duplicado': 'on',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Já existe paciente com este CPF')
        self.assertNotContains(resposta, 'Não, é outra pessoa — cadastrar mesmo assim')
        self.assertEqual(Paciente.objects.filter(nome_completo='Outra Ruth').count(), 0)

    def test_cpf_com_mascara_diferente_bloqueia(self):
        resposta = self.client.post(reverse('core:cadastrar_paciente'), _dados(
            nome_completo='Outra Pessoa',
            cpf='39053344705',
            telefone='11888887777',
            data_nascimento='09/09/2001',
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Já existe paciente com este CPF')
        self.assertEqual(Paciente.objects.count(), 1)
