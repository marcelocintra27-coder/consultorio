"""Leitura da integridade com os serializadores históricos, sem reparar hashes."""
import json
from dataclasses import dataclass

from django.db.models import Q
from django.urls import reverse


def tipos_documentos():
    from . import models as m
    return {
        'evolucao': m.RegistroEvolucaoClinica,
        'anamnese': m.FichaCadastroAnamnese,
        'plano_tratamento': m.FichaPlanoTratamento,
        'autorizacao_custo': m.FichaAutorizacaoCusto,
        'retificacao': m.RetificacaoDocumento,
        'prescricao': m.Prescricao,
    }


def tipo_documento(documento):
    return next((tipo for tipo, modelo in tipos_documentos().items() if isinstance(documento, modelo)), None)


def raiz_documento(obj):
    return obj.ficha if hasattr(obj, 'ficha_id') else obj


def assinaturas_documento(documento):
    from .models import AssinaturaEletronica
    documento = raiz_documento(documento)
    tipo = tipo_documento(documento)
    filtro = Q(tipo_documento=tipo, documento_id=documento.pk)
    if tipo == 'plano_tratamento':
        filtro |= Q(tipo_documento='plano_procedimento', documento_id__in=documento.itens.values('pk'))
        filtro |= Q(tipo_documento='plano_profissional', documento_id__in=documento.profissionais.values('pk'))
    return AssinaturaEletronica.objects.filter(filtro).order_by('assinado_em', 'pk')


def documento_bloqueado(obj):
    from .models import AssinaturaEletronica, Evolucao, RetificacaoDocumento
    if not obj.pk:
        return False
    raiz = raiz_documento(obj)
    if tipo_documento(raiz) == 'prescricao' and raiz.status == 'assinada':
        return True
    if isinstance(obj, (AssinaturaEletronica, Evolucao, RetificacaoDocumento)):
        return type(obj).objects.filter(pk=obj.pk).exists()
    return assinaturas_documento(raiz_documento(obj)).exists()


def texto_documento(documento):
    from .prescricao_conteudo import texto_para_hash_prescricao
    from .anamnese import texto_para_hash
    from .autorizacao import texto_para_hash_autorizacao
    from .evolucao import texto_para_hash_evolucao
    from .plano import texto_para_hash_plano
    serializadores = {
        'anamnese': texto_para_hash,
        'evolucao': texto_para_hash_evolucao,
        'plano_tratamento': texto_para_hash_plano,
        'autorizacao_custo': texto_para_hash_autorizacao,
        'retificacao': texto_para_hash_retificacao,
        'prescricao': texto_para_hash_prescricao,
    }
    documento = raiz_documento(documento)
    return serializadores[tipo_documento(documento)](documento)


def texto_para_hash_retificacao(registro):
    return json.dumps({
        'original_tipo': registro.original_tipo,
        'original_id': registro.original.pk,
        'autor_id': registro.autor_id,
        'nome_profissional': registro.nome_profissional,
        'cro': registro.cro,
        'criado_em': registro.criado_em.isoformat(),
        'justificativa': registro.justificativa,
        'conteudo': registro.conteudo,
    }, ensure_ascii=False, sort_keys=True)


def documento_da_assinatura(assinatura):
    from .models import ItemConsentimentoProcedimento, ResponsavelPlanoTratamento
    modelo = tipos_documentos().get(assinatura.tipo_documento)
    if assinatura.tipo_documento == 'plano_procedimento':
        modelo = ItemConsentimentoProcedimento
    elif assinatura.tipo_documento == 'plano_profissional':
        modelo = ResponsavelPlanoTratamento
    obj = modelo.objects.filter(pk=assinatura.documento_id).first() if modelo else None
    return raiz_documento(obj) if obj else None


@dataclass(frozen=True)
class Integridade:
    ocorrencias: tuple

    @property
    def integra(self):
        return not self.ocorrencias


