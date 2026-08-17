const API_URL = "http://127.0.0.1:8000/central-conteudo";
const API_PRODUCAO = "http://127.0.0.1:8000/producao";
const API_SUGESTOES = "http://127.0.0.1:8000/sugestoes-semana";

const campoBusca = document.getElementById("busca");
const campoIdade = document.getElementById("idade-maxima");
const campoFaixa = document.getElementById("faixa-etaria");
const campoFotos = document.getElementById("tem-fotos");
const campoVideos = document.getElementById("tem-videos");

const botaoBuscar = document.getElementById("botao-buscar");
const botaoLimpar = document.getElementById("botao-limpar");

const totalResultados = document.getElementById("total-resultados");
const statusConsulta = document.getElementById("status-consulta");
const mensagem = document.getElementById("mensagem");
const listaResultados = document.getElementById("lista-resultados");

const listaSugestoes = document.getElementById("lista-sugestoes");

const botaoAtualizarSugestoes = document.getElementById(
  "botao-atualizar-sugestoes",
);

// =========================================================
// PARÂMETROS DA BUSCA
// =========================================================

function montarParametros() {
  const parametros = new URLSearchParams();

  const busca = campoBusca.value.trim();
  const idade = campoIdade.value.trim();
  const faixa = campoFaixa.value;

  if (busca) {
    parametros.append("busca", busca);
  }

  if (idade) {
    parametros.append("idade_maxima", idade);
  }

  if (faixa) {
    parametros.append("faixa_etaria", faixa);
  }

  if (campoFotos.checked) {
    parametros.append("tem_fotos", "true");
  }

  if (campoVideos.checked) {
    parametros.append("tem_videos", "true");
  }

  return parametros;
}

// =========================================================
// FORMATAÇÕES
// =========================================================

function formatarData(data) {
  if (!data) {
    return "Não informada";
  }

  const partes = data.split("-");

  if (partes.length !== 3) {
    return data;
  }

  return `${partes[2]}/${partes[1]}/${partes[0]}`;
}

function formatarFaixa(faixa) {
  const nomes = {
    CRIANCA: "Criança",
    ADOLESCENTE: "Adolescente",
    ADULTO: "Adulto",
    IDADE_NAO_INFORMADA: "Idade não informada",
  };

  return nomes[faixa] || faixa || "Não informada";
}

function formatarStatusProducao(status) {
  const nomes = {
    A_FAZER: "Fila da semana",
    EM_PRODUCAO: "Em edição",
    PRONTO_PARA_POSTAR: "Pronto para postar",
    PUBLICADO: "Publicado",
  };

  return nomes[status] || status;
}

// =========================================================
// ADICIONAR À SEMANA
// =========================================================

async function adicionarSemana(
  sonhoId,
  botao,
  atualizarSugestoesDepois = false,
) {
  botao.disabled = true;
  botao.textContent = "Adicionando...";

  try {
    const resposta = await fetch(API_PRODUCAO, {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        sonho_id: sonhoId,
        tipo_conteudo: "NAO_DEFINIDO",
      }),
    });

    const dados = await resposta.json();

    if (resposta.status === 409) {
      botao.textContent = "✓ Já está na semana";
      botao.classList.add("adicionado");
      return;
    }

    if (!resposta.ok) {
      throw new Error(dados.detail || "Erro ao adicionar.");
    }

    botao.textContent = "✓ Adicionado à semana";

    botao.classList.add("adicionado");

    if (atualizarSugestoesDepois) {
      await carregarSugestoes();
    }
  } catch (erro) {
    console.error("Erro ao adicionar à semana:", erro);

    alert("Não foi possível adicionar este sonho à semana.");

    botao.disabled = false;
    botao.textContent = "+ Adicionar à semana";
  }
}

// =========================================================
// CARD DA BUSCA NORMAL
// =========================================================

