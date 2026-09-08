(function () {
    function exclusivoNenhuma(nome) {
        var caixa = document.querySelector('[name="' + nome + '"]');
        if (!caixa) {
            var todas = document.querySelectorAll('input[name="' + nome + '"]');
            if (!todas.length) return;
        }
        var inputs = document.querySelectorAll('input[name="' + nome + '"]');
        var nenhuma = null;
        inputs.forEach(function (item) {
            if (item.value === 'nenhuma') nenhuma = item;
        });
        if (!nenhuma) return;
        inputs.forEach(function (item) {
            item.addEventListener('change', function () {
                if (item === nenhuma && nenhuma.checked) {
                    inputs.forEach(function (outro) {
                        if (outro !== nenhuma) outro.checked = false;
                    });
                } else if (item !== nenhuma && item.checked) {
                    nenhuma.checked = false;
                }
            });
        });
    }

    exclusivoNenhuma('saude_condicoes');
    exclusivoNenhuma('saude_bucal');
})();
