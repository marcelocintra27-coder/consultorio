(function () {
    function marcarDentistaLogado(bloco, dentistaId) {
        if (!dentistaId || !bloco) return;
        bloco.querySelectorAll('input[type="checkbox"][name$="-dentistas"]').forEach(function (caixa) {
            if (caixa.value === String(dentistaId)) {
                caixa.checked = true;
            }
        });
    }

    function adicionarLinha(prefixo, dentistaId) {
        var total = document.getElementById('id_' + prefixo + '-TOTAL_FORMS');
        var molde = document.getElementById(prefixo + '-empty');
        var destino = document.getElementById(prefixo + '-rows');
        if (!total || !molde || !destino) return;
        var indice = parseInt(total.value, 10);
        var html = molde.innerHTML.replace(/__prefix__/g, String(indice));
        destino.insertAdjacentHTML('beforeend', html);
        total.value = String(indice + 1);
        var blocos = destino.querySelectorAll('.plano-item');
        marcarDentistaLogado(blocos[blocos.length - 1], dentistaId);
        if (window.iniciarQuadrosAssinatura) {
            window.iniciarQuadrosAssinatura();
        }
    }

    document.querySelectorAll('[data-formset-add]').forEach(function (botao) {
        botao.addEventListener('click', function () {
            adicionarLinha(
                botao.getAttribute('data-formset-add'),
                botao.getAttribute('data-dentista-logado')
            );
        });
    });
})();
