/* Tela de agendar/remarcar: mostra o que já ocupa o dia e preenche a hora fim. */
(function () {
    'use strict';
    var form = document.getElementById('form-consulta');
    if (!form) { return; }

    var caixa = document.getElementById('horarios-ocupados');
    var campoDentista = form.querySelector('[name="dentista"]');
    var campoData = form.querySelector('[name="data"]');
    var campoInicio = form.querySelector('[name="hora_inicio"]');
    var campoFim = form.querySelector('[name="hora_fim"]');

    /* ---------- Horários já ocupados ---------- */
    var pedidoAtual = 0;
    function atualizarHorarios() {
        if (!caixa || !campoData) { return; }
        var parametros = new URLSearchParams();
        parametros.set('data', campoData.value || '');
        if (caixa.dataset.consulta) {
            parametros.set('consulta', caixa.dataset.consulta);
        } else {
            parametros.set('dentista', campoDentista ? (campoDentista.value || '') : '');
        }
        var numero = ++pedidoAtual;
        fetch(caixa.dataset.url + '?' + parametros.toString(), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resposta) {
            if (!resposta.ok) { throw new Error(resposta.status); }
            return resposta.text();
        }).then(function (html) {
            if (numero === pedidoAtual) { caixa.innerHTML = html; }
        }).catch(function () {
            if (numero === pedidoAtual) {
                caixa.innerHTML = '<p class="resumo">Não foi possível mostrar os horários agora. ' +
                    'O sistema ainda confere o horário ao salvar.</p>';
            }
        });
    }
    if (campoDentista) { campoDentista.addEventListener('change', atualizarHorarios); }
    if (campoData) { campoData.addEventListener('change', atualizarHorarios); }
    atualizarHorarios();

    /* ---------- Hora fim automática ---------- */
    function paraMinutos(valor) {
        var partes = /^(\d{1,2}):(\d{2})/.exec(valor || '');
        return partes ? Number(partes[1]) * 60 + Number(partes[2]) : null;
    }
    function paraHora(minutos) {
        var h = Math.floor(minutos / 60), m = minutos % 60;
        return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    }
    if (campoInicio && campoFim) {
        var duracao = 30;
        var inicioAtual = paraMinutos(campoInicio.value);
        var fimAtual = paraMinutos(campoFim.value);
        if (inicioAtual !== null && fimAtual !== null && fimAtual > inicioAtual) {
            duracao = fimAtual - inicioAtual;
        }
        /* A hora fim só é trocada sozinha enquanto a pessoa não mexeu nela. */
        var fimMexidoAMao = false;
        campoFim.addEventListener('input', function () { fimMexidoAMao = true; });
        campoInicio.addEventListener('change', function () {
            var inicio = paraMinutos(campoInicio.value);
            if (inicio === null) { return; }
            if (fimMexidoAMao && campoFim.value) { return; }
            var fim = inicio + duracao;
            if (fim >= 24 * 60) { return; }
            campoFim.value = paraHora(fim);
        });
    }
})();
