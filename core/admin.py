from django.contrib import admin
from django.db import transaction

from .admin_clinico import AdminClinicoProtegido, InlineClinicoProtegido
from .auditoria_paciente import (
    acao_da_mudanca,
    diferencas,
    registrar_auditoria_paciente,
    snapshot,
    valores_iniciais,
)
from .models import RetificacaoDocumento
from .models import Prescricao
from .models import (
    Convenio,
    Paciente,
    Evolucao,
    Consulta,
    MaterialUsado,
    Procedimento,
    PrecoProcedimento,
    LancamentoAtendimento,
    AuditoriaConsulta,
    AuditoriaPaciente,
    MensagemWhatsApp,
    AtividadeDiaria,
    RegistroAcesso,
    ContaReceber,
    ParcelaContaReceber,
    RecebimentoPaciente,
    AuditoriaFinanceira,
    Fornecedor,
    CategoriaContaPagar,
    ContaPagar,
    BaixaContaPagar,
    AuditoriaContaPagar,
    ProcedimentoUniodonto,
    RepasseUniodonto,
    AssinaturaEletronica,
    FichaCadastroAnamnese,
    DigitalizacaoFicha,
    TrocaPacienteDigitalizacao,
    TrocaTipoDigitalizacao,
    RegistroEvolucaoClinica,
    FichaPlanoTratamento,
    ItemConsentimentoProcedimento,
    ResponsavelPlanoTratamento,
    FichaAutorizacaoCusto,
    ItemAutorizacaoCusto,
)


@admin.register(Convenio)
class ConvenioAdmin(admin.ModelAdmin):
    list_display = (
        'nome',
        'valor_hora',
        'percentual_desconto',
        'percentual_imposto',
        'ativo',
    )
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = (
        'nome_completo',
        'cpf',
        'convenio',
        'telefone',
        'ativo',
        'cadastrado_em',
    )
    list_filter = ('ativo', 'convenio')
    search_fields = (
        'nome_completo',
        'cpf',
        'telefone',
        'whatsapp',
        'email',
        'carteirinha',
    )
    autocomplete_fields = ('convenio',)
    exclude = ('nome_busca', 'cpf_busca', 'telefone_busca', 'whatsapp_busca')
    readonly_fields = ('cadastrado_em', 'aceita_lembretes_whatsapp_em')
    list_per_page = 25

    def save_model(self, request, obj, form, change):
        from .busca_paciente import formatar_nome

        obj.nome_completo = formatar_nome(obj.nome_completo)
        with transaction.atomic():
            if change:
                original = Paciente.objects.select_for_update().get(pk=obj.pk)
                alteracoes = diferencas(snapshot(original), obj)
            super().save_model(request, obj, form, change)
            if change and not alteracoes:
                return
            registrar_auditoria_paciente(
                paciente=obj,
                usuario=request.user,
                acao=(
                    acao_da_mudanca(alteracoes)
                    if change
                    else AuditoriaPaciente.Acao.CRIADO
                ),
                origem=AuditoriaPaciente.Origem.ADMINISTRACAO,
                alteracoes=alteracoes if change else valores_iniciais(obj),
            )


@admin.register(AuditoriaPaciente)
class AuditoriaPacienteAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'usuario', 'acao', 'origem', 'criado_em')
    list_filter = ('paciente', 'usuario', 'acao', 'criado_em')
    search_fields = ('paciente__nome_completo', 'usuario__username')
    readonly_fields = (
        'paciente', 'usuario', 'acao', 'origem', 'alteracoes', 'criado_em',
    )

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class _SomenteLeituraSuperusuarioAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegistroAcesso)
class RegistroAcessoAdmin(_SomenteLeituraSuperusuarioAdmin):
    list_display = ('usuario', 'usuario_digitado', 'tipo', 'fora_do_horario', 'digitalizacao', 'criado_em')
    list_filter = ('tipo', 'fora_do_horario', 'criado_em')
    search_fields = ('usuario__username', 'usuario_digitado', 'digitalizacao__paciente__nome_completo')
    readonly_fields = ('usuario', 'usuario_digitado', 'tipo', 'fora_do_horario', 'digitalizacao', 'criado_em')


