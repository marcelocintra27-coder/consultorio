"""Busca de paciente e aviso de duplicado, iguais no SQLite e no PostgreSQL."""
import re
import unicodedata

from django.db.models import Q

PALAVRAS_IGNORADAS = {'de', 'da', 'do', 'dos', 'das', 'e'}


def normalizar_nome(texto):
    texto = unicodedata.normalize('NFD', texto or '')
    texto = ''.join(
        caractere for caractere in texto
        if unicodedata.category(caractere) != 'Mn'
    )
    texto = texto.casefold()
    texto = re.sub(r'[^0-9a-z]+', ' ', texto)
    return ' '.join(texto.split())


def somente_digitos(texto):
    return re.sub(r'\D', '', texto or '')


def palavras_significativas(texto):
    return {
        palavra for palavra in normalizar_nome(texto).split()
        if palavra not in PALAVRAS_IGNORADAS
    }


def texto_numerico(termo):
    """Dígitos do texto quando ele é só número, com pontuação de CPF ou telefone."""
    termo = (termo or '').strip()
    digitos = somente_digitos(termo)
    if digitos and re.fullmatch(r'[\d\s.\-()/+]+', termo):
        return digitos
    return ''


def texto_para_busca(paciente):
    partes = [
        paciente.nome_busca or normalizar_nome(paciente.nome_completo),
        paciente.cpf_busca or somente_digitos(paciente.cpf),
        paciente.telefone_busca or somente_digitos(paciente.telefone),
        paciente.whatsapp_busca or somente_digitos(paciente.whatsapp),
    ]
    return ' '.join(parte for parte in partes if parte)


def filtrar_pacientes(queryset, termo):
    """Todas as palavras do nome, em qualquer ordem; ou CPF/telefone se for número."""
    termo = (termo or '').strip()
    if not termo:
        return queryset
    digitos = texto_numerico(termo)
    if digitos:
        return queryset.filter(
            Q(cpf_busca__icontains=digitos)
            | Q(telefone_busca__icontains=digitos)
            | Q(whatsapp_busca__icontains=digitos)
        )
    palavras = normalizar_nome(termo).split()
    if not palavras:
        return queryset.none()
    for palavra in palavras:
        queryset = queryset.filter(nome_busca__icontains=palavra)
    return queryset


def possiveis_duplicados(*, nome, nascimento, telefone, whatsapp, cpf):
    """Ativos parecidos. CPF igual, ativo ou não, volta na lista de bloqueio."""
    from .models import Paciente

    cpf_digitos = somente_digitos(cpf)
    bloqueio = []
    if cpf_digitos:
        bloqueio = list(
            Paciente.objects.filter(cpf_busca=cpf_digitos).order_by('nome_completo', 'pk')
        )
    palavras = palavras_significativas(nome)
    ativos = Paciente.objects.filter(ativo=True)
    vistos = {paciente.pk for paciente in bloqueio}
    parecidos = []
    if nascimento and palavras:
        for paciente in ativos.filter(data_nascimento=nascimento).order_by('nome_completo', 'pk'):
            if paciente.pk in vistos:
                continue
            if len(palavras & palavras_significativas(paciente.nome_completo)) >= 2:
                parecidos.append(paciente)
                vistos.add(paciente.pk)
    contatos = {somente_digitos(telefone), somente_digitos(whatsapp)} - {''}
    if contatos and palavras:
        por_contato = ativos.filter(
            Q(telefone_busca__in=contatos) | Q(whatsapp_busca__in=contatos)
        ).order_by('nome_completo', 'pk')
        for paciente in por_contato:
            if paciente.pk in vistos:
                continue
            if palavras & palavras_significativas(paciente.nome_completo):
                parecidos.append(paciente)
                vistos.add(paciente.pk)
    return bloqueio, parecidos
