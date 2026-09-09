(function () {
  const botao = document.getElementById("btn-gravar");
  if (!botao) return;

  const status = document.getElementById("gravador-status");
  const resultado = document.getElementById("gravador-resultado");
  const texto = document.getElementById("gravador-texto");
  const url = botao.dataset.url;
  const csrf = botao.dataset.csrf;

  let gravador = null;
  let pedacos = [];
  let gravando = false;

  botao.addEventListener("click", async function () {
    if (!gravando) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        gravador = new MediaRecorder(stream);
        pedacos = [];

        gravador.ondataavailable = (e) => pedacos.push(e.data);
        gravador.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          enviar(new Blob(pedacos, { type: "audio/webm" }));
        };

        gravador.start();
        gravando = true;
        botao.textContent = "Parar gravacao";
        botao.classList.add("gravando");
        status.textContent = "Gravando...";
      } catch (err) {
        status.textContent = "Nao foi possivel acessar o microfone: " + err.message;
      }
    } else {
      gravador.stop();
      gravando = false;
      botao.textContent = "Gravar evolucao";
      botao.classList.remove("gravando");
      status.textContent = "Transcrevendo, aguarde...";
      botao.disabled = true;
    }
  });

  async function enviar(blob) {
    const dados = new FormData();
    dados.append("audio", blob, "gravacao.webm");

    try {
      const resposta = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
        },
        body: dados,
      });

      const json = await resposta.json();
      if (!resposta.ok) {
        status.textContent = json.erro || "Falha na transcricao.";
        return;
      }

      texto.value = json.texto || "";
      const campoRegistro = document.getElementById("campo-registro-id");
      if (campoRegistro) campoRegistro.value = json.registro_id || "";
      resultado.hidden = false;
      status.textContent = "Transcricao pronta.";
    } catch (err) {
      status.textContent = "Erro ao enviar o audio: " + err.message;
    } finally {
      botao.disabled = false;
    }
  }

  const formSalvar = document.getElementById("form-salvar-evolucao");
  if (formSalvar) {
    formSalvar.addEventListener("submit", function () {
      document.getElementById("campo-texto-final").value = texto.value;
    });
  }
})();
