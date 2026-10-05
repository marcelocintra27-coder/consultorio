from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.agenda import validar_horario_consulta
from core.models import Consulta, Paciente
from locacao.models import Dentista, Despesa, PerfilUsuario, Sala, TurnoLocacao
from locacao.services import calcular_acerto_mensal


SEGUNDA = date(2026, 9, 28)
QUINTA = date(2026, 10, 1)
SEXTA = date(2026, 10, 2)


class LocatariaTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome='Sala Adriana')
        self.outra_sala = Sala.objects.create(nome='Sala Claudia')
        self.titular = Dentista.objects.create(
            nome_completo='Dra. Adriana',
            sala=self.sala,
        )
        self.titular_b = Dentista.objects.create(
            nome_completo='Dra. Claudia',
            sala=self.outra_sala,
        )
        self.titular_c = Dentista.objects.create(
            nome_completo='Dra. Simone',
            sala=Sala.objects.create(nome='Sala Simone'),
        )
        self.admin = User.objects.create_superuser('admin_loc', 'a@example.com', 'x')
        self.staff = User.objects.create_user('staff_loc', is_staff=True)
        self.secretaria = User.objects.create_user('secretaria_loc')
        PerfilUsuario.objects.create(
            usuario=self.secretaria,
            papel=PerfilUsuario.Papel.SECRETARIA,
        )
        self.user_titular = User.objects.create_user('titular_loc')
        PerfilUsuario.objects.create(
            usuario=self.user_titular,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=self.titular,
        )
        self.auxiliar = User.objects.create_user('auxiliar_loc')
        PerfilUsuario.objects.create(
            usuario=self.auxiliar,
            papel=PerfilUsuario.Papel.AUXILIAR,
            dentista=self.titular,
        )
        self.paciente_loc = Paciente.objects.create(
            nome_completo='Paciente da Locatária',
            cpf='705.111.000-01',
            data_nascimento=date(1990, 1, 1),
            telefone='11900000001',
        )
        self.paciente_tit = Paciente.objects.create(
            nome_completo='Paciente da Titular',
            cpf='705.111.000-02',
            data_nascimento=date(1991, 2, 2),
            telefone='11900000002',
        )

    def criar_locataria(self, nome='Dra. X'):
        return Dentista.objects.create(
            nome_completo=nome,
            tipo=Dentista.Tipo.LOCATARIA,
        )

    def turno(self, dentista, dia, inicio, fim, sala=None, ativo=True):
        return TurnoLocacao.objects.create(
            dentista=dentista,
            sala=sala or self.sala,
            dia_semana=dia,
            hora_inicio=inicio,
            hora_fim=fim,
            ativo=ativo,
            criado_por=self.admin,
        )

    def agendar(self, dentista, dia, inicio, fim, paciente=None):
        self.client.force_login(self.admin)
        return self.client.post(reverse('core:agendar_consulta'), {
            'paciente': (paciente or self.paciente_loc).pk,
            'dentista': dentista.pk,
            'data': dia.isoformat(),
            'hora_inicio': inicio,
            'hora_fim': fim,
        })

    def test_dentista_sem_tipo_continua_titular_com_sala(self):
        self.assertEqual(self.titular.tipo, Dentista.Tipo.TITULAR)
        self.assertEqual(Dentista._meta.get_field('tipo').default, Dentista.Tipo.TITULAR)
        self.assertEqual(self.titular.sala, self.sala)
        self.assertFalse(self.titular.eh_locataria)

    def test_duas_locatarias_sem_sala_e_titular_sem_sala_recusada(self):
        primeira = self.criar_locataria('Locatária Um')
        segunda = self.criar_locataria('Locatária Dois')
        self.assertIsNone(primeira.sala_id)
        self.assertIsNone(segunda.sala_id)
        sem_sala = Dentista(nome_completo='Sem sala', tipo=Dentista.Tipo.TITULAR)
        with self.assertRaises(ValidationError):
            sem_sala.full_clean()
        com_sala = Dentista(
            nome_completo='Locatária com sala',
            tipo=Dentista.Tipo.LOCATARIA,
            sala=Sala.objects.create(nome='Sala indevida'),
        )
        with self.assertRaises(ValidationError):
            com_sala.full_clean()
        with self.assertRaises(IntegrityError):
            Dentista.objects.create(
                nome_completo='Outra titular',
                sala=self.sala,
            )

    def test_turnos_sobrepostos_na_mesma_sala_sao_recusados(self):
        locataria = self.criar_locataria()
        self.turno(locataria, 0, time(8), time(12))
        with self.assertRaises(ValidationError):
            self.turno(locataria, 0, time(10), time(11))
        self.turno(locataria, 0, time(12), time(13))
        self.turno(locataria, 3, time(8), time(12))
        outra = self.criar_locataria('Dra. Y')
        with self.assertRaises(ValidationError):
            self.turno(outra, 0, time(9), time(10))
        self.turno(outra, 0, time(8), time(12), sala=self.outra_sala)
        with self.assertRaises(ValidationError):
            self.turno(outra, 0, time(9), time(11), sala=self.sala)
        primeiro = locataria.turnos.get(dia_semana=0, hora_inicio=time(8))
        primeiro.ativo = False
        primeiro.save()
        terceira = self.criar_locataria('Dra. Z')
        self.turno(terceira, 0, time(8), time(12))

    def test_telas_de_turnos_e_resumo_na_lista(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('locacao:cadastrar_dentista'), {
            'nome_completo': 'Dra. X',
            'tipo': Dentista.Tipo.LOCATARIA,
            'sala': self.sala.pk,
            'valor_hora': '0',
        })
        locataria = Dentista.objects.get(nome_completo='Dra. X')
        self.assertIsNone(locataria.sala_id)
        self.assertRedirects(resposta, reverse('locacao:editar_dentista', args=[locataria.pk]))
        editar = self.client.get(reverse('locacao:editar_dentista', args=[locataria.pk]))
        self.assertContains(editar, 'Turnos')
        for dia in (0, 3, 4):
            criado = self.client.post(
                reverse('locacao:cadastrar_turno', args=[locataria.pk]),
                {
                    'sala': self.sala.pk,
                    'dia_semana': dia,
                    'hora_inicio': '08:00',
                    'hora_fim': '12:00',
                    'observacao': '',
                },
            )
            self.assertRedirects(criado, reverse('locacao:editar_dentista', args=[locataria.pk]))
        conflito = self.client.post(
            reverse('locacao:cadastrar_turno', args=[locataria.pk]),
            {
                'sala': self.sala.pk,
                'dia_semana': 0,
                'hora_inicio': '10:00',
                'hora_fim': '11:00',
                'observacao': '',
            },
        )
        self.assertEqual(conflito.status_code, 200)
        self.assertContains(conflito, 'turno ativo sobreposto')
        self.assertEqual(locataria.turnos.filter(ativo=True).count(), 3)
        lista = self.client.get(reverse('locacao:listar_dentistas'))
        self.assertContains(lista, 'Locatária de turnos')
        self.assertContains(lista, 'Titular')
        self.assertContains(
            lista,
            'Sala Adriana — seg 08:00–12:00; qui 08:00–12:00; sex 08:00–12:00',
        )
        turno = locataria.turnos.get(dia_semana=4)
        editado = self.client.post(
            reverse('locacao:editar_turno', args=[locataria.pk, turno.pk]),
            {
                'sala': self.sala.pk,
                'dia_semana': 4,
                'hora_inicio': '13:00',
                'hora_fim': '17:00',
                'observacao': 'tarde',
            },
        )
        self.assertRedirects(editado, reverse('locacao:editar_dentista', args=[locataria.pk]))
        turno.refresh_from_db()
        self.assertEqual(turno.hora_inicio, time(13, 0))
        self.assertEqual(turno.observacao, 'tarde')
        self.client.post(reverse('locacao:desativar_turno', args=[locataria.pk, turno.pk]))
        turno.refresh_from_db()
        self.assertFalse(turno.ativo)
        lista = self.client.get(reverse('locacao:listar_dentistas'))
        self.assertNotContains(lista, 'sex 13:00')
        for usuario in (self.secretaria, self.user_titular, self.auxiliar, self.staff):
            self.client.force_login(usuario)
            self.assertEqual(
                self.client.get(reverse('locacao:editar_dentista', args=[locataria.pk])).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    reverse('locacao:cadastrar_turno', args=[locataria.pk]),
                    {
                        'sala': self.sala.pk,
                        'dia_semana': 1,
                        'hora_inicio': '08:00',
                        'hora_fim': '12:00',
                    },
                ).status_code,
                403,
            )

    def test_agenda_respeita_turno_e_a_titular(self):
        locataria = self.criar_locataria()
        self.turno(locataria, 0, time(8), time(12))
        self.turno(locataria, 4, time(13), time(18))
        dentro = self.agendar(locataria, SEGUNDA, '09:00', '10:00')
        self.assertEqual(dentro.status_code, 302)
        consulta = Consulta.objects.get(dentista=locataria)
        self.assertEqual(consulta.sala_agenda, self.sala)
        agenda = self.client.get(reverse('core:listar_consultas') + '?data=2026-09-28')
        self.assertContains(agenda, 'Sala Adriana')
        ficha = self.client.get(reverse('core:ficha_consulta', args=[consulta.pk]))
        self.assertContains(ficha, 'Sala Adriana')
        fora = self.agendar(locataria, SEGUNDA, '13:00', '14:00', self.paciente_tit)
        self.assertEqual(fora.status_code, 200)
        self.assertContains(fora, 'fora dos turnos ativos da locatária')
        self.assertEqual(Consulta.objects.filter(dentista=locataria).count(), 1)
        alugada = self.agendar(self.titular, SEGUNDA, '09:00', '10:00', self.paciente_tit)
        self.assertEqual(alugada.status_code, 200)
        self.assertContains(alugada, 'Esse horário da sala está alugado para Dra. X')
        livre = self.agendar(self.titular, QUINTA, '13:00', '14:00', self.paciente_tit)
        self.assertEqual(livre.status_code, 302)
        Consulta.objects.create(
            paciente=self.paciente_tit,
            dentista=self.titular,
            data=SEXTA,
            hora_inicio=time(14),
            hora_fim=time(15),
        )
        ocupada = self.agendar(locataria, SEXTA, '14:00', '15:00')
        self.assertEqual(ocupada.status_code, 200)
        self.assertContains(ocupada, 'A titular da sala já tem consulta neste horário.')
        depois = self.agendar(locataria, SEXTA, '15:00', '16:00')
        self.assertEqual(depois.status_code, 302)
        validar_horario_consulta(self.titular.pk, QUINTA, time(8), time(9))
        cancelada = Consulta.objects.create(
            paciente=self.paciente_tit,
            dentista=self.titular,
            data=SEGUNDA,
            hora_inicio=time(11),
            hora_fim=time(12),
            status=Consulta.Status.CANCELADA,
        )
        validar_horario_consulta(
            locataria.pk, SEGUNDA, time(11), time(12),
        )
        self.assertEqual(cancelada.status, Consulta.Status.CANCELADA)

    def test_acerto_mensal_nao_muda_com_locataria(self):
        mes = date(2026, 9, 1)
        Despesa.objects.create(
            descricao='Aluguel da clínica',
            valor=Decimal('90.00'),
            competencia=mes,
            tipo=Despesa.Tipo.COMPARTILHADA,
            pago_por=self.titular,
        )

        def foto():
            resultado = calcular_acerto_mensal(mes)
            pares = [
                (item['devedor'].pk, item['credor'].pk, item['valor'], item['valor_calculado'])
                for item in resultado['pares']
            ]
            resumo = [
                (item['dentista'].pk, item['a_receber'], item['a_pagar'], item['saldo'])
                for item in resultado['resumo']
            ]
            return pares, resumo

        antes = foto()
        despesa = Despesa.objects.get()
        self.assertEqual(despesa.valor_cota(), Decimal('30.00'))
        locataria = self.criar_locataria()
        self.turno(locataria, 0, time(8), time(12))
        self.turno(locataria, 3, time(8), time(12))
        self.turno(locataria, 4, time(8), time(12))
        self.assertEqual(despesa.valor_cota(), Decimal('30.00'))
        depois = foto()
        self.assertEqual(antes, depois)
        nomes = [item['dentista'].nome_completo for item in calcular_acerto_mensal(mes)['resumo']]
        self.assertNotIn('Dra. X', nomes)
        self.assertEqual(len(nomes), 3)

    def test_locataria_logada_ve_so_as_consultas_e_pacientes_dela(self):
        locataria = self.criar_locataria()
        self.turno(locataria, 0, time(8), time(12))
        usuario = User.objects.create_user('locataria_loc')
        PerfilUsuario.objects.create(
            usuario=usuario,
            papel=PerfilUsuario.Papel.DENTISTA,
            dentista=locataria,
        )
        consulta_loc = Consulta.objects.create(
            paciente=self.paciente_loc,
            dentista=locataria,
            data=SEGUNDA,
            hora_inicio=time(9),
            hora_fim=time(10),
        )
        consulta_tit = Consulta.objects.create(
            paciente=self.paciente_tit,
            dentista=self.titular,
            data=SEGUNDA,
            hora_inicio=time(14),
            hora_fim=time(15),
        )
        self.client.force_login(usuario)
        pacientes = self.client.get(reverse('core:listar_pacientes'))
        self.assertContains(pacientes, 'Paciente da Locatária')
        self.assertNotContains(pacientes, 'Paciente da Titular')
        agenda = self.client.get(reverse('core:listar_consultas') + '?data=2026-09-28')
        self.assertContains(agenda, 'Paciente da Locatária')
        self.assertContains(agenda, 'Sala Adriana')
        self.assertNotContains(agenda, 'Paciente da Titular')
        self.assertEqual(
            self.client.get(reverse('core:ficha_consulta', args=[consulta_tit.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('core:ficha_consulta', args=[consulta_loc.pk])).status_code,
            200,
        )
        self.client.force_login(self.secretaria)
        todos = self.client.get(reverse('core:listar_pacientes'))
        self.assertContains(todos, 'Paciente da Locatária')
        self.assertContains(todos, 'Paciente da Titular')
        agenda_secretaria = self.client.get(reverse('core:listar_consultas') + '?data=2026-09-28')
        self.assertContains(agenda_secretaria, 'Paciente da Locatária')
        self.assertContains(agenda_secretaria, 'Paciente da Titular')

    def _consulta(self, dentista, dia, inicio, fim, paciente, status=Consulta.Status.AGENDADA):
        return Consulta.objects.create(
            paciente=paciente,
            dentista=dentista,
            data=dia,
            hora_inicio=inicio,
            hora_fim=fim,
            status=status,
        )

    def test_turno_recusado_quando_titular_tem_consulta_futura(self):
        hoje = date(2026, 10, 1)
        terca = date(2026, 10, 6)
        locataria = self.criar_locataria()
        self._consulta(self.titular, terca, time(8, 30), time(9, 30), self.paciente_tit)
        self._consulta(
            self.titular, terca + timedelta(days=7), time(10), time(11), self.paciente_loc,
        )
        self._consulta(
            self.titular, terca + timedelta(days=14), time(11, 30), time(12, 30), self.paciente_tit,
        )
        with patch('locacao.models.timezone.localdate', return_value=hoje):
            with self.assertRaises(ValidationError) as erro:
                self.turno(locataria, 1, time(8), time(12))
            mensagem = erro.exception.messages[0]
            self.assertIn(
                'Não é possível salvar o turno: a sala já tem 3 consultas marcadas nesse horário.',
                mensagem,
            )
            self.assertIn('Remarque-as antes: ', mensagem)
            self.assertIn('06/10 08:30 Dra. Adriana — Paciente da Titular', mensagem)
            self.assertIn('13/10 10:00 Dra. Adriana — Paciente da Locatária', mensagem)
            self.assertIn('20/10 11:30 Dra. Adriana — Paciente da Titular', mensagem)
            self.client.force_login(self.admin)
            resposta = self.client.post(
                reverse('locacao:cadastrar_turno', args=[locataria.pk]),
                {
                    'sala': self.sala.pk,
                    'dia_semana': 1,
                    'hora_inicio': '08:00',
                    'hora_fim': '12:00',
                    'observacao': '',
                },
            )
        self.assertContains(resposta, 'a sala já tem 3 consultas marcadas nesse horário')
        self.assertContains(resposta, '06/10 08:30 Dra. Adriana — Paciente da Titular')
        self.assertFalse(locataria.turnos.exists())

        turno = self.turno(locataria, 0, time(8), time(12))
        turno.dia_semana = 1
        with patch('locacao.models.timezone.localdate', return_value=hoje):
            with self.assertRaises(ValidationError):
                turno.save()
        turno.refresh_from_db()
        self.assertEqual(turno.dia_semana, 0)

        inativo = TurnoLocacao(
            dentista=locataria,
            sala=self.sala,
            dia_semana=1,
            hora_inicio=time(8),
            hora_fim=time(12),
            ativo=False,
        )
        inativo.save()
        inativo.ativo = True
        with patch('locacao.models.timezone.localdate', return_value=hoje):
            with self.assertRaises(ValidationError) as reativado:
                inativo.save()
        self.assertIn('3 consultas marcadas', reativado.exception.messages[0])
        inativo.refresh_from_db()
        self.assertFalse(inativo.ativo)

    def test_turno_aceito_se_consulta_passada_cancelada_ou_fora(self):
        hoje = date(2026, 10, 1)
        terca = date(2026, 10, 6)
        passada = date(2026, 9, 29)
        locataria = self.criar_locataria()
        self._consulta(self.titular, passada, time(8, 30), time(9, 30), self.paciente_tit)
        self._consulta(
            self.titular, terca, time(8, 30), time(9, 30), self.paciente_tit,
            status=Consulta.Status.CANCELADA,
        )
        self._consulta(self.titular, terca, time(14), time(15), self.paciente_loc)
        self._consulta(self.titular, date(2026, 10, 7), time(8, 30), time(9, 30), self.paciente_tit)
        self._consulta(self.titular_b, terca, time(8, 30), time(9, 30), self.paciente_loc)
        with patch('locacao.models.timezone.localdate', return_value=hoje):
            self.turno(locataria, 1, time(8), time(12))
        self.assertEqual(locataria.turnos.filter(ativo=True).count(), 1)

    def test_mensagem_lista_no_maximo_dez_conflitos_e_o_total(self):
        hoje = date(2026, 10, 1)
        locataria = self.criar_locataria()
        terca = date(2026, 10, 6)
        for indice in range(11):
            paciente = Paciente.objects.create(
                nome_completo=f'Paciente {indice + 1:02d}',
                cpf=f'705.222.000-{indice + 1:02d}',
                data_nascimento=date(1992, 1, 1),
                telefone=f'119100000{indice:02d}',
            )
            self._consulta(
                self.titular,
                terca + timedelta(days=7 * indice),
                time(9),
                time(10),
                paciente,
            )
        with patch('locacao.models.timezone.localdate', return_value=hoje):
            with self.assertRaises(ValidationError) as erro:
                self.turno(locataria, 1, time(8), time(12))
        mensagem = erro.exception.messages[0]
        self.assertIn('a sala já tem 11 consultas marcadas nesse horário', mensagem)
        self.assertIn('06/10 09:00 Dra. Adriana — Paciente 01', mensagem)
        self.assertIn('08/12 09:00 Dra. Adriana — Paciente 10', mensagem)
        self.assertNotIn('Paciente 11', mensagem)
        self.assertEqual(mensagem.count('Dra. Adriana'), 10)
