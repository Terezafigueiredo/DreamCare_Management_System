// =========================================================
// ENDPOINTS DA API
// =========================================================

const API_SONHOS = "http://127.0.0.1:8000/sonhos";

const API_PRODUCAO = "http://127.0.0.1:8000/producao";

const API_HISTORICO = "http://127.0.0.1:8000/historico-publicados";

// =========================================================
// TOTAL DE SONHOS
// =========================================================

async function carregarTotalSonhos() {
  try {
    const resposta = await fetch(API_SONHOS);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    const elemento = document.getElementById("total-sonhos");

    if (elemento) {
      elemento.textContent = dados.total || 0;
    }
  } catch (erro) {
    console.error("Erro ao carregar total de sonhos:", erro);
  }
}

// =========================================================
// INDICADORES DE PRODUÇÃO
// =========================================================

async function carregarProducao() {
  try {
    const resposta = await fetch(API_PRODUCAO);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    const resultados = dados.resultados || [];

    const totais = {
      A_FAZER: 0,
      EM_PRODUCAO: 0,
      PRONTO_PARA_POSTAR: 0,
    };

    resultados.forEach((item) => {
      if (totais[item.status] !== undefined) {
        totais[item.status]++;
      }
    });

    const fila = document.getElementById("total-fila");

    const edicao = document.getElementById("total-edicao");

    const prontos = document.getElementById("total-prontos");

    if (fila) {
      fila.textContent = totais.A_FAZER;
    }

    if (edicao) {
      edicao.textContent = totais.EM_PRODUCAO;
    }

    if (prontos) {
      prontos.textContent = totais.PRONTO_PARA_POSTAR;
    }
  } catch (erro) {
    console.error("Erro ao carregar produção:", erro);
  }
}

// =========================================================
// TOTAL DE PUBLICADOS
// =========================================================

async function carregarHistorico() {
  try {
    const resposta = await fetch(API_HISTORICO);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    const elemento = document.getElementById("total-publicados");

    if (elemento) {
      elemento.textContent = dados.total || 0;
    }
  } catch (erro) {
    console.error("Erro ao carregar histórico:", erro);
  }
}
const API_CENTRAL = "http://127.0.0.1:8000/central-conteudo";

const API_PRODUCAO_ASSISTENTE = "http://127.0.0.1:8000/producao";

const campoPergunta = document.getElementById("pergunta-dreamcare");

const botaoPerguntar = document.getElementById("botao-perguntar");

const respostaAssistente = document.getElementById("resposta-assistente");

const resultadosAssistente = document.getElementById("resultados-assistente");

function interpretarPergunta(texto) {
  const pergunta = texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  const parametros = new URLSearchParams();

  // Fotos
  if (pergunta.includes("foto") || pergunta.includes("fotos")) {
    parametros.append("tem_fotos", "true");
  }

  // Vídeos
  if (pergunta.includes("video") || pergunta.includes("videos")) {
    parametros.append("tem_videos", "true");
  }

  // Crianças
  if (pergunta.includes("crianca") || pergunta.includes("criancas")) {
    parametros.append("faixa_etaria", "CRIANCA");
  }

  // Adolescentes
  if (pergunta.includes("adolescente") || pergunta.includes("adolescentes")) {
    parametros.append("faixa_etaria", "ADOLESCENTE");
  }

  // Adultos
  if (pergunta.includes("adulto") || pergunta.includes("adultos")) {
    parametros.append("faixa_etaria", "ADULTO");
  }

  // Detectar idade máxima
  const padroesIdade = [
    /abaixo de (\d+)/,
    /menos de (\d+)/,
    /ate (\d+)/,
    /até (\d+)/,
  ];

  for (const padrao of padroesIdade) {
    const resultado = pergunta.match(padrao);

    if (resultado) {
      parametros.set("idade_maxima", resultado[1]);

      break;
    }
  }

  return parametros;
}

function criarCardAssistente(item) {
  const card = document.createElement("article");

  card.className = "card-assistente";

  card.innerHTML = `
    <h3>
      ${item.nome || "Sem nome"}
    </h3>

    <div class="meta">
      ${item.idade ?? "?"} anos •
      ${item.faixa_etaria || ""}
    </div>

    <div class="sonho">
      <strong>Sonho:</strong>
      ${item.sonho || "Não informado"}
    </div>

    <div class="midias">
      <span>
        📷 ${item.quantidade_fotos || 0}
      </span>

      <span>
        🎥 ${item.quantidade_videos || 0}
      </span>
    </div>

    <div class="acoes-assistente">

      <a
        href="${item.drive_url}"
        target="_blank"
        rel="noopener noreferrer"
      >
        📁 Abrir Drive
      </a>

      ${
        item.ja_na_semana
          ? `
            <button
              type="button"
              disabled
            >
              ✓ Já está na semana
            </button>
          `
          : `
            <button
              type="button"
              class="adicionar-assistente"
              data-id="${item.id}"
            >
              + Adicionar à semana
            </button>
          `
      }

    </div>
  `;

  const botao = card.querySelector(".adicionar-assistente");

  if (botao) {
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      botao.textContent = "Adicionando...";

      try {
        const resposta = await fetch(API_PRODUCAO_ASSISTENTE, {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            sonho_id: item.id,
            tipo_conteudo: "NAO_DEFINIDO",
          }),
        });

        if (!resposta.ok && resposta.status !== 409) {
          throw new Error("Erro ao adicionar");
        }

        botao.textContent = "✓ Adicionado à semana";
      } catch (erro) {
        console.error(erro);

        botao.disabled = false;

        botao.textContent = "+ Adicionar à semana";
      }
    });
  }

  return card;
}

async function perguntarDreamCare() {
  const texto = campoPergunta.value.trim();

  if (!texto) {
    respostaAssistente.textContent = "Digite o que você deseja encontrar.";

    return;
  }

  const parametros = interpretarPergunta(texto);

  const url = parametros.toString()
    ? `${API_CENTRAL}?${parametros.toString()}`
    : API_CENTRAL;

  respostaAssistente.textContent = "Buscando sonhos...";

  resultadosAssistente.innerHTML = "";

  botaoPerguntar.disabled = true;

  try {
    const resposta = await fetch(url);

    if (!resposta.ok) {
      throw new Error(`Erro HTTP ${resposta.status}`);
    }

    const dados = await resposta.json();

    const resultados = dados.resultados || [];

    respostaAssistente.textContent = `${resultados.length} sonho(s) encontrado(s).`;

    if (!resultados.length) {
      return;
    }

    resultados.slice(0, 12).forEach((item) => {
      resultadosAssistente.appendChild(criarCardAssistente(item));
    });
  } catch (erro) {
    console.error("Erro no assistente:", erro);

    respostaAssistente.textContent = "Não foi possível realizar a busca.";
  } finally {
    botaoPerguntar.disabled = false;
  }
}

if (botaoPerguntar && campoPergunta) {
  botaoPerguntar.addEventListener("click", perguntarDreamCare);

  campoPergunta.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
      perguntarDreamCare();
    }
  });
}

// =========================================================
// CARREGAR DASHBOARD
// =========================================================

async function carregarDashboard() {
  await Promise.all([
    carregarTotalSonhos(),
    carregarProducao(),
    carregarHistorico(),
  ]);
}

// =========================================================
// INICIALIZAÇÃO
// =========================================================

carregarDashboard();