@admin.register(AtividadeDiaria)
class AtividadeDiariaAdmin(_SomenteLeituraSuperusuarioAdmin):
    list_display = ('usuario', 'data', 'primeira_atividade', 'ultima_atividade')
    list_filter = ('data',)
    search_fields = ('usuario__username',)
    readonly_fields = ('usuario', 'data', 'primeira_atividade', 'ultima_atividade')


@admin.register(Evolucao)
class EvolucaoAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = ('paciente', 'data', 'descricao')


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    list_display = (
        'paciente',
        'dentista',
        'data',
        'hora_inicio',
        'hora_fim',
        'status',
        'eh_legado',
        'pago',
        'forma_pagamento',
        'valor_a_cobrar',
    )
    list_filter = ('status', 'pago', 'eh_legado', 'forma_pagamento', 'data')
    search_fields = ('paciente__nome_completo',)
    autocomplete_fields = ('paciente', 'dentista')
    readonly_fields = (
        'data', 'hora_inicio', 'hora_fim', 'status', 'dentista',
        'cadastrado_em',
        'valor_a_cobrar',
        'valor_historico',
        'dentista_complementado_em',
        'dentista_complementado_por',
    )
    list_per_page = 25


@admin.register(MaterialUsado)
class MaterialUsadoAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'valor', 'consulta', 'cadastrado_em')
    search_fields = ('descricao', 'consulta__paciente__nome_completo')
    autocomplete_fields = ('consulta',)
    readonly_fields = ('cadastrado_em',)
    list_per_page = 25


@admin.register(Procedimento)
class ProcedimentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'dentista', 'duracao_estimada_minutos', 'ativo')
    list_filter = ('ativo', 'dentista')
    search_fields = ('nome',)
    autocomplete_fields = ('dentista',)


@admin.register(PrecoProcedimento)
class PrecoProcedimentoAdmin(admin.ModelAdmin):
    list_display = ('procedimento', 'convenio', 'valor')
    list_filter = ('convenio',)
    autocomplete_fields = ('procedimento', 'convenio')


@admin.register(LancamentoAtendimento)
class LancamentoAtendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'nome_procedimento',
        'consulta',
        'valor_final',
        'tipo',
        'cadastrado_em',
    )
    list_filter = ('tipo', 'particular')
    search_fields = ('nome_procedimento', 'codigo_tuss')
    autocomplete_fields = (
        'consulta',
        'procedimento',
        'procedimento_uniodonto',
        'dentista',
        'convenio',
    )
    readonly_fields = (
        'nome_procedimento',
        'codigo_tuss',
        'valor_us',
        'fator_us',
        'valor_tabela',
        'percentual_desconto',
        'valor_final',
        'cadastrado_em',
        'cadastrado_por',
    )


@admin.register(MensagemWhatsApp)
class MensagemWhatsAppAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'direcao', 'telefone', 'status', 'acao', 'paciente')
    list_filter = ('direcao', 'status', 'acao')
    search_fields = ('telefone', 'texto', 'paciente__nome_completo', 'id_externo')
    readonly_fields = (
        'consulta', 'paciente', 'lembrete', 'telefone', 'direcao', 'texto',
        'status', 'id_externo', 'acao', 'criado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaConsulta)
class AuditoriaConsultaAdmin(admin.ModelAdmin):
    list_display = ('consulta', 'usuario', 'descricao', 'cadastrado_em')
    readonly_fields = ('consulta', 'usuario', 'descricao', 'cadastrado_em')


class ParcelaContaReceberInline(admin.TabularInline):
    model = ParcelaContaReceber
    extra = 0
    readonly_fields = ('numero', 'vencimento', 'valor_original', 'criado_em')
    can_delete = False
    max_num = 0


@admin.register(ContaReceber)
class ContaReceberAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'descricao', 'data_emissao', 'valor_original', 'criado_por')
    search_fields = ('paciente__nome_completo', 'descricao')
    autocomplete_fields = ('paciente', 'consulta', 'criado_por')
    readonly_fields = ('paciente', 'consulta', 'descricao', 'data_emissao', 'valor_original', 'criado_em', 'criado_por')
    inlines = (ParcelaContaReceberInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecebimentoPaciente)
