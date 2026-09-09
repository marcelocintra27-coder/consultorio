from datetime import date
from itertools import groupby

from django import forms
from django.utils import timezone
from django.forms.models import ModelChoiceField, ModelChoiceIterator, inlineformset_factory

from .anamnese import (
    SAUDE_BUCAL,
    SAUDE_CONDICOES,
    UFS,
    eh_menor_de_idade,
)
from .autorizacao import TIPOS_QUE_EXIGEM_DESCRICAO
from .plano import CIENCIA_ITENS, COMPLEXIDADE_ITENS
from .models import (
    Convenio,
    Paciente,
    MaterialUsado,
    Consulta,
    Procedimento,
    ProcedimentoUniodonto,
    LancamentoAtendimento,
    RepasseUniodonto,
    AssinaturaEletronica,
    FichaCadastroAnamnese,
    RegistroEvolucaoClinica,
    FichaPlanoTratamento,
    ItemConsentimentoProcedimento,
    ResponsavelPlanoTratamento,
    FichaAutorizacaoCusto,
    ItemAutorizacaoCusto,
)
from locacao.models import Dentista


class PacienteForm(forms.ModelForm):
    data_nascimento = forms.DateField(
        label='data de nascimento',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )

    class Meta:
        model = Paciente
        fields = [
            'nome_completo',
            'cpf',
            'data_nascimento',
            'telefone',
            'whatsapp',
            'email',
            'endereco',
            'convenio',
            'carteirinha',
            'observacoes',
            'instagram',
            'facebook',
            'outra_rede_social',
        ]
        widgets = {
            'cpf': forms.TextInput(attrs={'autocomplete': 'off'}),
            'endereco': forms.Textarea(attrs={'rows': 2}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }


class ConvenioForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = [
            'nome',
            'valor_hora',
            'percentual_desconto',
            'percentual_imposto',
        ]
        widgets = {
            'valor_hora': forms.NumberInput(attrs={'step': '0.01'}),
            'percentual_desconto': forms.NumberInput(attrs={'step': '0.01'}),
            'percentual_imposto': forms.NumberInput(attrs={'step': '0.01'}),
        }


class MaterialUsadoForm(forms.ModelForm):
    class Meta:
        model = MaterialUsado
        fields = [
            'descricao',
            'valor',
        ]
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
        }


class ConsultaForm(forms.ModelForm):
    data = forms.DateField(
        label='data',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    hora_inicio = forms.TimeField(
        label='hora início',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
    )
    hora_fim = forms.TimeField(
        label='hora fim',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
    )
    dentista = forms.ModelChoiceField(
        label='dentista',
        queryset=Dentista.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )
    paciente = forms.ModelChoiceField(
        label='paciente',
        queryset=Paciente.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )

    class Meta:
        model = Consulta
        fields = [
            'paciente',
            'data',
            'hora_inicio',
            'hora_fim',
            'dentista',
            'observacoes',
        ]
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }


class StatusConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta
        fields = ['status']


class ProcedimentoForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        fields = ['nome', 'duracao_estimada_minutos', 'ativo']


