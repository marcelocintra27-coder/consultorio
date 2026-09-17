(function () {
    'use strict';
    const botao = document.getElementById('adicionar-medicamento');
    const total = document.getElementById('id_itens-TOTAL_FORMS');
    const modelo = document.getElementById('medicamento-vazio');
    const lista = document.getElementById('medicamentos');
    if (!botao || !total || !modelo || !lista) return;
    botao.addEventListener('click', function () {
        const indice = Number(total.value);
        if (indice >= 50) return;
        const copia = modelo.content.cloneNode(true);
        copia.querySelectorAll('*').forEach(function (elemento) {
            ['name', 'id', 'for', 'aria-describedby'].forEach(function (atributo) {
                if (elemento.hasAttribute(atributo)) {
                    elemento.setAttribute(atributo, elemento.getAttribute(atributo).replaceAll('__prefix__', String(indice)));
                }
            });
        });
        lista.appendChild(copia);
        total.value = indice + 1;
        botao.disabled = Number(total.value) >= 50;
        lista.lastElementChild.querySelector('input[type="text"]')?.focus();
    });
}());
