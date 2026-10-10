/* Novo funcionário / editar: o campo da dentista só aparece quando a função pede. */
(function () {
    'use strict';
    var form = document.getElementById('form-funcionario');
    if (!form) { return; }
    var bloco = document.getElementById('bloco-dentista');
    var rotulo = bloco ? bloco.querySelector('label') : null;
    function atualizar() {
        var marcada = form.querySelector('input[name="funcao"]:checked');
        var funcao = marcada ? marcada.value : '';
        if (!bloco) { return; }
        bloco.hidden = !(funcao === 'auxiliar' || funcao === 'dentista');
        if (rotulo) {
            rotulo.textContent = funcao === 'dentista'
                ? 'Qual é o cadastro desta dentista?'
                : 'Trabalha com qual dentista?';
        }
    }
    form.querySelectorAll('input[name="funcao"]').forEach(function (radio) {
        radio.addEventListener('change', atualizar);
    });
    atualizar();
})();
