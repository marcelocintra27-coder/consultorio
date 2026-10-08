"""A ordem das folhas de um paciente continua entre envios."""
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
import importlib
import tempfile
from uuid import uuid4

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from locacao.models import Dentista, PerfilUsuario, Sala

from .models import Consulta, DigitalizacaoFicha, Paciente

renumerar_folhas_por_paciente = importlib.import_module(
    'core.migrations.0043_ordem_folhas_continua',
).renumerar_folhas_por_paciente


def _png(nome='folha.png'):
    saida = BytesIO()
    Image.new('RGB', (20, 20), 'white').save(saida, format='PNG')
    return SimpleUploadedFile(nome, saida.getvalue(), 'image/png')


def _foto(ficha):
    return {
        'paciente_id': ficha.paciente_id,
        'tipo': ficha.tipo,
        'status': ficha.status,
        'lote': ficha.lote,
        'criado_em': ficha.criado_em,
        'imagem': ficha.imagem.name,
        'digitalizado_por_id': ficha.digitalizado_por_id,
        'ordem': ficha.ordem,
    }


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OrdemFolhasContinuaTests(TestCase):
    def setUp(self):
        diretorio = tempfile.TemporaryDirectory()
        self.addCleanup(diretorio.cleanup)
        raiz = Path(diretorio.name)
        cfg = override_settings(MEDIA_ROOT=raiz / 'media', FILE_UPLOAD_TEMP_DIR=raiz)
        cfg.enable()
        self.addCleanup(cfg.disable)
        self.sala = Sala.objects.create(nome='Sala ordem')
        self.dentista = Dentista.objects.create(nome_completo='Dra. Ordem', sala=self.sala)
        self.user = User.objects.create_user('dentista_ordem', password='x', first_name='Dra')
        PerfilUsuario.objects.create(
            usuario=self.user, papel=PerfilUsuario.Papel.DENTISTA, dentista=self.dentista,
        )
        self.admin = User.objects.create_superuser('admin_ordem', password='x')
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente com folhas',
            data_nascimento=date(1984, 3, 3),
            telefone='11955550000',
        )
        Consulta.objects.create(
            paciente=self.paciente, dentista=self.dentista,
            data=date(2026, 10, 8), hora_inicio=time(9), hora_fim=time(10),
        )
        self.envio = reverse('core:digitalizacao_upload')
        self.client.force_login(self.user)

    def _enviar(self, paciente, ordens, tipos):
        fotos = [_png(f'folha-{indice}.png') for indice in range(len(ordens))]
        return self.client.post(self.envio, {
            'paciente': paciente.pk,
            'imagens': fotos,
            'tipo': tipos,
            'ordem': [str(item) for item in ordens],
        }, follow=True)

    def test_segundo_envio_continua_a_numeracao_e_as_telas_seguem_essa_ordem(self):
        primeiro = self._enviar(
            self.paciente, [1, 2, 3], ['cadastro', 'anamnese', 'evolucao'],
        )
        self.assertEqual(primeiro.status_code, 200)
        self.assertEqual(
            list(DigitalizacaoFicha.objects.filter(paciente=self.paciente).order_by('ordem').values_list('ordem', flat=True)),
            [1, 2, 3],
        )

        segundo = self._enviar(self.paciente, [1, 2], ['exame', 'outro'])
        self.assertEqual(segundo.status_code, 200)
        self.assertContains(segundo, 'Pronto!')
        html_pronto = segundo.content.decode()
        self.assertLess(html_pronto.find('Folha 4'), html_pronto.find('Folha 5'))
        gravadas = list(
            DigitalizacaoFicha.objects.filter(paciente=self.paciente).order_by('ordem', 'pk')
        )
        self.assertEqual([ficha.ordem for ficha in gravadas], [1, 2, 3, 4, 5])
        self.assertEqual(
            [ficha.tipo for ficha in gravadas],
            ['cadastro', 'anamnese', 'evolucao', 'exame', 'outro'],
        )
        self.assertEqual(len({ficha.lote for ficha in gravadas}), 2)

        pagina = self.client.get(
            reverse('core:folhas_digitalizacao_paciente', args=[self.paciente.pk]),
        )
        self.assertEqual(pagina.status_code, 200)
        html = pagina.content.decode()
        posicoes = [html.find(f'Folha {numero}') for numero in range(1, 6)]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertTrue(all(posicao >= 0 for posicao in posicoes))

        self.client.force_login(self.admin)
        edicao = self.client.get(reverse('core:editar_paciente', args=[self.paciente.pk]))
        texto = edicao.content.decode()
        links = [
            texto.find(reverse('core:detalhe_digitalizacao', args=[ficha.pk]))
            for ficha in gravadas
        ]
        self.assertEqual(links, sorted(links))
        self.assertTrue(all(link >= 0 for link in links))

    def test_ordem_escolhida_dentro_do_envio_e_mantida(self):
        self._enviar(self.paciente, [1, 2, 3], ['cadastro', 'anamnese', 'evolucao'])
        resposta = self._enviar(
            self.paciente, [2, 1, 3], ['exame', 'encaminhamento', 'outro'],
        )
        self.assertEqual(resposta.status_code, 200)
        novas = list(
            DigitalizacaoFicha.objects.filter(paciente=self.paciente, ordem__gte=4)
            .order_by('pk')
        )
        self.assertEqual([ficha.ordem for ficha in novas], [5, 4, 6])
        self.assertEqual(
            [ficha.tipo for ficha in novas],
            ['exame', 'encaminhamento', 'outro'],
        )
        pagina = self.client.get(
            reverse('core:folhas_digitalizacao_paciente', args=[self.paciente.pk]),
        )
        html = pagina.content.decode()
        self.assertLess(html.find('Encaminhamento'), html.find('Exame'))
        self.assertLess(html.find('Exame'), html.find('Outro'))


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RenumerarFolhasExistentesTests(TestCase):
    def setUp(self):
        diretorio = tempfile.TemporaryDirectory()
        self.addCleanup(diretorio.cleanup)
        cfg = override_settings(MEDIA_ROOT=Path(diretorio.name))
        cfg.enable()
        self.addCleanup(cfg.disable)
        self.paciente = Paciente.objects.create(
            nome_completo='Paciente dois envios',
            data_nascimento=date(1970, 1, 1),
            telefone='11966660000',
        )
        self.unico = Paciente.objects.create(
            nome_completo='Paciente um envio',
            data_nascimento=date(1971, 2, 2),
            telefone='11977770000',
        )
        self.inicio = timezone.make_aware(datetime(2026, 10, 1, 10, 0))

    def _folha(self, paciente, ordem, quando, lote=None, tipo='cadastro', nome='folha.png'):
        ficha = DigitalizacaoFicha.objects.create(
            paciente=paciente,
            imagem=_png(nome),
            tipo=tipo,
            ordem=ordem,
            lote=lote,
        )
        DigitalizacaoFicha.objects.filter(pk=ficha.pk).update(criado_em=quando)
        ficha.refresh_from_db()
        return ficha

    def test_migration_renumera_dois_envios_intercalados(self):
        lote_a = uuid4()
        lote_b = uuid4()
        # O gravado no primeiro envio não segue a ordem da tela: a folha 2
        # foi salva antes da folha 1. O segundo envio recomeça em 1.
        a2 = self._folha(
            self.paciente, 2, self.inicio, lote_a, 'anamnese', 'a2.png',
        )
        a1 = self._folha(
            self.paciente, 1, self.inicio + timedelta(seconds=1), lote_a, 'cadastro', 'a1.png',
        )
        a3 = self._folha(
            self.paciente, 3, self.inicio + timedelta(seconds=2), lote_a, 'evolucao', 'a3.png',
        )
        solta = self._folha(
            self.paciente, 9, self.inicio + timedelta(days=1), None, 'exame', 'solta.png',
        )
        b_arquivo = self._folha(
            self.paciente, 2, self.inicio + timedelta(days=2), lote_b, 'outro', 'b2.png',
        )
        b_escolhida = self._folha(
            self.paciente, 1, self.inicio + timedelta(days=2, seconds=1), lote_b,
            'encaminhamento', 'b1.png',
        )
        sem_paciente = self._folha(
            None, 4, self.inicio, uuid4(), 'cadastro', 'sem.png',
        )
        antes_sem = _foto(sem_paciente)

        renumerar_folhas_por_paciente(apps, None)

        ordem = list(
            DigitalizacaoFicha.objects.filter(paciente=self.paciente).order_by('ordem', 'pk')
        )
        self.assertEqual(
            [ficha.pk for ficha in ordem],
            [a1.pk, a2.pk, a3.pk, solta.pk, b_escolhida.pk, b_arquivo.pk],
        )
        self.assertEqual([ficha.ordem for ficha in ordem], [1, 2, 3, 4, 5, 6])
        self.assertEqual(
            [ficha.tipo for ficha in ordem],
            ['cadastro', 'anamnese', 'evolucao', 'exame', 'encaminhamento', 'outro'],
        )
        for ficha in ordem:
            ficha.refresh_from_db()
        self.assertEqual(a1.imagem.name, DigitalizacaoFicha.objects.get(pk=a1.pk).imagem.name)
        sem_paciente.refresh_from_db()
        self.assertEqual(_foto(sem_paciente), antes_sem)

    def test_paciente_com_um_envio_nao_muda(self):
        lote = uuid4()
        folhas = [
            self._folha(self.unico, 1, self.inicio, lote, 'cadastro', 'u1.png'),
            self._folha(
                self.unico, 2, self.inicio + timedelta(seconds=5), lote, 'anamnese', 'u2.png',
            ),
            self._folha(
                self.unico, 3, self.inicio + timedelta(seconds=1), lote, 'evolucao', 'u3.png',
            ),
        ]
        antes = {ficha.pk: _foto(ficha) for ficha in folhas}
        sem = self._folha(None, 1, self.inicio + timedelta(days=3), None, 'outro', 'fora.png')
        antes_sem = _foto(sem)

        renumerar_folhas_por_paciente(apps, None)

        for ficha in folhas:
            ficha.refresh_from_db()
            self.assertEqual(_foto(ficha), antes[ficha.pk])
        sem.refresh_from_db()
        self.assertEqual(_foto(sem), antes_sem)