function criarCard(item) {
  const card = document.createElement("article");

  card.className = "card-sonho";

  const idadeTexto =
    item.idade !== null && item.idade !== undefined
      ? `${item.idade} anos`
      : "Idade não informada";

  const botaoSemana = item.ja_na_semana
    ? `
        <button
          type="button"
          class="botao-producao adicionado"
          disabled
        >
          ✓ ${formatarStatusProducao(item.producao_status)}
        </button>
      `
    : `
        <button
          type="button"
          class="botao-producao"
          data-sonho-id="${item.id}"
        >
          + Adicionar à semana
        </button>
      `;

  card.innerHTML = `
    <div class="card-topo">

      <div>

        <h2 class="card-nome">
          ${item.nome || "Sem nome"}
        </h2>

        <p class="card-faixa">
          ${formatarFaixa(item.faixa_etaria)}
        </p>

      </div>

      <span class="card-idade">
        ${idadeTexto}
      </span>

    </div>

    <div class="card-sonho-texto">

      <strong>Sonho:</strong>

      ${item.sonho || "Não informado"}

    </div>

    <div class="card-detalhes">

      <p>
        <strong>Data:</strong>
        ${formatarData(item.data_realizacao)}
      </p>

      <p>
        <strong>Enfermidade:</strong>
        ${item.enfermidade || "Não informada"}
      </p>

      <p>
        <strong>Idealizador:</strong>
        ${item.idealizador || "Não informado"}
      </p>

    </div>

    <div class="card-midias">

      <span class="badge">
        📷 ${item.quantidade_fotos || 0}
        fotos
      </span>

      <span class="badge">
        🎥 ${item.quantidade_videos || 0}
        vídeos
      </span>

    </div>

    <div class="card-acoes">

      <a
        class="botao-drive"
        href="${item.drive_url}"
        target="_blank"
        rel="noopener noreferrer"
      >
        📁 Abrir Drive
      </a>

      ${botaoSemana}

    </div>
  `;

  const botao = card.querySelector(".botao-producao:not(.adicionado)");

  if (botao) {
    botao.addEventListener("click", async () => {
      await adicionarSemana(item.id, botao);
    });
  }

  return card;
}

// =========================================================
// RESULTADOS DA BUSCA
// =========================================================

function mostrarResultados(resultados) {
  listaResultados.innerHTML = "";

  if (!resultados.length) {
    listaResultados.innerHTML = `
      <div class="sem-resultados">

        <strong>
          Nenhum sonho encontrado.
        </strong>

        <p>
          Tente alterar os filtros.
        </p>

      </div>
    `;

    return;
  }

  resultados.forEach((item) => {
    listaResultados.appendChild(criarCard(item));
  });
}

// =========================================================
// BUSCAR CONTEÚDOS
// =========================================================

async function buscarConteudos() {
  const parametros = montarParametros();

  const url = parametros.toString()
    ? `${API_URL}?${parametros.toString()}`
    : API_URL;

  statusConsulta.textContent = "Buscando...";

  mensagem.style.display = "block";

  mensagem.textContent = "Consultando o DreamCare...";

  botaoBuscar.disabled = true;

  botaoBuscar.textContent = "Buscando...";

  try {
    const resposta = await fetch(url);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    totalResultados.textContent = dados.total;

    statusConsulta.textContent = "Consulta concluída";

    mostrarResultados(dados.resultados || []);

    if (dados.total > 0) {
      mensagem.style.display = "none";
    } else {
      mensagem.textContent = "Nenhum sonho corresponde aos filtros escolhidos.";
    }
  } catch (erro) {
    console.error("Erro na busca:", erro);

    totalResultados.textContent = "0";

    statusConsulta.textContent = "Erro";

    listaResultados.innerHTML = "";

    mensagem.style.display = "block";

    mensagem.textContent = "Não foi possível acessar a API.";
  } finally {
    botaoBuscar.disabled = false;

    botaoBuscar.textContent = "Buscar sonhos";
  }
}

