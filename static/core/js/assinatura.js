(function () {
    var FUNDO = '#e8f1f4';
    var TRACO = '#1c2b33';

    function bind(canvas, hidden, limpar) {
        if (!canvas || !hidden) return;
        var ctx = canvas.getContext('2d');
        var desenhando = false;
        var houveTraco = false;
        var ultimo = null;

        function pintarFundo() {
            ctx.fillStyle = FUNDO;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

        function ponto(evento) {
            var ret = canvas.getBoundingClientRect();
            if (!ret.width || !ret.height) {
                return { x: 0, y: 0 };
            }
            return {
                x: (evento.clientX - ret.left) * (canvas.width / ret.width),
                y: (evento.clientY - ret.top) * (canvas.height / ret.height),
            };
        }

        function iniciar(evento) {
            if (evento.pointerType === 'mouse' && evento.button !== 0) return;
            evento.preventDefault();
            desenhando = true;
            houveTraco = true;
            ultimo = ponto(evento);
            try {
                canvas.setPointerCapture(evento.pointerId);
            } catch (e) {}
        }

        function mover(evento) {
            if (!desenhando) return;
            evento.preventDefault();
            var atual = ponto(evento);
            ctx.strokeStyle = TRACO;
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.beginPath();
            ctx.moveTo(ultimo.x, ultimo.y);
            ctx.lineTo(atual.x, atual.y);
            ctx.stroke();
            ultimo = atual;
            hidden.value = canvas.toDataURL('image/png');
        }

        function parar(evento) {
            if (!desenhando) return;
            if (evento) evento.preventDefault();
            desenhando = false;
            ultimo = null;
            if (houveTraco) {
                hidden.value = canvas.toDataURL('image/png');
            }
        }

        pintarFundo();

        canvas.addEventListener('pointerdown', iniciar);
        canvas.addEventListener('pointermove', mover);
        canvas.addEventListener('pointerup', parar);
        canvas.addEventListener('pointercancel', parar);
        canvas.addEventListener('lostpointercapture', parar);

        if (limpar) {
            limpar.addEventListener('click', function () {
                pintarFundo();
                hidden.value = '';
                houveTraco = false;
            });
        }

        var form = canvas.closest('form');
        if (form) {
            form.addEventListener('submit', function (evento) {
                if (!houveTraco || !hidden.value) {
                    evento.preventDefault();
                    canvas.focus();
                }
            });
        }
    }

    function iniciarQuadros() {
        document.querySelectorAll('.assinatura-canvas').forEach(function (canvas) {
            if (canvas.dataset.assinaturaPronta) return;
            canvas.dataset.assinaturaPronta = '1';
            var id = canvas.id.replace(/-canvas$/, '');
            bind(
                canvas,
                document.getElementById('id_' + id),
                document.querySelector('[data-assinatura-limpar="' + id + '"]')
            );
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciarQuadros);
    } else {
        iniciarQuadros();
    }
})();
