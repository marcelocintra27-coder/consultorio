from core.permissoes import usuario_e_administrador, usuario_pode_acessar_prontuario, dentista_do_usuario


def pode_acessar(user, paciente):
    if not user.is_authenticated or not user.is_active:
        return False
    if usuario_e_administrador(user):
        return True
    dentista = dentista_do_usuario(user)
    return bool(dentista and dentista.ativo and usuario_pode_acessar_prontuario(user, paciente))


def pode_corrigir(user, exame):
    return pode_acessar(user, exame.paciente) and (usuario_e_administrador(user) or exame.criado_por_id == user.pk)