// =========================================================
// LIMPAR BUSCA
// =========================================================

function limparFiltros() {
  campoBusca.value = "";
  campoIdade.value = "";
  campoFaixa.value = "";

  campoFotos.checked = false;
  campoVideos.checked = false;

  totalResultados.textContent = "0";

  statusConsulta.textContent = "Aguardando busca";

  listaResultados.innerHTML = "";

  mensagem.style.display = "block";

  mensagem.textContent = "Use os filtros acima para encontrar sonhos.";
}

// =========================================================
// CARD DE SUGESTÃO
// =========================================================

function criarCardSugestao(item) {
  const card = document.createElement("article");

  card.className = "card-sugestao";

  const idadeTexto =
    item.idade !== null && item.idade !== undefined
      ? `${item.idade} anos`
      : "Idade não informada";

  card.innerHTML = `

    <div>

      <h3>
        ${item.nome || "Sem nome"}
      </h3>

      <p class="sugestao-meta">
        ${idadeTexto}
        •
        ${formatarFaixa(item.faixa_etaria)}
      </p>

    </div>

    <div class="sugestao-sonho">

      <strong>Sonho:</strong>

      ${item.sonho || "Não informado"}

    </div>

    <div class="card-midias">

      <span class="badge">
        📷
        ${item.quantidade_fotos || 0}
        fotos
      </span>

      <span class="badge">
        🎥
        ${item.quantidade_videos || 0}
        vídeos
      </span>

    </div>

    <span class="sugestao-score">
  Boa disponibilidade de mídia
</span>

    <div class="sugestao-acoes">

      <a
        class="botao-drive"
        href="${item.drive_url}"
        target="_blank"
        rel="noopener noreferrer"
      >
        📁 Abrir Drive
      </a>

      <button
        type="button"
        class="botao-producao"
      >
        + Adicionar à semana
      </button>

    </div>
  `;

  const botao = card.querySelector(".botao-producao");

  botao.addEventListener("click", async () => {
    await adicionarSemana(item.id, botao, true);
  });

  return card;
}

// =========================================================
// CARREGAR SUGESTÕES
// =========================================================

async function carregarSugestoes() {
  if (!listaSugestoes || !botaoAtualizarSugestoes) {
    return;
  }

  listaSugestoes.innerHTML = `
    <div class="mensagem-sugestoes">
      Carregando sugestões...
    </div>
  `;

  botaoAtualizarSugestoes.disabled = true;

  botaoAtualizarSugestoes.textContent = "Atualizando...";

  try {
    const resposta = await fetch(API_SUGESTOES);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    listaSugestoes.innerHTML = "";

    if (!dados.sugestoes?.length) {
      listaSugestoes.innerHTML = `
        <div class="mensagem-sugestoes">

          Nenhuma sugestão disponível
          neste momento.

        </div>
      `;

      return;
    }

    dados.sugestoes.forEach((item) => {
      listaSugestoes.appendChild(criarCardSugestao(item));
    });
  } catch (erro) {
    console.error("Erro ao carregar sugestões:", erro);

    listaSugestoes.innerHTML = `
      <div class="mensagem-sugestoes">

        Não foi possível carregar
        as sugestões.

      </div>
    `;
  } finally {
    botaoAtualizarSugestoes.disabled = false;

    botaoAtualizarSugestoes.textContent = "Atualizar sugestões";
  }
}

// =========================================================
// EVENTOS
// =========================================================

botaoBuscar.addEventListener("click", buscarConteudos);

botaoLimpar.addEventListener("click", limparFiltros);

campoBusca.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter") {
    buscarConteudos();
  }
});

if (botaoAtualizarSugestoes) {
  botaoAtualizarSugestoes.addEventListener("click", carregarSugestoes);
}

// =========================================================
// INICIALIZAÇÃO
// =========================================================

carregarSugestoes();