class RecebimentoPacienteAdmin(admin.ModelAdmin):
    list_display = ('parcela', 'tipo', 'valor', 'desconto', 'recebido_em', 'operador', 'numero_recibo')
    list_filter = ('tipo', 'forma_pagamento')
    readonly_fields = (
        'parcela', 'tipo', 'valor', 'desconto', 'forma_pagamento', 'observacoes',
        'recebido_em', 'operador', 'recebimento_original', 'numero_recibo', 'criado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaFinanceira)
class AuditoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ('conta', 'parcela', 'recebimento', 'usuario', 'acao', 'criado_em')
    list_filter = ('acao',)
    search_fields = ('conta__paciente__nome_completo', 'descricao')
    readonly_fields = ('conta', 'parcela', 'recebimento', 'usuario', 'acao', 'descricao', 'dados', 'criado_em')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'documento', 'contato', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome', 'documento')


@admin.register(CategoriaContaPagar)
class CategoriaContaPagarAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)


@admin.register(ContaPagar)
class ContaPagarAdmin(admin.ModelAdmin):
    list_display = ('fornecedor', 'descricao', 'vencimento', 'valor_original', 'situacao')
    list_filter = ('situacao', 'recorrencia', 'categoria')
    search_fields = ('fornecedor__nome', 'descricao')
    readonly_fields = (
        'fornecedor', 'categoria', 'descricao', 'competencia', 'vencimento',
        'valor_original', 'recorrencia', 'situacao', 'responsavel',
        'aprovado_por', 'aprovado_em', 'observacoes', 'criado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BaixaContaPagar)
class BaixaContaPagarAdmin(admin.ModelAdmin):
    list_display = ('conta', 'valor', 'baixado_em', 'operador')
    readonly_fields = ('conta', 'valor', 'baixado_em', 'operador', 'chave_operacao', 'observacoes', 'criado_em')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaContaPagar)
class AuditoriaContaPagarAdmin(admin.ModelAdmin):
    list_display = ('conta', 'baixa', 'usuario', 'acao', 'criado_em')
    readonly_fields = ('conta', 'baixa', 'usuario', 'acao', 'descricao', 'dados', 'criado_em')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProcedimentoUniodonto)
class ProcedimentoUniodontoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo',
        'nome',
        'categoria',
        'valor_us',
        'valor_reais',
        'fator_us',
        'ativo',
    )
    list_filter = ('categoria', 'ativo')
    search_fields = ('codigo', 'nome')
    readonly_fields = ('codigo', 'nome', 'categoria', 'valor_us', 'valor_reais', 'fator_us')


@admin.register(RepasseUniodonto)
class RepasseUniodontoAdmin(admin.ModelAdmin):
    list_display = (
        'dentista',
        'competencia',
        'producao_bruta',
        'liquido_recebido',
        'liquido_calculado',
    )
    list_filter = ('competencia', 'dentista')
    autocomplete_fields = ('dentista',)
    readonly_fields = ('liquido_calculado', 'cadastrado_em', 'cadastrado_por')


@admin.register(AssinaturaEletronica)
class AssinaturaEletronicaAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = (
        'assinado_em',
        'papel',
        'nome_assinante',
        'tipo_assinatura',
        'tipo_documento',
        'status_verificacao',
    )
    list_filter = ('tipo_assinatura', 'papel', 'tipo_documento')
    search_fields = ('nome_assinante', 'cpf_assinante', 'hash_conteudo')
    readonly_fields = (
        'assinado_em',
        'hash_conteudo',
        'hash_imagem',
        'ip',
        'user_agent',
    )


@admin.register(FichaCadastroAnamnese)
class FichaCadastroAnamneseAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = (
        'paciente',
        'tipo',
        'status',
        'preenchida_por',
        'criado_em',
    )
    list_filter = ('tipo', 'status', 'preenchida_por')
    search_fields = ('paciente__nome_completo', 'cpf', 'nome_completo')
    readonly_fields = ('token', 'criado_em', 'atualizado_em')