class LancamentoForm(forms.Form):
    procedimento = forms.ModelChoiceField(
        label='procedimento',
        queryset=Procedimento.objects.none(),
    )
    convenio = forms.ModelChoiceField(
        label='tabela',
        queryset=Convenio.objects.catalogo_dentista(),
        required=False,
        empty_label='Particular',
    )
    valor_tabela = forms.DecimalField(
        label='valor de tabela',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    percentual_desconto = forms.DecimalField(
        label='desconto (%)',
        max_digits=5,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    valor_final = forms.DecimalField(
        label='valor final',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    tipo = forms.ChoiceField(
        label='tipo',
        choices=LancamentoAtendimento.Tipo.choices,
        initial=LancamentoAtendimento.Tipo.ATENDIMENTO,
    )

    def __init__(self, *args, dentista=None, **kwargs):
        super().__init__(*args, **kwargs)
        if dentista is not None:
            self.fields['procedimento'].queryset = Procedimento.objects.filter(
                dentista=dentista,
                ativo=True,
            ).order_by('nome')
        else:
            self.fields['procedimento'].queryset = Procedimento.objects.none()


class ProcedimentoUniodontoIterator(ModelChoiceIterator):
    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        objetos = list(self.queryset)
        for categoria, grupo in groupby(objetos, key=lambda item: item.categoria):
            rotulo = ProcedimentoUniodonto.Categoria(categoria).label
            yield (rotulo, [self.choice(obj) for obj in grupo])


class ProcedimentoUniodontoChoiceField(ModelChoiceField):
    iterator = ProcedimentoUniodontoIterator

    def label_from_instance(self, obj):
        return f'{obj.codigo} — {obj.nome}'


class LancamentoUniodontoForm(forms.Form):
    procedimento_uniodonto = ProcedimentoUniodontoChoiceField(
        label='procedimento',
        queryset=ProcedimentoUniodonto.objects.none(),
        empty_label='Selecione o procedimento',
    )
    valor_tabela = forms.DecimalField(
        label='valor de tabela',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    percentual_desconto = forms.DecimalField(
        label='desconto (%)',
        max_digits=5,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    valor_final = forms.DecimalField(
        label='valor final',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    tipo = forms.ChoiceField(
        label='tipo',
        choices=LancamentoAtendimento.Tipo.choices,
        initial=LancamentoAtendimento.Tipo.ATENDIMENTO,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['procedimento_uniodonto'].queryset = (
            ProcedimentoUniodonto.objects.filter(ativo=True).order_by(
                'categoria', 'nome'
            )
        )


class ComplementarDentistaForm(forms.Form):
    dentista = forms.ModelChoiceField(
        label='dentista',
        queryset=Dentista.objects.filter(ativo=True).order_by('nome_completo'),
        required=True,
    )


class RepasseUniodontoForm(forms.ModelForm):
    competencia = forms.CharField(
        label='competência',
        widget=forms.TextInput(attrs={'type': 'month'}),
    )

    class Meta:
        model = RepasseUniodonto
        fields = [
            'dentista',
            'competencia',
            'producao_bruta',
            'glosa',
            'estorno',
            'inss_retido',
            'irrf_retido',
            'liquido_recebido',
            'observacoes',
        ]
        widgets = {
            'producao_bruta': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'glosa': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'estorno': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'inss_retido': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'irrf_retido': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'liquido_recebido': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, dentista_fixo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentista'].queryset = Dentista.objects.filter(
            ativo=True
        ).order_by('nome_completo')
        if dentista_fixo is not None:
            self.fields['dentista'].initial = dentista_fixo.pk
            self.fields['dentista'].disabled = True
            self.fields['dentista'].required = False
            self._dentista_fixo = dentista_fixo
        else:
            self._dentista_fixo = None
        if self.instance.pk and self.instance.competencia:
            self.initial['competencia'] = self.instance.competencia.strftime('%Y-%m')
        elif not self.instance.pk:
            hoje = timezone.localdate()
            self.initial.setdefault(
                'competencia', f'{hoje.year:04d}-{hoje.month:02d}'
            )

    def clean_competencia(self):
        bruto = (self.cleaned_data.get('competencia') or '').strip()
        try:
            ano, mes = bruto.split('-')
            return date(int(ano), int(mes), 1)
        except (TypeError, ValueError):
            raise forms.ValidationError('Informe um mês válido.')

    def clean_dentista(self):
        if self._dentista_fixo is not None:
            return self._dentista_fixo
        return self.cleaned_data.get('dentista')

    def clean(self):
        dados = super().clean()
        dentista = dados.get('dentista')
        competencia = dados.get('competencia')
        if dentista and competencia:
            existente = RepasseUniodonto.objects.filter(
                dentista=dentista,
                competencia=competencia,
            )
            if self.instance.pk:
                existente = existente.exclude(pk=self.instance.pk)
            if existente.exists():
                self.add_error(
                    'competencia',
                    'Já existe um extrato para esta dentista nesta competência.',
                )
        return dados


class AssinaturaTesteForm(forms.Form):
    paciente = forms.ModelChoiceField(
        label='paciente',
        queryset=Paciente.objects.filter(ativo=True).order_by('nome_completo'),
        required=False,
    )
    papel = forms.ChoiceField(
        label='quem assina',
        choices=AssinaturaEletronica.Papel.choices,
        initial=AssinaturaEletronica.Papel.PACIENTE,
    )
    nome_assinante = forms.CharField(label='nome de quem assina', max_length=200)
    cpf_assinante = forms.CharField(
        label='CPF de quem assina',
        max_length=18,
        required=False,
    )
    imagem_base64 = forms.CharField(
        label='assinatura',
        widget=forms.HiddenInput(),
    )

    def clean_imagem_base64(self):
        from .assinatura import png_de_data_url

        bruto = self.cleaned_data.get('imagem_base64') or ''
        try:
            png_de_data_url(bruto)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return bruto


def _validar_png_opcional(bruto, obrigatorio):
    from .assinatura import png_de_data_url

    bruto = (bruto or '').strip()
    if not bruto:
        if obrigatorio:
            raise forms.ValidationError('Desenhe a assinatura no quadro.')
        return ''
    try:
        png_de_data_url(bruto)
    except ValueError as exc:
        raise forms.ValidationError(str(exc)) from exc
    return bruto


def _checklist_valido(valores, rotulo):
    valores = list(valores or [])
    chaves = {item[0] for item in (
        SAUDE_CONDICOES if rotulo == 'saude' else SAUDE_BUCAL
    )}
    invalidos = [item for item in valores if item not in chaves]
    if invalidos:
        raise forms.ValidationError('Opção inválida no checklist.')
    if 'nenhuma' in valores and len(valores) > 1:
        raise forms.ValidationError(
            'Se marcar “nenhuma”, não marque as outras opções.'
        )
    return valores


class FichaAnamneseForm(forms.ModelForm):
    saude_condicoes = forms.MultipleChoiceField(
        label='sua saúde',
        choices=SAUDE_CONDICOES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    saude_bucal = forms.MultipleChoiceField(
        label='sua saúde bucal',
        choices=SAUDE_BUCAL,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    uf = forms.ChoiceField(
        label='UF',
        choices=[('', '—')] + list(UFS),
        required=False,
    )
    aceitou_declaracao = forms.BooleanField(
        label='li e concordo com a declaração',
        required=False,
    )
    assinatura_paciente_base64 = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    assinatura_dentista_base64 = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = FichaCadastroAnamnese
        fields = [
            'nome_completo',
            'data_nascimento',
            'cpf',
            'telefone',
            'whatsapp',
            'email',
            'endereco',
            'cidade',
            'uf',
            'profissao',
            'nome_responsavel',
            'saude_condicoes',
            'saude_outra_texto',
            'alergia',
            'alergia_qual',
            'usa_medicamento',
            'medicamento_nome',
            'cirurgia_recente',
            'cirurgia_qual',
            'saude_bucal',
            'data_ultima_consulta',
            'experiencia_anterior',
            'experiencia_relato',
            'o_que_incomoda',
            'o_que_espera',
            'fuma',
            'bebida_alcoolica',
            'range_dentes',
            'gravidez',
            'outra_info_saude',
            'outra_info_relato',
            'aceitou_declaracao',
        ]
        widgets = {
            'data_nascimento': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'data_ultima_consulta': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'endereco': forms.Textarea(attrs={'rows': 2}),
            'experiencia_relato': forms.Textarea(attrs={'rows': 3}),
            'o_que_incomoda': forms.Textarea(attrs={'rows': 3}),
            'o_que_espera': forms.Textarea(attrs={'rows': 3}),
            'outra_info_relato': forms.Textarea(attrs={'rows': 3}),
            'alergia': forms.RadioSelect,
            'usa_medicamento': forms.RadioSelect,
            'cirurgia_recente': forms.RadioSelect,
            'experiencia_anterior': forms.RadioSelect,
            'fuma': forms.RadioSelect,
            'bebida_alcoolica': forms.RadioSelect,
            'range_dentes': forms.RadioSelect,
            'gravidez': forms.RadioSelect,
            'outra_info_saude': forms.RadioSelect,
        }

    def __init__(
        self,
        *args,
        exigir_completo=False,
        coletar_paciente=False,
        coletar_dentista=False,
        **kwargs,
    ):
        self.exigir_completo = exigir_completo
        self.coletar_paciente = coletar_paciente
        self.coletar_dentista = coletar_dentista
        super().__init__(*args, **kwargs)
        self.fields['data_nascimento'].input_formats = ['%Y-%m-%d']
        self.fields['data_ultima_consulta'].input_formats = ['%Y-%m-%d']
        self.fields['data_ultima_consulta'].required = False
        for nome in (
            'alergia',
            'usa_medicamento',
            'cirurgia_recente',
            'experiencia_anterior',
            'fuma',
            'bebida_alcoolica',
            'range_dentes',
            'gravidez',
            'outra_info_saude',
        ):
            self.fields[nome].required = False

    def clean_saude_condicoes(self):
        return _checklist_valido(self.cleaned_data.get('saude_condicoes'), 'saude')

    def clean_saude_bucal(self):
        return _checklist_valido(self.cleaned_data.get('saude_bucal'), 'bucal')

    def clean_assinatura_paciente_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_paciente_base64'),
            self.coletar_paciente,
        )

    def clean_assinatura_dentista_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_dentista_base64'),
            self.coletar_dentista,
        )

    def clean(self):
        dados = super().clean()
        nascimento = dados.get('data_nascimento')
        menor = eh_menor_de_idade(nascimento)
        if menor and not (dados.get('nome_responsavel') or '').strip():
            self.add_error(
                'nome_responsavel',
                'Informe o responsável legal (paciente menor de 18 anos).',
            )
        if not self.exigir_completo:
            return dados
        if not dados.get('saude_condicoes'):
            self.add_error('saude_condicoes', 'Marque ao menos uma opção.')
        if 'outra' in (dados.get('saude_condicoes') or []) and not (
            dados.get('saude_outra_texto') or ''
        ).strip():
            self.add_error('saude_outra_texto', 'Descreva a outra condição.')
        if not dados.get('saude_bucal'):
            self.add_error('saude_bucal', 'Marque ao menos uma opção.')
        pares = [
            ('alergia', 'alergia_qual', 'Descreva a alergia.'),
            ('usa_medicamento', 'medicamento_nome', 'Informe o medicamento.'),
            (
                'cirurgia_recente',
                'cirurgia_qual',
                'Informe a cirurgia ou internação e quando.',
            ),
            (
                'experiencia_anterior',
                'experiencia_relato',
                'Relate a experiência anterior.',
            ),
            (
                'outra_info_saude',
                'outra_info_relato',
                'Relate a informação de saúde.',
            ),
        ]
        for origem, detalhe, mensagem in pares:
            if dados.get(origem) == FichaCadastroAnamnese.SimNao.SIM and not (
                dados.get(detalhe) or ''
            ).strip():
                self.add_error(detalhe, mensagem)
        for nome in (
            'alergia',
            'usa_medicamento',
            'cirurgia_recente',
            'experiencia_anterior',
            'fuma',
            'bebida_alcoolica',
            'range_dentes',
            'gravidez',
            'outra_info_saude',
        ):
            if not dados.get(nome):
                self.add_error(nome, 'Este campo é obrigatório.')
        if not dados.get('aceitou_declaracao'):
            self.add_error(
                'aceitou_declaracao',
                'É preciso concordar com a declaração para enviar a ficha.',
            )
        return dados


class AssinaturaDentistaAnamneseForm(forms.Form):
    assinatura_dentista_base64 = forms.CharField(widget=forms.HiddenInput())

    def clean_assinatura_dentista_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_dentista_base64'),
            True,
        )


class RegistroEvolucaoClinicaForm(forms.ModelForm):
    assinatura_base64 = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        model = RegistroEvolucaoClinica
        fields = [
            'data',
            'procedimento_etapa',
            'descricao_clinica',
            'orientacoes',
            'nome_profissional',
            'cro',
        ]
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descricao_clinica': forms.Textarea(attrs={'rows': 4}),
            'orientacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']
        self.fields['orientacoes'].required = False

    def clean_assinatura_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_base64'),
            True,
        )


class FichaPlanoTratamentoForm(forms.ModelForm):
    ciencia_itens = forms.MultipleChoiceField(
        label='itens informados',
        choices=CIENCIA_ITENS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    complexidade_itens = forms.MultipleChoiceField(
        label='procedimentos de maior complexidade',
        choices=COMPLEXIDADE_ITENS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    uf = forms.ChoiceField(
        label='UF',
        choices=[('', '—')] + list(UFS),
        required=False,
    )
    aceitou_declaracao = forms.BooleanField(
        label='li e concordo com a declaração',
        required=False,
    )
    assinatura_paciente_base64 = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = FichaPlanoTratamento
        fields = [
            'nome_completo',
            'data_nascimento',
            'cpf',
            'telefone',
            'whatsapp',
            'email',
            'endereco',
            'cidade',
            'uf',
            'profissao',
            'nome_responsavel',
            'plano_tratamento',
            'ciencia_itens',
            'aceitou_declaracao',
            'local_assinatura',
            'data_consentimento',
            'complexidade_itens',
        ]
        widgets = {
            'data_nascimento': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'data_consentimento': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'endereco': forms.Textarea(attrs={'rows': 2}),
            'plano_tratamento': forms.Textarea(attrs={'rows': 6}),
        }

    def __init__(self, *args, exigir_completo=False, coletar_paciente=False, **kwargs):
        self.exigir_completo = exigir_completo
        self.coletar_paciente = coletar_paciente
        super().__init__(*args, **kwargs)
        self.fields['data_nascimento'].input_formats = ['%Y-%m-%d']
        self.fields['data_consentimento'].input_formats = ['%Y-%m-%d']
        self.fields['data_consentimento'].required = False

    def clean_assinatura_paciente_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_paciente_base64'),
            self.coletar_paciente,
        )

    def clean(self):
        dados = super().clean()
        if eh_menor_de_idade(dados.get('data_nascimento')) and not (
            dados.get('nome_responsavel') or ''
        ).strip():
            self.add_error(
                'nome_responsavel',
                'Informe o responsável legal (paciente menor de 18 anos).',
            )
        if not self.exigir_completo:
            return dados
        if not (dados.get('plano_tratamento') or '').strip():
            self.add_error('plano_tratamento', 'Descreva o plano de tratamento.')
        if len(dados.get('ciencia_itens') or []) < len(CIENCIA_ITENS):
            self.add_error(
                'ciencia_itens',
                'Marque todos os itens informados ao paciente.',
            )
        if not dados.get('aceitou_declaracao'):
            self.add_error(
                'aceitou_declaracao',
                'É preciso concordar com a declaração para concluir.',
            )
        if not (dados.get('local_assinatura') or '').strip():
            self.add_error('local_assinatura', 'Informe o local.')
        if not dados.get('data_consentimento'):
            self.add_error('data_consentimento', 'Informe a data.')
        return dados


class ItemConsentimentoForm(forms.ModelForm):
    dentistas = forms.ModelMultipleChoiceField(
        label='dentista responsável',
        queryset=Dentista.objects.filter(ativo=True).order_by('nome_completo'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    assinatura_base64 = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ItemConsentimentoProcedimento
        fields = ['procedimento', 'descricao', 'dentistas', 'cro']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, exigir_completo=False, **kwargs):
        self.exigir_completo = exigir_completo
        super().__init__(*args, **kwargs)
        self.fields['procedimento'].required = False
        self.fields['cro'].required = False

    def linha_preenchida(self):
        dados = self.cleaned_data
        if dados.get('DELETE'):
            return False
        return bool(
            (dados.get('procedimento') or '').strip()
            or (dados.get('descricao') or '').strip()
            or dados.get('dentistas')
            or (dados.get('cro') or '').strip()
            or (dados.get('assinatura_base64') or '').strip()
        )

    def clean_assinatura_base64(self):
        bruto = self.cleaned_data.get('assinatura_base64') or ''
        if not self.exigir_completo:
            if not bruto.strip():
                return ''
            return _validar_png_opcional(bruto, False)
        return bruto

    def clean(self):
        dados = super().clean()
        if not self.exigir_completo or not self.linha_preenchida():
            return dados
        if not (dados.get('procedimento') or '').strip():
            self.add_error('procedimento', 'Informe o procedimento.')
        if not dados.get('dentistas'):
            self.add_error('dentistas', 'Marque o dentista responsável.')
        if not (dados.get('cro') or '').strip():
            self.add_error('cro', 'Informe o CRO.')
        try:
            dados['assinatura_base64'] = _validar_png_opcional(
                dados.get('assinatura_base64'), True
            )
        except forms.ValidationError as exc:
            self.add_error('assinatura_base64', exc)
        return dados


class ResponsavelPlanoForm(forms.ModelForm):
    assinatura_base64 = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ResponsavelPlanoTratamento
        fields = ['nome', 'cro']

    def __init__(self, *args, exigir_completo=False, **kwargs):
        self.exigir_completo = exigir_completo
        super().__init__(*args, **kwargs)
        self.fields['nome'].required = False
        self.fields['cro'].required = False

    def linha_preenchida(self):
        dados = self.cleaned_data
        if dados.get('DELETE'):
            return False
        return bool(
            (dados.get('nome') or '').strip()
            or (dados.get('cro') or '').strip()
            or (dados.get('assinatura_base64') or '').strip()
        )

    def clean(self):
        dados = super().clean()
        if not self.exigir_completo or not self.linha_preenchida():
            return dados
        if not (dados.get('nome') or '').strip():
            self.add_error('nome', 'Informe o nome do profissional.')
        if not (dados.get('cro') or '').strip():
            self.add_error('cro', 'Informe o CRO.')
        try:
            dados['assinatura_base64'] = _validar_png_opcional(
                dados.get('assinatura_base64'), True
            )
        except forms.ValidationError as exc:
            self.add_error('assinatura_base64', exc)
        return dados


def montar_itens_formset(exigir_completo=False, dentista=None, **kwargs):
    if dentista is not None and kwargs.get('data') is None:
        kwargs.setdefault('initial', [{'dentistas': [dentista.pk]}])
    factory = inlineformset_factory(
        FichaPlanoTratamento,
        ItemConsentimentoProcedimento,
        form=ItemConsentimentoForm,
        extra=1,
        can_delete=True,
    )
    formset = factory(**kwargs)
    for form in formset.forms:
        form.exigir_completo = exigir_completo
    formset.exigir_completo = exigir_completo
    return formset


def montar_profissionais_formset(exigir_completo=False, **kwargs):
    factory = inlineformset_factory(
        FichaPlanoTratamento,
        ResponsavelPlanoTratamento,
        form=ResponsavelPlanoForm,
        extra=1,
        can_delete=True,
    )
    formset = factory(**kwargs)
    for form in formset.forms:
        form.exigir_completo = exigir_completo
    return formset


class FichaAutorizacaoCustoForm(forms.ModelForm):
    aceitou_declaracao = forms.BooleanField(
        label='li e concordo com a declaração',
        required=False,
    )
    assinatura_paciente_base64 = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = FichaAutorizacaoCusto
        fields = [
            'consulta',
            'nome_completo',
            'data_nascimento',
            'cpf',
            'nome_responsavel',
            'aceitou_declaracao',
        ]
        widgets = {
            'data_nascimento': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
        }

    def __init__(self, *args, exigir_completo=False, coletar_paciente=False, **kwargs):
        self.exigir_completo = exigir_completo
        self.coletar_paciente = coletar_paciente
        super().__init__(*args, **kwargs)
        self.fields['data_nascimento'].input_formats = ['%Y-%m-%d']
        paciente = self.instance.paciente if self.instance.pk else None
        consultas = Consulta.objects.none()
        if paciente is not None:
            consultas = Consulta.objects.filter(paciente=paciente).order_by(
                '-data', '-hora_inicio'
            )
        self.fields['consulta'].queryset = consultas
        self.fields['consulta'].required = False
        self.fields['consulta'].empty_label = 'sem consulta vinculada'

    def clean_assinatura_paciente_base64(self):
        return _validar_png_opcional(
            self.cleaned_data.get('assinatura_paciente_base64'),
            self.coletar_paciente,
        )

    def clean(self):
        dados = super().clean()
        consulta = dados.get('consulta')
        paciente = self.instance.paciente
        if consulta and paciente and consulta.paciente_id != paciente.pk:
            self.add_error('consulta', 'A consulta precisa ser deste paciente.')
        if eh_menor_de_idade(dados.get('data_nascimento')) and not (
            dados.get('nome_responsavel') or ''
        ).strip():
            self.add_error(
                'nome_responsavel',
                'Informe o responsável legal (paciente menor de 18 anos).',
            )
        if not self.exigir_completo:
            return dados
        if not dados.get('aceitou_declaracao'):
            self.add_error(
                'aceitou_declaracao',
                'É preciso concordar com a declaração para concluir.',
            )
        return dados


class ItemAutorizacaoCustoForm(forms.ModelForm):
    class Meta:
        model = ItemAutorizacaoCusto
        fields = ['tipo', 'descricao', 'quantidade', 'valor']
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'quantidade': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, exigir_completo=False, **kwargs):
        self.exigir_completo = exigir_completo
        super().__init__(*args, **kwargs)
        self.fields['tipo'].required = False
        self.fields['valor'].required = False
        self.fields['quantidade'].required = False

    def linha_preenchida(self):
        dados = self.cleaned_data
        if dados.get('DELETE'):
            return False
        return bool(
            (dados.get('tipo') or '').strip()
            or (dados.get('descricao') or '').strip()
            or dados.get('valor') is not None
        )

    def clean(self):
        dados = super().clean()
        if not self.exigir_completo or not self.linha_preenchida():
            return dados
        tipo = dados.get('tipo') or ''
        if not tipo:
            self.add_error('tipo', 'Escolha o tipo do item.')
        if tipo in TIPOS_QUE_EXIGEM_DESCRICAO and not (
            dados.get('descricao') or ''
        ).strip():
            self.add_error('descricao', 'Descreva o item.')
        if dados.get('valor') is None:
            self.add_error(
                'valor',
                'Informe o valor a cobrar (use 0,00 se não houver).',
            )
        quantidade = dados.get('quantidade')
        if not quantidade:
            dados['quantidade'] = 1
        return dados


def montar_itens_autorizacao_formset(exigir_completo=False, **kwargs):
    factory = inlineformset_factory(
        FichaAutorizacaoCusto,
        ItemAutorizacaoCusto,
        form=ItemAutorizacaoCustoForm,
        extra=1,
        can_delete=True,
    )
    formset = factory(**kwargs)
    for form in formset.forms:
        form.exigir_completo = exigir_completo
    return formset


