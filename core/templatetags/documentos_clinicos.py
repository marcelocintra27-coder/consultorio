from django import template
from core.integridade_documentos import contexto_integridade

register = template.Library()


@register.inclusion_tag('core/includes/integridade_documento.html')
def integridade_documento(documento):
    return contexto_integridade(documento)


@register.inclusion_tag('core/includes/evolucoes_legadas.html')
def evolucoes_legadas(paciente):
    # Chamado somente na ficha clínica já autorizada pelo backend.
    return {'legados': paciente.evolucoes.order_by('data', 'pk')}
