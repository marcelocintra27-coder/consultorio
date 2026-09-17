"""Normalização e sugestões para conciliação, sem integração bancária direta."""

import csv
import hashlib
import io
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    BaixaContaPagar,
    ImportacaoExtrato,
    ItemConciliacao,
    LancamentoExtrato,
    MovimentoCaixa,
    RecebimentoPaciente,
    RepasseUniodonto,
    AuditoriaConciliacao,
)


def hash_arquivo_extrato(conteudo):
    if isinstance(conteudo, str):
        conteudo = conteudo.encode('utf-8')
    return hashlib.sha256(conteudo).hexdigest()


def _decimal_extrato(valor):
    texto = str(valor or '').strip().replace('R$', '').replace(' ', '')
    if texto.count(',') == 1 and texto.count('.') >= 1:
        texto = texto.replace('.', '').replace(',', '.')
    else:
        texto = texto.replace(',', '.')
    try:
        valor_decimal = Decimal(texto)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError('Valor inválido no extrato.') from exc
    if valor_decimal == 0:
        raise ValidationError('Lançamento de extrato não pode ter valor zero.')
    return abs(valor_decimal).quantize(Decimal('0.01'))


def normalizar_csv_extrato(conteudo):
    """Lê CSV já validado pelo chamador e devolve registros normalizados.

    A importação de arquivo ainda não possui upload: esta função prepara o
    serviço para uma etapa posterior que tenha política de retenção aprovada.
    """
    leitor = csv.DictReader(io.StringIO(conteudo))
    registros = []
    for indice, linha in enumerate(leitor, start=1):
        dados = {str(chave or '').strip().lower(): valor for chave, valor in linha.items()}
        data_bruta = dados.get('data') or dados.get('date')
        try:
            data = datetime.strptime(data_bruta, '%Y-%m-%d').date()
        except (TypeError, ValueError) as exc:
            raise ValidationError('CSV deve informar data no formato AAAA-MM-DD.') from exc
        valor_bruto = dados.get('valor') or dados.get('amount')
        valor = _decimal_extrato(valor_bruto)
        natureza = dados.get('natureza') or dados.get('tipo')
        if not natureza:
            natureza = 'entrada' if not str(valor_bruto).strip().startswith('-') else 'saida'
        natureza = natureza.strip().lower()
        if natureza not in {LancamentoExtrato.Natureza.ENTRADA, LancamentoExtrato.Natureza.SAIDA}:
            raise ValidationError('CSV deve informar natureza como entrada ou saída.')
        registros.append({
            'indice_origem': indice,
            'referencia_externa': (dados.get('referencia') or dados.get('id') or '').strip(),
            'data': data,
            'descricao': (dados.get('descricao') or dados.get('description') or '').strip() or 'Sem descrição',
            'natureza': natureza,
            'valor': valor,
            'saldo_informado': None,
        })
    return registros


def normalizar_ofx_extrato(conteudo):
    """Normaliza os campos essenciais de OFX clássico, sem persistir o arquivo."""
    registros = []
    blocos = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', conteudo, flags=re.IGNORECASE | re.DOTALL)
    for indice, bloco in enumerate(blocos, start=1):
        def campo(nome):
            resultado = re.search(rf'<{nome}>([^<\r\n]+)', bloco, re.IGNORECASE)
            return resultado.group(1).strip() if resultado else ''

        data_bruta = campo('DTPOSTED')[:8]
        try:
            data = datetime.strptime(data_bruta, '%Y%m%d').date()
        except ValueError as exc:
            raise ValidationError('OFX contém data de lançamento inválida.') from exc
        valor_bruto = campo('TRNAMT')
        valor = _decimal_extrato(valor_bruto)
        registros.append({
            'indice_origem': indice,
            'referencia_externa': campo('FITID'),
            'data': data,
            'descricao': campo('MEMO') or campo('NAME') or 'Sem descrição',
            'natureza': (
                LancamentoExtrato.Natureza.SAIDA
                if valor_bruto.strip().startswith('-')
                else LancamentoExtrato.Natureza.ENTRADA
            ),
            'valor': valor,
            'saldo_informado': None,
        })
    if not registros:
        raise ValidationError('OFX não contém lançamentos reconhecíveis.')
    return registros


