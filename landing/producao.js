const API_PRODUCAO = "http://127.0.0.1:8000/producao";

const mensagem = document.getElementById("mensagem");

const listas = {
  A_FAZER: document.getElementById("lista-a-fazer"),
  EM_PRODUCAO: document.getElementById("lista-em-producao"),
  PRONTO_PARA_POSTAR: document.getElementById("lista-pronto"),
  PUBLICADO: document.getElementById("lista-publicado"),
};

const contadores = {
  A_FAZER: document.getElementById("contador-a-fazer"),
  EM_PRODUCAO: document.getElementById("contador-em-producao"),
  PRONTO_PARA_POSTAR: document.getElementById("contador-pronto"),
  PUBLICADO: document.getElementById("contador-publicado"),
};

const totais = {
  A_FAZER: document.getElementById("total-a-fazer"),
  EM_PRODUCAO: document.getElementById("total-em-producao"),
  PRONTO_PARA_POSTAR: document.getElementById("total-pronto"),
  PUBLICADO: document.getElementById("total-publicado"),
};

function formatarStatus(status) {
  const nomes = {
    A_FAZER: "Fila da semana",
    EM_PRODUCAO: "Em edição",
    PRONTO_PARA_POSTAR: "Pronto para postar",
    PUBLICADO: "Publicado",
  };

  return nomes[status] || status;
}

function proximoStatus(status) {
  const fluxo = {
    A_FAZER: "EM_PRODUCAO",
    EM_PRODUCAO: "PRONTO_PARA_POSTAR",
    PRONTO_PARA_POSTAR: "PUBLICADO",
  };

  return fluxo[status] || null;
}

function statusAnterior(status) {
  const fluxo = {
    EM_PRODUCAO: "A_FAZER",
    PRONTO_PARA_POSTAR: "EM_PRODUCAO",
    PUBLICADO: "PRONTO_PARA_POSTAR",
  };

  return fluxo[status] || null;
}

function textoBotao(status) {
  const textos = {
    A_FAZER: "Começar edição",
    EM_PRODUCAO: "Finalizar edição",
    PRONTO_PARA_POSTAR: "Marcar como publicado",
  };

  return textos[status] || "";
}

function limparColunas() {
  Object.values(listas).forEach((lista) => {
    lista.innerHTML = "";
  });
}

function atualizarContadores(dados) {
  const quantidades = {
    A_FAZER: 0,
    EM_PRODUCAO: 0,
    PRONTO_PARA_POSTAR: 0,
    PUBLICADO: 0,
  };

  dados.forEach((item) => {
    if (quantidades[item.status] !== undefined) {
      quantidades[item.status]++;
    }
  });

  Object.keys(quantidades).forEach((status) => {
    contadores[status].textContent = quantidades[status];
    totais[status].textContent = quantidades[status];
  });
}

