from django.conf import settings
from django.db import models


class ConsentimentoIA(models.Model):
    FINALIDADE_CHOICES = [
        ("transcricao_voz", "Transcrição de voz do prontuário"),
        ("analise_imagem", "Análise de imagem/radiografia"),
        ("rascunho_documento", "Rascunho de documento"),
        ("outros", "Outros"),
    ]

    paciente = models.ForeignKey("core.Paciente", on_delete=models.PROTECT, related_name="consentimentos_ia", verbose_name="Paciente")
    finalidade = models.CharField("Finalidade", max_length=30, choices=FINALIDADE_CHOICES)
    concedido = models.BooleanField("Concedido", default=False)
    texto_versao = models.CharField("Versão do termo", max_length=20, blank=True)
    concedido_em = models.DateTimeField("Concedido em", null=True, blank=True)
    revogado_em = models.DateTimeField("Revogado em", null=True, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="consentimentos_ia_registrados", verbose_name="Registrado por")
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Consentimento de IA"
        verbose_name_plural = "Consentimentos de IA"
        ordering = ["-criado_em"]

    def __str__(self):
        situacao = "concedido" if self.concedido else "não concedido"
        return f"{self.paciente} - {self.get_finalidade_display()} ({situacao})"


class RegistroAuditoriaIA(models.Model):
    RECURSO_CHOICES = [
        ("transcricao_voz", "Transcrição de voz"),
        ("analise_imagem", "Análise de imagem"),
        ("rascunho_documento", "Rascunho de documento"),
        ("outros", "Outros"),
    ]

    DECISAO_CHOICES = [
        ("pendente", "Pendente"),
        ("aceita", "Aceita"),
        ("editada", "Editada"),
        ("rejeitada", "Rejeitada"),
    ]

    data_hora = models.DateTimeField("Data e hora", auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="registros_auditoria_ia", verbose_name="Usuário")
    paciente = models.ForeignKey("core.Paciente", on_delete=models.PROTECT, null=True, blank=True, related_name="registros_auditoria_ia", verbose_name="Paciente")
    recurso = models.CharField("Recurso", max_length=30, choices=RECURSO_CHOICES)
    modelo_utilizado = models.CharField("Modelo utilizado", max_length=100, blank=True)
    entrada_resumo = models.TextField("Resumo da entrada", blank=True)
    saida_sugerida = models.TextField("Saída sugerida pela IA", blank=True)
    decisao = models.CharField("Decisão", max_length=20, choices=DECISAO_CHOICES, default="pendente")
    texto_final = models.TextField("Texto final aprovado", blank=True)
    decidido_em = models.DateTimeField("Decidido em", null=True, blank=True)
    observacoes = models.TextField("Observações", blank=True)

    class Meta:
        verbose_name = "Registro de auditoria de IA"
        verbose_name_plural = "Registros de auditoria de IA"
        ordering = ["-data_hora"]

    def __str__(self):
        return f"{self.get_recurso_display()} - {self.get_decisao_display()}"
