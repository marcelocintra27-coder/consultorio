from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from locacao.models import PerfilUsuario


def perfil_do_usuario(user):
    if user is None or not user.is_authenticated:
        return None
    try:
        return user.perfil
    except ObjectDoesNotExist:
        return None


def usuario_e_administrador(user):
    """Retorna somente o administrador de negócio explícito.

    ``is_staff`` apenas dá acesso potencial ao Django Admin; não é um papel
    clínico ou financeiro. Usá-lo aqui faria qualquer conta operacional marcada
    como staff herdar acesso total aos dados do consultório.
    """
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_superuser
    )


def usuario_pode_financeiro(user):
    """Autoriza somente o financeiro administrativo global."""
    if user is None or not user.is_authenticated:
        return False
    return usuario_e_administrador(user)


def usuario_pode_operar_financeiro(user):
    """Autoriza lançamentos operacionais do administrador ou dentista."""
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    return perfil.papel == PerfilUsuario.Papel.DENTISTA


def exige_financeiro(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not usuario_pode_financeiro(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return inner


def exige_operacao_financeira(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not usuario_pode_operar_financeiro(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return inner


def usuario_pode_acessar_consulta(user, consulta):
    """Restringe agenda de dentista/auxiliar ao dentista vinculado."""
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    if perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return True
    return bool(
        perfil.papel in {PerfilUsuario.Papel.DENTISTA, PerfilUsuario.Papel.AUXILIAR}
        and perfil.dentista_id
        and consulta.dentista_id == perfil.dentista_id
    )


def consultas_visiveis_para_usuario(user, queryset):
    """Aplica o escopo de agenda aprovado sem expor consultas alheias."""
    if usuario_e_administrador(user):
        return queryset
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return queryset.none()
    if perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return queryset
    if (
        perfil.papel in {PerfilUsuario.Papel.DENTISTA, PerfilUsuario.Papel.AUXILIAR}
        and perfil.dentista_id
    ):
        return queryset.filter(dentista_id=perfil.dentista_id)
    return queryset.none()


def usuario_pode_agendar_consulta(user):
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    return bool(
        perfil
        and perfil.papel in {
            PerfilUsuario.Papel.DENTISTA,
            PerfilUsuario.Papel.SECRETARIA,
        }
    )


def usuario_pode_gerenciar_agenda(user, consulta=None):
    """Autoriza status de consulta a administrador, dentista ou secretária.

    A secretária participa do fluxo operacional de agenda; o auxiliar não deve
    alterar o status de atendimentos de terceiros.
    """
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    permitido = bool(
        perfil
        and perfil.papel in {
            PerfilUsuario.Papel.DENTISTA,
            PerfilUsuario.Papel.SECRETARIA,
        }
    )
    if not permitido:
        return False
    if consulta is None or perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return True
    return usuario_pode_acessar_consulta(user, consulta)


def status_consulta_permitidos(user, consulta):
    """Retorna as transições administrativas permitidas para a consulta.

    A confirmação e a chegada são operações de agenda. A conclusão clínica
    exige dentista vinculado ou administrador e só pode ocorrer após a chegada
    registrada. Status finais não são reabertos neste fluxo.
    """
    if not usuario_pode_gerenciar_agenda(user, consulta):
        return set()

    status = consulta.Status
    transicoes = {
        status.AGENDADA: {
            status.CONFIRMADA,
            status.PRESENTE,
            status.CANCELADA,
            status.FALTOU,
        },
        status.CONFIRMADA: {
            status.AGENDADA,
            status.PRESENTE,
            status.CANCELADA,
            status.FALTOU,
        },
        status.PRESENTE: {
            status.CANCELADA,
            status.FALTOU,
        },
    }
    permitidos = transicoes.get(consulta.status, set())

    perfil = perfil_do_usuario(user)
    pode_concluir = usuario_e_administrador(user) or bool(
        perfil and perfil.papel == PerfilUsuario.Papel.DENTISTA
    )
    if consulta.status == status.PRESENTE and pode_concluir:
        permitidos = permitidos | {status.REALIZADA}
    return permitidos


def usuario_pode_alterar_status_consulta(user, consulta, novo_status):
    return novo_status in status_consulta_permitidos(user, consulta)


def dentista_do_usuario(user):
    perfil = perfil_do_usuario(user)
    if perfil is None or perfil.papel != PerfilUsuario.Papel.DENTISTA:
        return None
    return perfil.dentista


def usuario_pode_lancar(user, consulta):
    if not usuario_pode_operar_financeiro(user):
        return False
    if usuario_e_administrador(user):
        return True
    if consulta.dentista_id is None:
        return False
    dentista = dentista_do_usuario(user)
    return dentista is not None and dentista.pk == consulta.dentista_id


def usuario_pode_complementar_dentista(user, consulta):
    if not consulta.eh_legado:
        return False
    return usuario_pode_financeiro(user)


def usuario_pode_editar_catalogo(user, dentista):
    if not usuario_pode_financeiro(user):
        return False
    if usuario_e_administrador(user):
        return True
    dentista_user = dentista_do_usuario(user)
    return dentista_user is not None and dentista_user.pk == dentista.pk


def usuario_pode_acessar_cadastro_paciente(user, paciente):
    """Aplica o menor privilégio aos dados cadastrais de pacientes."""
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    if perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return True
    if (
        perfil.papel not in {PerfilUsuario.Papel.DENTISTA, PerfilUsuario.Papel.AUXILIAR}
        or not perfil.dentista_id
    ):
        return False
    from core.models import Consulta

    return Consulta.objects.filter(
        paciente=paciente,
        dentista_id=perfil.dentista_id,
    ).exists()


def pacientes_visiveis_para_usuario(user, queryset):
    if usuario_e_administrador(user):
        return queryset
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return queryset.none()
    if perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return queryset
    if (
        perfil.papel in {PerfilUsuario.Papel.DENTISTA, PerfilUsuario.Papel.AUXILIAR}
        and perfil.dentista_id
    ):
        return queryset.filter(consultas__dentista_id=perfil.dentista_id).distinct()
    return queryset.none()


def usuario_pode_cadastrar_paciente(user):
    if user is None or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    return bool(
        perfil
        and perfil.papel in {
            PerfilUsuario.Papel.DENTISTA,
            PerfilUsuario.Papel.SECRETARIA,
        }
    )


def usuario_pode_editar_cadastro_paciente(user, paciente):
    if usuario_e_administrador(user):
        return True
    perfil = perfil_do_usuario(user)
    if perfil is None:
        return False
    if perfil.papel == PerfilUsuario.Papel.SECRETARIA:
        return True
    return bool(
        perfil.papel == PerfilUsuario.Papel.DENTISTA
        and usuario_pode_acessar_cadastro_paciente(user, paciente)
    )


def usuario_pode_acessar_prontuario(user, paciente, consulta=None):
    """Restringe dados clínicos ao administrador ou ao dentista vinculado.

    Não existe vínculo direto entre paciente e dentista. Portanto, para a
    consulta clínica longitudinal, o vínculo é comprovado por uma consulta do
    paciente atribuída ao dentista; quando uma consulta específica é recebida,
    ela própria deve pertencer ao dentista.
    """
    if not user or not user.is_authenticated:
        return False
    if usuario_e_administrador(user):
        return True
    dentista = dentista_do_usuario(user)
    if dentista is None:
        return False
    if consulta is not None:
        return (
            consulta.paciente_id == paciente.pk
            and consulta.dentista_id == dentista.pk
        )
    from core.models import Consulta

    return Consulta.objects.filter(paciente=paciente, dentista=dentista).exists()


def usuario_pode_registrar_prontuario(user, paciente, consulta=None):
    """Somente dentistas vinculados e administradores podem assinar registros."""
    return usuario_pode_acessar_prontuario(user, paciente, consulta)


def usuario_pode_emitir_prescricao(user, paciente, prescricao=None):
    dentista = dentista_do_usuario(user)
    if not dentista or not dentista.ativo:
        return False
    # Exige vínculo real mesmo para superusuário que também seja dentista.
    from .models import Consulta
    if not Consulta.objects.filter(paciente=paciente, dentista=dentista).exists():
        return False
    return prescricao is None or prescricao.dentista_id == dentista.pk


def usuario_pode_digitalizar(user):
    """Acesso ao fluxo de digitalização, sem mudar a matriz dos demais módulos."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if usuario_e_administrador(user):
        return True
    dentista = dentista_do_usuario(user)
    return bool(dentista and dentista.ativo)


def usuario_pode_acessar_digitalizacao(user, paciente):
    if not usuario_pode_digitalizar(user):
        return False
    if usuario_e_administrador(user):
        return True
    return paciente is not None and usuario_pode_acessar_prontuario(user, paciente)