function criarCard(item) {
  const card = document.createElement("article");

  card.className = "card-producao";

  const proximo = proximoStatus(item.status);
  const anterior = statusAnterior(item.status);

  card.innerHTML = `
    <h3>${item.nome || "Sem nome"}</h3>

    <div class="card-meta">
      ${item.idade ?? "?"} anos •
      ${item.faixa_etaria || "Sem categoria"}
    </div>

    <div class="card-sonho">
      <strong>Sonho:</strong>
      ${item.sonho || "Não informado"}
    </div>

    <div class="card-midias">

      <span class="badge">
        📷 ${item.quantidade_fotos || 0}
      </span>

      <span class="badge">
        🎥 ${item.quantidade_videos || 0}
      </span>

    </div>

    <select
      class="tipo-conteudo"
      data-id="${item.producao_id}"
    >

      <option value="NAO_DEFINIDO">
        Definir formato
      </option>

      <option value="REEL">
        Reel
      </option>

      <option value="CARROSSEL">
        Carrossel
      </option>

      <option value="STORY">
        Story
      </option>

      <option value="POST">
        Post
      </option>

    </select>

    <div class="card-acoes">

      <a
        href="${item.drive_url}"
        target="_blank"
        rel="noopener noreferrer"
        class="botao-card botao-drive"
      >
        📁 Abrir Drive
      </a>

      ${
        anterior
          ? `
          <button
            type="button"
            class="botao-card botao-voltar-etapa"
            data-id="${item.producao_id}"
            data-status="${anterior}"
          >
            ← Voltar etapa
          </button>
          `
          : ""
      }

      ${
        proximo
          ? `
          <button
            type="button"
            class="botao-card botao-avancar"
            data-id="${item.producao_id}"
            data-status="${proximo}"
          >
            ${textoBotao(item.status)}
          </button>
          `
          : `
          <button
            type="button"
            class="botao-card botao-publicado"
            disabled
          >
            ✓ Publicado
          </button>
          `
      }

    </div>
  `;

  const select = card.querySelector(".tipo-conteudo");

  if (item.tipo_conteudo) {
    select.value = item.tipo_conteudo;
  }

  select.addEventListener("change", async () => {
    try {
      await atualizarProducao(item.producao_id, {
        tipo_conteudo: select.value,
      });
    } catch (erro) {
      await carregarProducao();
    }
  });

  const botaoAvancar = card.querySelector(".botao-avancar");

  if (botaoAvancar) {
    botaoAvancar.addEventListener("click", async () => {
      botaoAvancar.disabled = true;
      botaoAvancar.textContent = "Atualizando...";

      try {
        await atualizarProducao(item.producao_id, {
          status: botaoAvancar.dataset.status,
        });

        await carregarProducao();
      } catch (erro) {
        botaoAvancar.disabled = false;
        botaoAvancar.textContent = textoBotao(item.status);
      }
    });
  }

  const botaoVoltar = card.querySelector(".botao-voltar-etapa");

  if (botaoVoltar) {
    botaoVoltar.addEventListener("click", async () => {
      botaoVoltar.disabled = true;
      botaoVoltar.textContent = "Voltando...";

      try {
        await atualizarProducao(item.producao_id, {
          status: botaoVoltar.dataset.status,
        });

        await carregarProducao();
      } catch (erro) {
        botaoVoltar.disabled = false;
        botaoVoltar.textContent = "← Voltar etapa";
      }
    });
  }

  return card;
}

async function carregarProducao() {
  mensagem.style.display = "block";
  mensagem.textContent = "Carregando produção...";

  try {
    const resposta = await fetch(API_PRODUCAO);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    limparColunas();

    atualizarContadores(dados.resultados || []);

    const agrupados = {
      A_FAZER: [],
      EM_PRODUCAO: [],
      PRONTO_PARA_POSTAR: [],
      PUBLICADO: [],
    };

    (dados.resultados || []).forEach((item) => {
      if (agrupados[item.status]) {
        agrupados[item.status].push(item);
      }
    });

    Object.keys(agrupados).forEach((status) => {
      if (!agrupados[status].length) {
        listas[status].innerHTML = `
            <div class="vazio">
              Nenhum conteúdo nesta etapa.
            </div>
          `;

        return;
      }

      agrupados[status].forEach((item) => {
        listas[status].appendChild(criarCard(item));
      });
    });

    mensagem.style.display = "none";
  } catch (erro) {
    console.error("Erro ao carregar produção:", erro);

    mensagem.style.display = "block";

    mensagem.textContent = "Não foi possível carregar a produção.";
  }
}

async function atualizarProducao(producaoId, dados) {
  try {
    const resposta = await fetch(`${API_PRODUCAO}/${producaoId}`, {
      method: "PATCH",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify(dados),
    });

    if (!resposta.ok) {
      const erro = await resposta.json();

      throw new Error(erro.detail || "Erro ao atualizar produção.");
    }

    return await resposta.json();
  } catch (erro) {
    console.error("Erro ao atualizar produção:", erro);

    alert("Não foi possível atualizar este conteúdo.");

    throw erro;
  }
}

carregarProducao();
