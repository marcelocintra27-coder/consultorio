from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.permissoes import usuario_e_administrador, usuario_pode_acessar_consulta
from .models import Exame, EventoExame
from .permissoes import pode_acessar, pode_corrigir
from . import antivirus, storage


def evento(user, acao, resultado='ok', exame=None, justificativa=''):
    return EventoExame.objects.create(usuario=user if user.is_authenticated else None, acao=acao,
                                     resultado=resultado, exame=exame, justificativa=justificativa)


def autorizar(user, paciente):
    if not pode_acessar(user, paciente):
        evento(user, 'acesso_negado', 'negado')
        raise PermissionDenied


def incluir(user, paciente, dados, anterior=None):
    autorizar(user, paciente)
    consulta = dados.get('consulta')
    if consulta and (consulta.paciente_id != paciente.pk or not usuario_pode_acessar_consulta(user, consulta)):
        raise PermissionDenied
    if anterior and (anterior.paciente_id != paciente.pk or not pode_corrigir(user, anterior)):
        raise PermissionDenied
    upload = dados['arquivo']
    tipo = storage.validar_arquivo(upload)
    estado = antivirus.inspecionar(upload)
    exame = Exame(paciente=paciente, criado_por=user, categoria=dados['categoria'], titulo=dados['titulo'],
                  data_exame=dados.get('data_exame'), consulta=consulta, observacao=dados.get('observacao', ''),
                  tamanho=upload.size, tipo=tipo, anterior=anterior, justificativa=dados.get('justificativa', ''))
    gravado = False
    try:
        # Durable evita que um chamador faça rollback posterior e deixe arquivo órfão.
        with transaction.atomic(durable=True):
            if anterior:
                anterior = Exame.objects.select_for_update().get(pk=anterior.pk)
                if anterior.invalidado or Exame.objects.filter(anterior=anterior).exists():
                    raise ValidationError('Registro já invalidado ou substituído. Atualize a página.')
            exame.sha256 = storage.gravar(upload, exame.chave)
            gravado = True
            exame.save(force_insert=True)
            evento(user, 'incluido', exame=exame)
            evento(user, estado, resultado=estado, exame=exame)
            if anterior:
                evento(user, 'substituido', exame=anterior, justificativa=exame.justificativa)
        return exame
    except Exception:
        if gravado:
            storage.caminho(exame.chave).unlink(missing_ok=True)
        raise


def invalidar(user, exame, justificativa):
    if not pode_corrigir(user, exame):
        evento(user, 'acesso_negado', 'negado')
        raise PermissionDenied
    if not justificativa.strip():
        raise ValidationError('Justificativa obrigatória.')
    with transaction.atomic():
        exame = Exame.objects.select_for_update().get(pk=exame.pk)
        if exame.invalidado:
            raise ValidationError('Registro já invalidado ou substituído.')
        evento(user, 'invalidado', exame=exame, justificativa=justificativa)


def reinspecionar(user, exame):
    if not pode_corrigir(user, exame):
        evento(user, 'acesso_negado', 'negado')
        raise PermissionDenied
    # A inspeção não escreve no arquivo nem aceita liberação manual.
    with transaction.atomic():
        exame = Exame.objects.select_for_update().get(pk=exame.pk)
        if exame.seguranca != 'quarentena':
            raise ValidationError('Somente arquivos em quarentena podem ser reinspecionados.')
        try:
            with storage.abrir_verificado(exame) as arquivo:
                estado = antivirus.inspecionar(arquivo)
        except ValidationError:
            estado = 'integridade_falhou'
        evento(user, estado, resultado=estado, exame=exame)
    return estado
