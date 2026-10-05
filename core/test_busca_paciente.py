"""Busca tolerante de paciente e aviso de cadastro parecido."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, Paciente


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
        self.assertContains(pagina, 'Digite o nome, CPF ou telefone do paciente')
        self.assertContains(pagina, 'Escolha o paciente')
        self.assertNotContains(pagina, '- Select an option -')
        self.assertNotContains(pagina, '---------')
        self.assertContains(pagina, 'Nenhum paciente encontrado')
        self.assertContains(pagina, 'Cadastrar novo paciente')
        self.assertContains(pagina, '>Trocar<')
        self.assertContains(pagina, 'data-busca="ruth goncalves souza 39053344705 11977776655 11966665555"')
        self.assertContains(pagina, 'data-nascimento="02/02/1980"')
        agenda = self.client.get(reverse('core:agendar_consulta'))
        self.assertEqual(agenda.status_code, 200)
        self.assertContains(agenda, 'Digite o nome, CPF ou telefone do paciente')
        self.assertContains(agenda, 'Escolha o paciente')
        self.assertNotContains(agenda, '- Select an option -')

    def test_nome_arrumado_ao_salvar(self):
        from .busca_paciente import formatar_nome

        self.assertEqual(formatar_nome('  roberto   gomes da silva '), 'Roberto Gomes da Silva')
        self.assertEqual(formatar_nome('ana e maria'), 'Ana e Maria')
        self.assertEqual(formatar_nome('da silva roberto'), 'Da Silva Roberto')
        self.assertEqual(formatar_nome('HOMOLOG-Ana'), 'HOMOLOG-Ana')
        self.assertEqual(formatar_nome('homolog-ana'), 'HOMOLOG-Ana')
        self.assertEqual(formatar_nome('Homolog-Ana'), 'HOMOLOG-Ana')
        self.assertEqual(formatar_nome('HOMOLOG-ana da silva'), 'HOMOLOG-Ana da Silva')
        paciente = Paciente.objects.create(
            nome_completo='  roberto   gomes da silva ',
            data_nascimento=date(1985, 5, 5),
            telefone='11900002222',
        )
        paciente.refresh_from_db()
        self.assertEqual(paciente.nome_completo, 'Roberto Gomes da Silva')
        self.assertEqual(paciente.nome_busca, 'roberto gomes da silva')
        resposta = self.client.post(reverse('core:cadastrar_paciente'), _dados(
            nome_completo='  roberto   gomes da silva ',
            telefone='11900003333',
            data_nascimento='06/06/1986',
        ))
        self.assertEqual(resposta.status_code, 302)
        salvo = Paciente.objects.get(telefone_busca='11900003333')
        self.assertEqual(salvo.nome_completo, 'Roberto Gomes da Silva')

    def test_migracao_arruma_nomes_ja_cadastrados(self):
        import importlib

        from django.apps import apps

        arrumar_nomes = importlib.import_module(
            'core.migrations.0039_nome_paciente_arrumado'
        ).arrumar_nomes
        Paciente.objects.filter(pk=self.ruth.pk).update(
            nome_completo='  roberto   gomes da silva ',
            nome_busca='desatualizado',
        )
        arrumar_nomes(apps, None)
        self.ruth.refresh_from_db()
        self.assertEqual(self.ruth.nome_completo, 'Roberto Gomes da Silva')
        self.assertEqual(self.ruth.nome_busca, 'roberto gomes da silva')

    def test_endpoint_exige_login_e_nao_devolve_dado_clinico(self):
        url = reverse('core:buscar_pacientes')
        self.client.logout()
        anonimo = self.client.get(url, {'q': 'ruth'})
        self.assertEqual(anonimo.status_code, 302)
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(url).json()['pacientes'], [])
        resposta = self.client.get(url, {'q': 'ruth souza'})
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(list(corpo), ['pacientes'])
        self.assertEqual(len(corpo['pacientes']), 1)
        item = corpo['pacientes'][0]
        self.assertEqual(set(item), {'id', 'nome', 'nascimento'})
        self.assertEqual(item['id'], self.ruth.pk)
        self.assertEqual(item['nome'], 'Ruth Gonçalves Souza')
        self.assertEqual(item['nascimento'], '02/02/1980')
        texto = resposta.content.decode()
        self.assertNotIn('alergia registrada no prontuário', texto)
        self.assertNotIn('observacoes', texto)
        self.assertNotIn('97777', texto)
        self.assertNotIn('endereco', texto)
        for indice in range(12):
            Paciente.objects.create(
                nome_completo=f'Homônimo {indice + 1:02d}',
                data_nascimento=date(1990, 1, 1),
                telefone=f'1191000{indice:04d}',
            )
        limite = self.client.get(url, {'q': 'homonimo'})
        self.assertEqual(len(limite.json()['pacientes']), 10)

    def test_busca_numa_caixa_respeita_quem_cada_perfil_ve(self):
        Paciente.objects.create(
            nome_completo='Carlos Alheio',
            data_nascimento=date(1970, 1, 1),
            telefone='11888880000',
            observacoes='prontuário secreto do alheio',
        )
        sala = Sala.objects.create(nome='Sala busca')
        dentista = Dentista.objects.create(nome_completo='Dra. Busca', sala=sala)
        usuario = User.objects.create_user('dentista_busca', password='x')
        PerfilUsuario.objects.create(
            usuario=usuario, papel=PerfilUsuario.Papel.DENTISTA, dentista=dentista,
        )
        Consulta.objects.create(
            paciente=self.ruth, dentista=dentista,
            data=date(2026, 10, 6), hora_inicio=time(9), hora_fim=time(10),
        )
        url = reverse('core:buscar_pacientes')
        self.client.force_login(usuario)
        ruth = self.client.get(url, {'q': 'ruth'}).json()['pacientes']
        self.assertEqual([item['nome'] for item in ruth], ['Ruth Gonçalves Souza'])
        self.assertEqual(self.client.get(url, {'q': 'alheio'}).json()['pacientes'], [])
        pagina = self.client.get(reverse('core:digitalizacao_upload'))
        self.assertContains(pagina, 'Digite o nome, CPF ou telefone do paciente')
        self.assertContains(pagina, 'Escolha o paciente')
        self.assertNotContains(pagina, '- Select an option -')
        self.assertNotContains(pagina, 'Carlos Alheio')
        self.assertContains(pagina, 'Ruth Gonçalves Souza')
        self.assertNotContains(pagina, 'prontuário secreto do alheio')
        self.client.force_login(self.secretaria)
        alheios = self.client.get(url, {'q': 'alheio'})
        self.assertEqual(
            [item['nome'] for item in alheios.json()['pacientes']],
            ['Carlos Alheio'],
        )
        self.assertNotIn('prontuário secreto do alheio', alheios.content.decode())
        self.assertContains(
            self.client.get(reverse('core:digitalizacao_upload')),
            'Carlos Alheio',
        )

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
