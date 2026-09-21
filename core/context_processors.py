from django.utils import timezone
from django.urls import reverse

from .permissoes import (
    perfil_do_usuario,
    usuario_e_administrador,
    usuario_pode_digitalizar,
    usuario_pode_financeiro,
)


def _item(request, rotulo, icone, rota):
    atual = getattr(request, 'resolver_match', None)
    return {
        'rotulo': rotulo,
        'icone': icone,
        'url': reverse(rota),
        'ativo': bool(atual and atual.view_name == rota),
    }


def _grupo(titulo, itens):
    return {'titulo': titulo, 'itens': itens}


def admin_local_date(request):
    return {"admin_local_date": timezone.localdate().isoformat()}


def permissoes_usuario(request):
    return {
        'pode_financeiro': usuario_pode_financeiro(request.user),
        'pode_digitalizar': usuario_pode_digitalizar(request.user),
    }


def navegacao_usuario(request):
    """Fornece somente links existentes e compatíveis com o perfil atual."""
    user = request.user
    if not user.is_authenticated:
        return {'menu_lateral': [], 'perfil_navegacao': ''}

    inicio = _item(request, 'Início', 'inicio', 'core:inicio')
    if usuario_e_administrador(user):
        return {
            'perfil_navegacao': 'Administrador',
            'menu_lateral': [
                _grupo('', [inicio]),
                _grupo('Operação', [
                    _item(request, 'Agenda', 'agenda', 'core:listar_consultas'),
                    _item(request, 'Pacientes', 'pacientes', 'core:listar_pacientes'),
                ]),
                _grupo('Financeiro atual', [
                    _item(request, 'Contas a receber', 'pagamentos', 'core:listar_contas_receber'),
                    _item(request, 'Inadimplência', 'pagamentos', 'core:listar_inadimplencia'),
                    _item(request, 'Contas a pagar', 'pagamentos', 'core:listar_contas_pagar'),
                    _item(request, 'Caixa', 'pagamentos', 'core:caixa_diario'),
                    _item(request, 'Conciliação', 'pagamentos', 'core:listar_conciliacoes'),
                    _item(request, 'Formas de pagamento', 'pagamentos', 'core:listar_formas_pagamento_configuraveis'),
                    _item(request, 'Relatórios', 'relatorios', 'core:relatorios_financeiros'),
                    _item(request, 'Fornecedores', 'pagamentos', 'core:listar_fornecedores'),
                    _item(request, 'Pagamentos', 'pagamentos', 'core:listar_pagamentos_consulta'),
                    _item(request, 'Materiais', 'materiais', 'core:listar_materiais_dia'),
                    _item(request, 'Procedimentos', 'procedimentos', 'core:listar_procedimentos'),
                    _item(request, 'Convênios', 'convenios', 'core:listar_convenios'),
                    _item(request, 'Repasses Uniodonto', 'repasses', 'core:listar_repasses_uniodonto'),
                    _item(request, 'Despesas', 'despesas', 'locacao:listar_despesas'),
                    _item(request, 'Dívidas', 'dividas', 'locacao:listar_dividas'),
                    _item(request, 'Acerto mensal', 'acerto', 'locacao:acerto_mensal'),
                ]),
                _grupo('Administração', [
                    _item(request, 'Administração', 'configuracoes', 'core:administracao'),
                ]),
            ],
        }

    perfil = perfil_do_usuario(user)
    if perfil is None:
        return {'menu_lateral': [_grupo('', [inicio])], 'perfil_navegacao': 'Usuário'}

    if perfil.papel == perfil.Papel.SECRETARIA:
        return {
            'perfil_navegacao': 'Secretária',
            'menu_lateral': [
                _grupo('', [inicio]),
                _grupo('Operação', [
                    _item(request, 'Agenda', 'agenda', 'core:listar_consultas'),
                    _item(request, 'Pacientes', 'pacientes', 'core:listar_pacientes'),
                ]),
            ],
        }

    if perfil.papel == perfil.Papel.DENTISTA:
        return {
            'perfil_navegacao': 'Dentista',
            'menu_lateral': [
                _grupo('', [inicio]),
                _grupo('Minha rotina', [
                    _item(request, 'Minha agenda', 'agenda', 'core:listar_consultas'),
                    _item(request, 'Pacientes', 'pacientes', 'core:listar_pacientes'),
                    _item(request, 'Materiais utilizados', 'materiais', 'core:listar_materiais_dia'),
                ]),
            ],
        }

    if perfil.papel == perfil.Papel.AUXILIAR:
        return {
            'perfil_navegacao': 'Auxiliar',
            'menu_lateral': [
                _grupo('', [inicio]),
                _grupo('Consulta', [
                    _item(request, 'Agenda', 'agenda', 'core:listar_consultas'),
                    _item(request, 'Pacientes', 'pacientes', 'core:listar_pacientes'),
                ]),
            ],
        }

    return {'menu_lateral': [_grupo('', [inicio])], 'perfil_navegacao': 'Usuário'}
