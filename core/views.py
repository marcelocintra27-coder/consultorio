from datetime import datetime

from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone

from .models import Paciente, Consulta
from .forms import PacienteForm

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
        .select_related('paciente')
        .order_by('hora_inicio')
    )
    return render(request, 'core/listar_consultas.html', {
        'consultas': consultas,
        'data': data,
    })
