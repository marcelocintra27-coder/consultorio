from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DentistaForm, DespesaForm
from .models import Dentista, Despesa, PagamentoPar
from .services import calcular_acerto_mensal, mes_anterior, mes_seguinte


def listar_dentistas(request):
    termo = request.GET.get('q', '').strip()
    dentistas = Dentista.objects.filter(ativo=True).select_related('sala')
    if termo:
        dentistas = dentistas.filter(nome_completo__icontains=termo)
    dentistas = dentistas.order_by('nome_completo')
    return render(request, 'locacao/listar_dentistas.html', {
        'dentistas': dentistas,
        'termo': termo,
    })


def cadastrar_dentista(request):
    if request.method == 'POST':
        form = DentistaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('locacao:listar_dentistas')
    else:
        form = DentistaForm()
    return render(request, 'locacao/form_dentista.html', {
        'form': form,
        'titulo': 'Cadastrar Dentista',
    })


def editar_dentista(request, pk):
    dentista = get_object_or_404(Dentista, pk=pk, ativo=True)
    if request.method == 'POST':
        form = DentistaForm(request.POST, instance=dentista)
        if form.is_valid():
            form.save()
            return redirect('locacao:listar_dentistas')
    else:
        form = DentistaForm(instance=dentista)
    return render(request, 'locacao/form_dentista.html', {
        'form': form,
        'titulo': 'Editar Dentista',
    })


def listar_despesas(request):
    termo = request.GET.get('q', '').strip()
    mes = _parse_mes(request.GET.get('mes', '').strip())
    despesas = (
        Despesa.objects.filter(competencia=mes)
        .select_related('pago_por')
        .order_by('descricao')
    )
    if termo:
        despesas = despesas.filter(descricao__icontains=termo)
    return render(request, 'locacao/listar_despesas.html', {
        'despesas': despesas,
        'termo': termo,
        'mes_input': mes.strftime('%Y-%m'),
    })


def cadastrar_despesa(request):
    if request.method == 'POST':
        form = DespesaForm(request.POST)
        if form.is_valid():
            despesa = form.save()
            return redirect(
                f"{reverse('locacao:listar_despesas')}"
                f"?mes={despesa.competencia.strftime('%Y-%m')}"
            )
    else:
        form = DespesaForm()
    return render(request, 'locacao/form_despesa.html', {
        'form': form,
        'titulo': 'Cadastrar Despesa',
    })


def editar_despesa(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method == 'POST':
        form = DespesaForm(request.POST, instance=despesa)
        if form.is_valid():
            despesa = form.save()
            return redirect(
                f"{reverse('locacao:listar_despesas')}"
                f"?mes={despesa.competencia.strftime('%Y-%m')}"
            )
    else:
        form = DespesaForm(instance=despesa)
    return render(request, 'locacao/form_despesa.html', {
        'form': form,
        'titulo': 'Editar Despesa',
    })


def _parse_mes(mes_str):
    if mes_str:
        try:
            ano, mes_num = mes_str.split('-')
            return date(int(ano), int(mes_num), 1)
        except (TypeError, ValueError):
            pass
    hoje = timezone.localdate()
    return date(hoje.year, hoje.month, 1)


@staff_member_required
def acerto_mensal(request):
    mes = _parse_mes(request.GET.get('mes', '').strip())
    resultado = calcular_acerto_mensal(mes)
    return render(request, 'locacao/acerto_mensal.html', {
        **resultado,
        'mes_input': mes.strftime('%Y-%m'),
        'mes_anterior': mes_anterior(mes).strftime('%Y-%m'),
        'mes_seguinte': mes_seguinte(mes).strftime('%Y-%m'),
    })


@staff_member_required
@require_POST
def marcar_pagamento(request):
    mes = _parse_mes(request.POST.get('mes', '').strip())
    try:
        devedor_id = int(request.POST.get('devedor_id', ''))
        credor_id = int(request.POST.get('credor_id', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Requisição inválida.')
        return redirect(f"{reverse('locacao:acerto_mensal')}?mes={mes.strftime('%Y-%m')}")

    acao = request.POST.get('acao')
    resultado = calcular_acerto_mensal(mes)
    par = next(
        (
            p for p in resultado['pares']
            if p['devedor'].id == devedor_id and p['credor'].id == credor_id
        ),
        None,
    )

    if par is None:
        messages.error(request, 'Esse par não tem mais saldo pendente nesse mês.')
    elif acao == 'marcar':
        pagamento, _ = PagamentoPar.objects.get_or_create(
            de_dentista_id=devedor_id,
            para_dentista_id=credor_id,
            competencia=mes,
        )
        pagamento.valor = par['valor_calculado']
        pagamento.pago = True
        pagamento.full_clean()
        pagamento.save()
        messages.success(
            request,
            f"Pagamento de {par['devedor']} para {par['credor']} marcado como pago.",
        )
    elif acao == 'desmarcar' and par['pagamento'] is not None:
        par['pagamento'].pago = False
        par['pagamento'].save(update_fields=['pago'])
        messages.success(
            request,
            f"Pagamento de {par['devedor']} para {par['credor']} voltou para pendente.",
        )

    return redirect(f"{reverse('locacao:acerto_mensal')}?mes={mes.strftime('%Y-%m')}")