@admin.register(RegistroEvolucaoClinica)
class RegistroEvolucaoClinicaAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = (
        'paciente',
        'data',
        'procedimento_etapa',
        'nome_profissional',
        'cro',
    )
    search_fields = (
        'paciente__nome_completo',
        'procedimento_etapa',
        'nome_profissional',
        'cro',
    )
    autocomplete_fields = ('paciente', 'dentista')
    readonly_fields = ('criado_em',)


@admin.register(DigitalizacaoFicha)
class DigitalizacaoFichaAdmin(admin.ModelAdmin):
    list_display = (
        'paciente',
        'tipo',
        'status',
        'digitalizado_por',
        'criado_em',
    )
    list_filter = ('tipo', 'status')
    search_fields = ('paciente__nome_completo',)
    autocomplete_fields = ('paciente',)
    readonly_fields = ('criado_em', 'revisado_em')


@admin.register(TrocaPacienteDigitalizacao)
class TrocaPacienteDigitalizacaoAdmin(_SomenteLeituraSuperusuarioAdmin):
    list_display = (
        'ficha',
        'paciente_anterior',
        'paciente_novo',
        'trocado_por',
        'trocado_em',
    )
    search_fields = (
        'paciente_anterior__nome_completo',
        'paciente_novo__nome_completo',
        'motivo',
    )
    readonly_fields = (
        'ficha',
        'paciente_anterior',
        'paciente_novo',
        'motivo',
        'trocado_por',
        'trocado_em',
    )


@admin.register(TrocaTipoDigitalizacao)
class TrocaTipoDigitalizacaoAdmin(_SomenteLeituraSuperusuarioAdmin):
    list_display = (
        'ficha',
        'tipo_anterior',
        'tipo_novo',
        'trocado_por',
        'trocado_em',
    )
    readonly_fields = (
        'ficha',
        'tipo_anterior',
        'tipo_novo',
        'trocado_por',
        'trocado_em',
    )


class ItemConsentimentoInline(InlineClinicoProtegido, admin.TabularInline):
    model = ItemConsentimentoProcedimento
    extra = 0


class ResponsavelPlanoInline(InlineClinicoProtegido, admin.TabularInline):
    model = ResponsavelPlanoTratamento
    extra = 0


@admin.register(FichaPlanoTratamento)
class FichaPlanoTratamentoAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = ('paciente', 'status', 'criado_em')
    list_filter = ('status',)
    search_fields = ('paciente__nome_completo', 'cpf', 'nome_completo')
    autocomplete_fields = ('paciente',)
    readonly_fields = ('criado_em', 'atualizado_em')
    inlines = (ItemConsentimentoInline, ResponsavelPlanoInline)


class ItemAutorizacaoCustoInline(InlineClinicoProtegido, admin.TabularInline):
    model = ItemAutorizacaoCusto
    extra = 0


@admin.register(FichaAutorizacaoCusto)
class FichaAutorizacaoCustoAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = ('paciente', 'status', 'consulta', 'criado_em')
    list_filter = ('status',)
    search_fields = ('paciente__nome_completo', 'cpf', 'nome_completo')
    autocomplete_fields = ('paciente', 'consulta')
    readonly_fields = ('criado_em', 'atualizado_em')
    inlines = (ItemAutorizacaoCustoInline,)


@admin.register(RetificacaoDocumento)
class RetificacaoDocumentoAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = ('criado_em', 'nome_profissional', 'cro', 'autor')
    readonly_fields = ('criado_em',)


@admin.register(Prescricao)
class PrescricaoAdmin(AdminClinicoProtegido, admin.ModelAdmin):
    list_display = ('criado_em', 'nome_paciente', 'nome_profissional', 'cro', 'status')
    search_fields = ('nome_paciente', 'nome_profissional', 'cro')
    list_filter = ('status',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from . import admin_usuarios  # noqa: E402,F401



