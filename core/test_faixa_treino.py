"""Faixa laranja só no TREINO, inclusive na tela de entrada."""
from django.test import TestCase, override_settings
from django.urls import reverse


class FaixaTreinoTests(TestCase):
    @override_settings(AMBIENTE='homologacao')
    def test_treino_mostra_a_faixa_na_entrada(self):
        self.assertContains(self.client.get(reverse('entrar')), 'TREINO — dados de teste')

    @override_settings(AMBIENTE='production')
    def test_definitivo_nao_mostra(self):
        self.assertNotContains(self.client.get(reverse('entrar')), 'faixa-treino')