@transaction.atomic
def registrar_importacao_arquivo(*, instituicao, conta_referencia, formato, conteudo, usuario):
    """Persiste um CSV/OFX normalizado e bloqueia a importação do mesmo arquivo."""
    if formato == ImportacaoExtrato.Formato.CSV:
        registros = normalizar_csv_extrato(conteudo)
    elif formato == ImportacaoExtrato.Formato.OFX:
        registros = normalizar_ofx_extrato(conteudo)
    else:
        raise ValidationError('Formato de importação inválido.')
    assinatura = hash_arquivo_extrato(conteudo)
    if ImportacaoExtrato.objects.select_for_update().filter(hash_arquivo=assinatura).exists():
        raise ValidationError('Este arquivo já foi importado.')
    importacao = ImportacaoExtrato(
        instituicao=instituicao,
        conta_referencia=conta_referencia,
        formato=formato,
        hash_arquivo=assinatura,
        periodo_inicial=min(registro['data'] for registro in registros),
        periodo_final=max(registro['data'] for registro in registros),
        criado_por=usuario,
    )
    importacao.full_clean()
    importacao.save()
    LancamentoExtrato.objects.bulk_create([
        LancamentoExtrato(importacao=importacao, **registro)
        for registro in registros
    ])
    AuditoriaConciliacao.objects.create(
        importacao=importacao,
        usuario=usuario,
        acao='arquivo_importado',
        descricao='Arquivo de extrato normalizado e importado.',
        dados={'formato': formato, 'quantidade_lancamentos': len(registros)},
    )
    return importacao


def valor_origem(item):
    if isinstance(item, RepasseUniodonto):
        return item.liquido_recebido
    return item.valor


def data_origem(item):
    if isinstance(item, RecebimentoPaciente):
        return item.recebido_em.date()
    if isinstance(item, BaixaContaPagar):
        return item.baixado_em.date()
    if isinstance(item, MovimentoCaixa):
        return item.criado_em.date()
    return item.competencia


def sugerir_origens(lancamento, tolerancia_dias=3):
    """Retorna sugestões; nunca confirma conciliação automaticamente."""
    inicio = lancamento.data - timedelta(days=tolerancia_dias)
    fim = lancamento.data + timedelta(days=tolerancia_dias)
    valor = lancamento.valor
    sugestoes = []
    if lancamento.natureza == LancamentoExtrato.Natureza.ENTRADA:
        fontes = [
            ('recebimento', RecebimentoPaciente.objects.filter(
                tipo=RecebimentoPaciente.Tipo.RECEBIMENTO,
                valor=valor, recebido_em__date__range=(inicio, fim),
            )),
            ('repasse_uniodonto', RepasseUniodonto.objects.filter(liquido_recebido=valor)),
        ]
    else:
        fontes = [
            ('recebimento', RecebimentoPaciente.objects.filter(
                tipo=RecebimentoPaciente.Tipo.ESTORNO,
                valor=valor, recebido_em__date__range=(inicio, fim),
            )),
            ('baixa', BaixaContaPagar.objects.filter(
                valor=valor, baixado_em__date__range=(inicio, fim),
            )),
            ('movimento_caixa', MovimentoCaixa.objects.filter(
                valor=valor, recebido__isnull=True, baixa__isnull=True,
                criado_em__date__range=(inicio, fim),
            )),
        ]
    for tipo, queryset in fontes:
        for origem in queryset:
            filtro = {tipo: origem, 'ativo': True}
            if not ItemConciliacao.objects.filter(**filtro).exists():
                sugestoes.append({'tipo': tipo, 'origem': origem, 'valor': valor_origem(origem)})
    return sugestoes