def verificar_integridade(documento, *, exigir_completude=True):
    from .assinatura import hash_sha256
    documento = raiz_documento(documento)
    tipo = tipo_documento(documento)
    assinaturas = list(assinaturas_documento(documento))
    ocorrencias = []
    if not assinaturas and exigir_completude:
        ocorrencias.append('Assinatura e hashes esperados não encontrados.')
    esperado = hash_sha256(texto_documento(documento).encode('utf-8'))
    for assinatura in assinaturas:
        prefixo = f'Assinatura {assinatura.pk}: '
        if assinatura.paciente_id != documento.paciente_id:
            ocorrencias.append(prefixo + 'vínculo com paciente divergente.')
        if not assinatura.hash_conteudo:
            ocorrencias.append(prefixo + 'hash do conteúdo ausente.')
        elif assinatura.hash_conteudo != esperado:
            ocorrencias.append(prefixo + 'conteúdo divergente do hash registrado.')
        if not assinatura.hash_imagem:
            ocorrencias.append(prefixo + 'hash da imagem ausente.')
        try:
            if not assinatura.imagem:
                raise FileNotFoundError
            with assinatura.imagem.open('rb') as arquivo:
                import hashlib
                digest = hashlib.sha256()
                for bloco in iter(lambda: arquivo.read(65536), b''):
                    digest.update(bloco)
            if assinatura.hash_imagem and digest.hexdigest() != assinatura.hash_imagem:
                ocorrencias.append(prefixo + 'imagem divergente do hash registrado.')
        except (OSError, ValueError):
            ocorrencias.append(prefixo + 'arquivo de assinatura indisponível.')
    if not exigir_completude:
        return Integridade(tuple(ocorrencias))
    # Detecta também assinaturas faltantes em documentos com várias assinaturas.
    presentes = {(a.tipo_documento, a.documento_id, a.papel) for a in assinaturas}
    if tipo in ('evolucao', 'retificacao', 'prescricao'):
        if (tipo, documento.pk, 'dentista') not in presentes:
            ocorrencias.append('Assinatura profissional esperada não encontrada.')
    if tipo == 'prescricao':
        profissionais = [a for a in assinaturas if a.papel == 'dentista']
        if len(assinaturas) != 1 or len(profissionais) != 1:
            ocorrencias.append('A prescrição exige uma única assinatura profissional.')
        elif profissionais[0].nome_assinante != documento.nome_profissional:
            ocorrencias.append('Autoria da assinatura divergente da prescrição.')
    if tipo in ('anamnese', 'plano_tratamento', 'autorizacao_custo'):
        if not any((tipo, documento.pk, papel) in presentes for papel in ('paciente', 'responsavel')):
            ocorrencias.append('Assinatura do paciente/responsável esperada não encontrada.')
    if tipo == 'anamnese' and documento.status == 'concluida':
        if (tipo, documento.pk, 'dentista') not in presentes:
            ocorrencias.append('Assinatura do dentista esperada não encontrada.')
    if tipo == 'plano_tratamento':
        for item in documento.itens.all():
            if not any(('plano_procedimento', item.pk, papel) in presentes for papel in ('paciente', 'responsavel')):
                ocorrencias.append(f'Assinatura do item {item.pk} ausente.')
        for prof in documento.profissionais.all():
            if ('plano_profissional', prof.pk, 'dentista') not in presentes:
                ocorrencias.append(f'Assinatura do profissional {prof.pk} ausente.')
    return Integridade(tuple(ocorrencias))


def url_documento(documento):
    tipo = tipo_documento(documento)
    if tipo == 'prescricao':
        return reverse('core:ver_prescricao', args=[documento.paciente_id, documento.pk])
    if tipo == 'evolucao':
        return reverse('core:ficha_evolucao_clinica', args=[documento.paciente_id])
    nomes = {'anamnese': 'ver_ficha_anamnese', 'plano_tratamento': 'ver_ficha_plano', 'autorizacao_custo': 'ver_ficha_autorizacao'}
    return reverse('core:' + nomes[tipo], args=[documento.paciente_id, documento.pk])


def contexto_integridade(documento):
    resultado = verificar_integridade(documento)
    retificacoes = list(documento.retificacoes.select_related('autor').order_by('criado_em', 'pk'))
    for registro in retificacoes:
        registro.integridade = verificar_integridade(registro)
        registro.assinatura = assinaturas_documento(registro).first()
    return {
        'integridade': resultado, 'retificacoes': retificacoes,
        'url_retificar': reverse('core:retificar_documento', args=[tipo_documento(documento), documento.pk]),
    }
