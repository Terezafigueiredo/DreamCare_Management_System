const API =
  "http://127.0.0.1:8000/historico-publicados";

const campoAno =
  document.getElementById("ano");

const campoTipo =
  document.getElementById("tipo");

const botaoBuscar =
  document.getElementById("botao-buscar");

const total =
  document.getElementById("total");

const mensagem =
  document.getElementById("mensagem");

const lista =
  document.getElementById("lista");


function formatarData(data) {

  if (!data) {
    return "Não informada";
  }

  const partes =
    data.split("-");

  if (partes.length !== 3) {
    return data;
  }

  return (
    `${partes[2]}/` +
    `${partes[1]}/` +
    `${partes[0]}`
  );
}


function formatarTipo(tipo) {

  const tipos = {
    REEL: "Reel",
    CARROSSEL: "Carrossel",
    STORY: "Story",
    POST: "Post",
    NAO_DEFINIDO:
      "Não definido"
  };

  return tipos[tipo] || tipo;
}


function criarCard(item) {

  const card =
    document.createElement("article");

  card.className = "card";

  card.innerHTML = `

    <h2>
      ${item.nome || "Sem nome"}
    </h2>

    <div class="meta">

      ${item.idade ?? "?"} anos
      •
      ${item.faixa_etaria || "Sem categoria"}

    </div>

    <div class="sonho">

      <strong>Sonho:</strong>

      ${item.sonho || "Não informado"}

    </div>

    <div class="badges">

      <span class="badge">

        ${formatarTipo(
          item.tipo_conteudo
        )}

      </span>

      <span class="badge">

        📷
        ${item.quantidade_fotos || 0}

      </span>

      <span class="badge">

        🎥
        ${item.quantidade_videos || 0}

      </span>

    </div>

    <div class="data-publicacao">

      Publicado em:
      ${formatarData(
        item.data_publicacao
      )}

    </div>

    <a
      href="${item.drive_url}"
      target="_blank"
      rel="noopener noreferrer"
      class="botao-drive"
    >

      📁 Abrir Drive

    </a>
  `;

  return card;
}


async function carregarHistorico() {

  const parametros =
    new URLSearchParams();

  if (campoAno.value) {

    parametros.append(
      "ano",
      campoAno.value
    );

  }

  if (campoTipo.value) {

    parametros.append(
      "tipo_conteudo",
      campoTipo.value
    );

  }


  const url =
    parametros.toString()
      ? `${API}?${parametros}`
      : API;


  mensagem.style.display =
    "block";

  mensagem.textContent =
    "Carregando histórico...";


  try {

    const resposta =
      await fetch(url);


    if (!resposta.ok) {

      throw new Error(
        `Erro HTTP ${resposta.status}`
      );

    }


    const dados =
      await resposta.json();


    total.textContent =
      dados.total;


    lista.innerHTML =
      "";


    if (!dados.resultados.length) {

      lista.innerHTML = `

        <div class="vazio">

          Nenhum conteúdo publicado encontrado.

        </div>
      `;

      mensagem.style.display =
        "none";

      return;

    }


    dados.resultados.forEach(
      (item) => {

        lista.appendChild(
          criarCard(item)
        );

      }
    );


    mensagem.style.display =
      "none";


  } catch (erro) {

    console.error(
      erro
    );

    lista.innerHTML =
      "";

    mensagem.style.display =
      "block";

    mensagem.textContent =
      "Não foi possível carregar o histórico.";

  }
}


botaoBuscar.addEventListener(
  "click",
  carregarHistorico
);


carregarHistorico();