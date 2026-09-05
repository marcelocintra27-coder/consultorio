from datetime import datetime

from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Convenio, Paciente, Consulta
from .forms import ConvenioForm, PacienteForm

def inicio(request):
    return render(request, 'core/inicio.html')

def listar_pacientes(request):
    termo = request.GET.get('q', '').strip()
    pacientes = Paciente.objects.filter(ativo=True)
    if termo:
        pacientes = pacientes.filter(nome_completo__icontains=termo)
    pacientes = pacientes.order_by('nome_completo')
    return render(request, 'core/listar_pacientes.html', {'pacientes': pacientes, 'termo': termo})

def cadastrar_paciente(request):
    if request.method == 'POST':
        form = PacienteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('core:listar_pacientes')
    else:
        form = PacienteForm()
    return render(request, 'core/form_paciente.html', {
        'form': form,
        'titulo': 'Cadastrar Paciente',
    })


def editar_paciente(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, ativo=True)
    if request.method == 'POST':
        form = PacienteForm(request.POST, instance=paciente)
        if form.is_valid():
            form.save()
            return redirect('core:listar_pacientes')
    else:
        form = PacienteForm(instance=paciente)
    return render(request, 'core/form_paciente.html', {
        'form': form,
        'titulo': 'Editar Paciente',
    })


def listar_convenios(request):
    termo = request.GET.get('q', '').strip()
    convenios = Convenio.objects.filter(ativo=True)
    if termo:
        convenios = convenios.filter(nome__icontains=termo)
    convenios = convenios.order_by('nome')
    return render(request, 'core/listar_convenios.html', {
        'convenios': convenios,
        'termo': termo,
    })


def cadastrar_convenio(request):
    if request.method == 'POST':
        form = ConvenioForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('core:listar_convenios')
    else:
        form = ConvenioForm()
    return render(request, 'core/form_convenio.html', {
        'form': form,
        'titulo': 'Cadastrar Convênio',
    })


def editar_convenio(request, pk):
    convenio = get_object_or_404(Convenio, pk=pk, ativo=True)
    if request.method == 'POST':
        form = ConvenioForm(request.POST, instance=convenio)
        if form.is_valid():
            form.save()
            return redirect('core:listar_convenios')
    else:
        form = ConvenioForm(instance=convenio)
    return render(request, 'core/form_convenio.html', {
        'form': form,
        'titulo': 'Editar Convênio',
    })


def listar_consultas(request):
    data_str = request.GET.get('data', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = (
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio')
        .order_by('hora_inicio')
    )
    return render(request, 'core/listar_consultas.html', {
        'consultas': consultas,
        'data': data,
    })


@require_POST
def marcar_consulta_paga(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    acao = request.POST.get('acao')
    if acao == 'marcar':
        consulta.pago = True
        consulta.save(update_fields=['pago'])
    elif acao == 'desmarcar':
        consulta.pago = False
        consulta.save(update_fields=['pago'])
    return redirect(
        f"{reverse('core:listar_consultas')}?data={consulta.data.isoformat()}"
    )


def listar_pagamentos_consulta(request):
    data_str = request.GET.get('data', '').strip()
    hoje = timezone.localdate()
    if data_str:
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data = hoje
    else:
        data = hoje
    consultas = (
        Consulta.objects.filter(data=data)
        .select_related('paciente__convenio')
        .order_by('hora_inicio')
    )
    return render(request, 'core/listar_pagamentos_consulta.html', {
        'consultas': consultas,
        'data': data,
        'formas_pagamento': Consulta.FormaPagamento.choices,
    })


@require_POST
def salvar_forma_pagamento(request, pk):
    consulta = get_object_or_404(Consulta, pk=pk)
    forma = (request.POST.get('forma_pagamento') or '').strip()
    opcoes = {choice[0] for choice in Consulta.FormaPagamento.choices}
    if forma == '' or forma in opcoes:
        consulta.forma_pagamento = forma
        consulta.save(update_fields=['forma_pagamento'])
    return redirect(
        f"{reverse('core:listar_pagamentos_consulta')}?data={consulta.data.isoformat()}"
    )
