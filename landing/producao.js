const API_PRODUCAO = "http://127.0.0.1:8080/producao";
const API_BASE = "http://127.0.0.1:8080";
const PUBLICACAO_INSTAGRAM_ATIVA = false;
let revisaoEmAndamento = false;

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
    PRONTO_PARA_POSTAR: "Registrar publicação manual",
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

    <div class="automacao-social">
      <label for="legenda-${item.producao_id}">Legenda do Instagram</label>
      <textarea
        id="legenda-${item.producao_id}"
        class="legenda-instagram"
        rows="3"
        placeholder="Escreva a legenda que será revisada antes da publicação"
      >${item.legenda_instagram || ""}</textarea>

      ${
        item.edicao_status === "AGUARDANDO_APROVACAO"
          ? `<video class="previa-video" controls preload="metadata"
               src="${API_BASE}${item.video_preview_url}"></video>`
          : ""
      }

      ${
        item.resumo_edicao
          ? `<div class="resumo-edicao">
               <span>${Number(item.resumo_edicao.duracao_segundos || 0).toFixed(1)}s</span>
               <span>${item.resumo_edicao.videos_utilizados || 0} vídeos</span>
               <span>${item.resumo_edicao.trechos_utilizados || 0} trechos</span>
             </div>
             <a class="link-relatorio" href="${API_BASE}${item.relatorio_edicao_url}"
                target="_blank" rel="noopener noreferrer">Ver relatório JSON</a>`
          : ""
      }

      ${
        item.edicao_status === "AGUARDANDO_APROVACAO"
          ? `<button type="button" class="botao-card botao-revisar-trechos">
               Revisar trechos
             </button>
             <section class="revisao-trechos" hidden></section>`
          : ""
      }

      <p class="status-automacao ${item.edicao_status === "ERRO" ? "status-erro" : ""}">
        ${textoStatusEdicao(item)}
      </p>

      ${
        item.status !== "PUBLICADO" && item.edicao_status !== "PROCESSANDO"
          ? `<button type="button" class="botao-card botao-editar-video">
               ${item.edicao_status === "AGUARDANDO_APROVACAO" ? "Refazer edição automática" : "Preparar vídeo automaticamente"}
             </button>`
          : ""
      }

      ${
        PUBLICACAO_INSTAGRAM_ATIVA &&
        item.edicao_status === "AGUARDANDO_APROVACAO" &&
        item.status === "PRONTO_PARA_POSTAR"
          ? `<button type="button" class="botao-card botao-instagram">
               Autorizar e publicar no Instagram
             </button>`
          : ""
      }
    </div>

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

  const botaoEditar = card.querySelector(".botao-editar-video");
  if (botaoEditar) {
    botaoEditar.addEventListener("click", async () => {
      const legenda = card.querySelector(".legenda-instagram").value;
      botaoEditar.disabled = true;
      botaoEditar.textContent = "Iniciando edição...";
      try {
        await chamarAutomacao(`${API_PRODUCAO}/${item.producao_id}/preparar-video`, {
          legenda,
          duracao_maxima: 60,
        });
        await carregarProducao();
      } catch (erro) {
        botaoEditar.disabled = false;
        botaoEditar.textContent = "Preparar vídeo automaticamente";
      }
    });
  }

  const botaoRevisar = card.querySelector(".botao-revisar-trechos");
  if (botaoRevisar) {
    botaoRevisar.addEventListener("click", async () => {
      const painel = card.querySelector(".revisao-trechos");
      if (!painel.hidden) {
        painel.hidden = true;
        revisaoEmAndamento = false;
        botaoRevisar.textContent = "Revisar trechos";
        return;
      }
      botaoRevisar.disabled = true;
      botaoRevisar.textContent = "Carregando trechos...";
      try {
        const revisao = await carregarRevisao(item.producao_id);
        montarRevisao(painel, item, revisao);
        painel.hidden = false;
        revisaoEmAndamento = true;
        botaoRevisar.textContent = "Fechar revisão";
      } catch (erro) {
        alert(erro.message);
        botaoRevisar.textContent = "Revisar trechos";
      } finally {
        botaoRevisar.disabled = false;
      }
    });
  }

  const botaoInstagram = card.querySelector(".botao-instagram");
  if (botaoInstagram) {
    botaoInstagram.addEventListener("click", async () => {
      const autorizou = confirm(
        "Você revisou o vídeo e a legenda? Ao continuar, o Reel será publicado no Instagram."
      );
      if (!autorizou) return;

      botaoInstagram.disabled = true;
      botaoInstagram.textContent = "Publicando...";
      try {
        await chamarAutomacao(
          `${API_PRODUCAO}/${item.producao_id}/publicar-instagram`,
          { confirmar_publicacao: true }
        );
        alert("Reel publicado no Instagram com sucesso.");
        await carregarProducao();
      } catch (erro) {
        botaoInstagram.disabled = false;
        botaoInstagram.textContent = "Autorizar e publicar no Instagram";
      }
    });
  }

  const botaoAvancar = card.querySelector(".botao-avancar");

  if (botaoAvancar) {
    botaoAvancar.addEventListener("click", async () => {
      if (
        botaoAvancar.dataset.status === "PUBLICADO" &&
        !confirm("Confirma que este conteúdo já foi publicado manualmente?")
      ) {
        return;
      }
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

function textoStatusEdicao(item) {
  const textos = {
    NAO_INICIADA: "A edição automática ainda não foi iniciada.",
    PROCESSANDO: "Editando os vídeos da pasta. A página pode ser atualizada.",
    AGUARDANDO_APROVACAO: "Prévia pronta e aguardando aprovação.",
    ERRO: `Falha na edição: ${item.erro_automacao || "erro não informado"}`,
  };
  return textos[item.edicao_status] || textos.NAO_INICIADA;
}

async function chamarAutomacao(url, dados) {
  const resposta = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
  });
  const retorno = await resposta.json();
  if (!resposta.ok) {
    alert(retorno.detail || "Não foi possível executar a automação.");
    throw new Error(retorno.detail || `Erro HTTP ${resposta.status}`);
  }
  return retorno;
}

async function carregarRevisao(producaoId) {
  const resposta = await fetch(`${API_PRODUCAO}/${producaoId}/revisar-trechos`);
  const retorno = await resposta.json();
  if (!resposta.ok) {
    throw new Error(retorno.detail || "Não foi possível carregar os trechos.");
  }
  return retorno;
}

function escaparHtml(valor) {
  const elemento = document.createElement("span");
  elemento.textContent = String(valor ?? "");
  return elemento.innerHTML;
}

function montarRevisao(painel, item, revisao) {
  painel.innerHTML = `
    <h4>Revisar trechos</h4>
    <p class="revisao-ajuda">
      Ajuste os intervalos de vídeo e a duração das fotos, reordene ou adicione
      mais mídia da pasta do sonho. A soma final deve ter até 60 segundos.
    </p>
    <div class="lista-trechos-revisao"></div>
    <div class="total-revisao"></div>
    <button type="button" class="botao-card botao-previa-sequencia-reels">▶ Pré-visualizar sequência</button>
    <div class="navegacao-midia">
      <h5>Adicionar mídia da pasta do sonho</h5>
      <div class="breadcrumb-pasta"></div>
      <div class="grid-subpastas"></div>
      <div class="grid-midias"></div>
    </div>
    <button type="button" class="botao-card botao-gerar-versao">Gerar nova versão</button>
  `;
  const lista = painel.querySelector(".lista-trechos-revisao");
  (revisao.trechos || []).forEach((trecho) => {
    lista.appendChild(criarTrechoRevisao(trecho, item.producao_id));
  });

  const atualizar = () => atualizarResumoRevisao(painel);
  lista.addEventListener("input", atualizar);
  lista.addEventListener("change", atualizar);
  montarNavegacaoMidia(painel, item);
  painel.querySelector(".botao-previa-sequencia-reels").addEventListener("click", () => {
    abrirPreviaSequenciaReels(painel);
  });
  painel.querySelector(".botao-gerar-versao").addEventListener("click", async (evento) => {
    const botao = evento.currentTarget;
    const trechos = [...lista.querySelectorAll(".trecho-revisao")].map((cardTrecho) => {
      if (cardTrecho.dataset.tipoMidia === "imagem") {
        return {
          tipo_midia: "imagem",
          drive_file_id: cardTrecho.dataset.fileId,
          duracao_segundos: Number(cardTrecho.querySelector(".duracao-foto").value),
          encaixe: cardTrecho.querySelector(".encaixe-foto").value,
        };
      }
      return {
        tipo_midia: "video",
        drive_file_id: cardTrecho.dataset.fileId,
        inicio_segundos: Number(cardTrecho.querySelector(".inicio-trecho").value),
        fim_segundos: Number(cardTrecho.querySelector(".fim-trecho").value),
      };
    });
    const total = trechos.reduce(
      (soma, trecho) =>
        soma + (trecho.tipo_midia === "imagem" ? trecho.duracao_segundos : trecho.fim_segundos - trecho.inicio_segundos),
      0
    );
    const algumInvalido = trechos.some((trecho) =>
      trecho.tipo_midia === "imagem"
        ? !(trecho.duracao_segundos >= 2 && trecho.duracao_segundos <= 8)
        : trecho.inicio_segundos < 0 || trecho.fim_segundos - trecho.inicio_segundos < 1
    );
    if (!trechos.length || algumInvalido) {
      alert("Verifique os itens: vídeos precisam de início válido e ao menos 1 segundo; fotos, entre 2 e 8 segundos.");
      return;
    }
    if (total > 60.001) {
      alert("A soma dos itens não pode ultrapassar 60 segundos.");
      return;
    }
    if (!confirm("Gerar uma nova versão preservando o Reel atual?")) return;
    botao.disabled = true;
    botao.textContent = "Iniciando nova renderização...";
    try {
      await chamarAutomacao(`${API_PRODUCAO}/${item.producao_id}/renderizar-revisao`, {
        trechos,
        duracao_maxima: 60,
      });
      revisaoEmAndamento = false;
      await carregarProducao();
    } catch (erro) {
      botao.disabled = false;
      botao.textContent = "Gerar nova versão";
    }
  });
  atualizar();
}

function adicionarMidiaNaLista(painel, producaoId, midia) {
  const lista = painel.querySelector(".lista-trechos-revisao");
  const ordem = lista.querySelectorAll(".trecho-revisao").length + 1;
  const trechoSintetico =
    midia.tipo_midia === "imagem"
      ? {
          ordem,
          tipo_midia: "imagem",
          drive_file_id: midia.drive_file_id,
          arquivo: midia.nome,
          duracao_segundos: 3.0,
          encaixe: "conter",
          novo: true,
        }
      : {
          ordem,
          tipo_midia: "video",
          drive_file_id: midia.drive_file_id,
          arquivo: midia.nome,
          inicio_segundos: 0,
          fim_segundos: 1,
          duracao_segundos: null,
          audio_original: null,
          pontuacao_movimento: null,
          novo: true,
        };
  lista.appendChild(criarTrechoRevisao(trechoSintetico, producaoId));
  atualizarResumoRevisao(painel);
}

async function montarNavegacaoMidia(painel, item) {
  const container = painel.querySelector(".navegacao-midia");
  const breadcrumbEl = container.querySelector(".breadcrumb-pasta");
  const subpastasEl = container.querySelector(".grid-subpastas");
  const midiasEl = container.querySelector(".grid-midias");

  let todasMidias = [];
  let caminhoAtual = "";

  try {
    const resposta = await fetch(`${API_PRODUCAO}/${item.producao_id}/midias-disponiveis`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível listar a mídia da pasta.");
    todasMidias = dados.midias || [];
  } catch (erro) {
    container.innerHTML = `<h5>Adicionar mídia da pasta do sonho</h5><p class="revisao-ajuda">Não foi possível carregar a mídia da pasta: ${escaparHtml(erro.message)}</p>`;
    return;
  }

  function subpastasDiretas(caminho) {
    const prefixo = caminho ? `${caminho}/` : "";
    const nomes = new Set();
    todasMidias.forEach((midia) => {
      if (caminho && !midia.caminho_relativo.startsWith(prefixo)) return;
      const resto = caminho ? midia.caminho_relativo.slice(prefixo.length) : midia.caminho_relativo;
      const barra = resto.indexOf("/");
      if (barra > -1) nomes.add(resto.slice(0, barra));
    });
    return [...nomes].sort();
  }

  function midiasDiretas(caminho) {
    const prefixo = caminho ? `${caminho}/` : "";
    return todasMidias.filter((midia) => {
      if (caminho && !midia.caminho_relativo.startsWith(prefixo)) return false;
      const resto = caminho ? midia.caminho_relativo.slice(prefixo.length) : midia.caminho_relativo;
      return resto.indexOf("/") === -1;
    });
  }

  function renderizarBreadcrumb() {
    const partes = caminhoAtual ? caminhoAtual.split("/") : [];
    let acumulado = "";
    const trilhos = [{ nome: "Raiz", caminho: "" }];
    partes.forEach((parte) => {
      acumulado = acumulado ? `${acumulado}/${parte}` : parte;
      trilhos.push({ nome: parte, caminho: acumulado });
    });
    breadcrumbEl.innerHTML = trilhos
      .map(
        (trilho, indice) => `
      <button type="button" class="item-breadcrumb" data-caminho="${escaparHtml(trilho.caminho)}" ${indice === trilhos.length - 1 ? "disabled" : ""}>
        ${escaparHtml(trilho.nome)}
      </button>`
      )
      .join("<span>/</span>");
    breadcrumbEl.querySelectorAll(".item-breadcrumb").forEach((botao) => {
      botao.addEventListener("click", () => {
        caminhoAtual = botao.dataset.caminho;
        renderizarNavegacao();
      });
    });
  }

  function renderizarNavegacao() {
    renderizarBreadcrumb();
    const subpastas = subpastasDiretas(caminhoAtual);
    subpastasEl.innerHTML = subpastas
      .map((nome) => `<button type="button" class="pasta-item" data-nome="${escaparHtml(nome)}">📁 ${escaparHtml(nome)}</button>`)
      .join("");
    subpastasEl.querySelectorAll(".pasta-item").forEach((botao) => {
      botao.addEventListener("click", () => {
        caminhoAtual = caminhoAtual ? `${caminhoAtual}/${botao.dataset.nome}` : botao.dataset.nome;
        renderizarNavegacao();
      });
    });

    const midias = midiasDiretas(caminhoAtual);
    midiasEl.innerHTML = midias.length
      ? midias
          .map(
            (midia, indice) => `
          <div class="midia-item">
            ${
              midia.tipo_midia === "imagem"
                ? `<img class="midia-thumb-foto" loading="lazy" src="${API_PRODUCAO}/${item.producao_id}/midia-original/${encodeURIComponent(midia.drive_file_id)}" alt="${escaparHtml(midia.nome)}">`
                : `<span class="badge-tipo-midia badge-video">VÍDEO</span>`
            }
            <span class="midia-nome">${escaparHtml(midia.nome)}</span>
            <button type="button" class="botao-adicionar-midia" data-indice="${indice}">+ Adicionar</button>
          </div>`
          )
          .join("")
      : `<p class="revisao-ajuda">Nenhuma mídia diretamente nesta pasta.</p>`;

    midiasEl.querySelectorAll(".botao-adicionar-midia").forEach((botao) => {
      botao.addEventListener("click", () => {
        const midia = midias[Number(botao.dataset.indice)];
        adicionarMidiaNaLista(painel, item.producao_id, midia);
      });
    });
  }

  renderizarNavegacao();
}

// =========================================================
// PRÉVIA SEQUENCIAL DA REVISÃO (foto + vídeo, sem gerar MP4)
// =========================================================
// Lê a ordem, os cortes de vídeo e a duração das fotos diretamente dos
// cards visíveis no momento em que a prévia é aberta — nunca do servidor —
// para sempre refletir a seleção atual da interface, incluindo edições
// ainda não salvas. Não usa FFmpeg nem gera nenhum arquivo: só alterna um
// <video>/<img> reaproveitando as mesmas URLs de preview já usadas nos
// cards (video-original/midia-original).

let sequenciaPreviaReels = [];
let indicePreviaReelsAtual = 0;
let geracaoPreviaReels = 0;
let previaReelsTocando = false;
let timeoutFotoPreviaReels = null;
let fotoPreviaReelsInicioTs = 0;
let fotoPreviaReelsRestanteMs = 0;
let seekEmAndamentoPreviaReels = false;

function limparTimerFotoPreviaReels() {
  if (timeoutFotoPreviaReels) {
    clearTimeout(timeoutFotoPreviaReels);
    timeoutFotoPreviaReels = null;
  }
}

function iniciarTimerFotoPreviaReels(duracaoMs, geracaoAlvo) {
  limparTimerFotoPreviaReels();
  fotoPreviaReelsInicioTs = performance.now();
  fotoPreviaReelsRestanteMs = duracaoMs;
  timeoutFotoPreviaReels = setTimeout(() => {
    if (geracaoAlvo !== geracaoPreviaReels) return;
    avancarAutoPreviaReels();
  }, duracaoMs);
}

function pausarTimerFotoPreviaReels() {
  if (timeoutFotoPreviaReels) {
    fotoPreviaReelsRestanteMs = Math.max(0, fotoPreviaReelsRestanteMs - (performance.now() - fotoPreviaReelsInicioTs));
  }
  limparTimerFotoPreviaReels();
}

function garantirModalPreviaReels() {
  let modal = document.getElementById("modal-previa-reels");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "modal-previa-reels";
  modal.className = "modal-previa";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="modal-previa-conteudo">
      <div class="modal-previa-cabecalho">
        <span id="previa-reels-titulo">Item 1 de 1</span>
        <button type="button" id="previa-reels-fechar" class="botao-fechar-previa" aria-label="Fechar prévia">✕</button>
      </div>
      <div class="previa-reels-info">
        <span id="previa-reels-badge" class="badge-tipo-midia badge-video">VÍDEO</span>
        <span id="previa-reels-nome"></span>
      </div>
      <video id="previa-reels-video" class="previa-sequencia-video" playsinline></video>
      <img id="previa-reels-imagem" class="previa-sequencia-video" alt="" hidden>
      <div class="previa-sequencia-navegacao">
        <button type="button" id="previa-reels-anterior" class="botao-card">‹ Anterior</button>
        <button type="button" id="previa-reels-playpause" class="botao-card">▶ Play</button>
        <button type="button" id="previa-reels-proxima" class="botao-card">Próximo ›</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const video = modal.querySelector("#previa-reels-video");
  video.addEventListener("timeupdate", () => {
    // Ignora leituras durante um seek em andamento: setar currentTime não
    // atualiza o valor lido por um timeupdate instantaneamente, então um
    // evento pode chegar ainda com o tempo ANTIGO (ex.: reaproveitando o
    // mesmo <video> de um item anterior que tinha parado bem no fim) e
    // avançar o item errado antes do seek de fato completar.
    if (seekEmAndamentoPreviaReels) return;
    const itemAtual = sequenciaPreviaReels[indicePreviaReelsAtual];
    if (!itemAtual || itemAtual.tipoMidia !== "video" || video.readyState < 1) return;
    if (video.currentTime >= itemAtual.fim) {
      avancarAutoPreviaReels();
    }
  });
  video.addEventListener("play", () => {
    const itemAtual = sequenciaPreviaReels[indicePreviaReelsAtual];
    if (itemAtual && itemAtual.tipoMidia === "video" && (video.currentTime < itemAtual.inicio || video.currentTime >= itemAtual.fim)) {
      video.currentTime = itemAtual.inicio;
    }
  });

  modal.querySelector("#previa-reels-fechar").addEventListener("click", fecharPreviaSequenciaReels);
  modal.querySelector("#previa-reels-anterior").addEventListener("click", () => {
    if (indicePreviaReelsAtual > 0) carregarItemPreviaReels(indicePreviaReelsAtual - 1);
  });
  modal.querySelector("#previa-reels-proxima").addEventListener("click", () => {
    if (indicePreviaReelsAtual < sequenciaPreviaReels.length - 1) carregarItemPreviaReels(indicePreviaReelsAtual + 1);
  });
  modal.querySelector("#previa-reels-playpause").addEventListener("click", alternarPlayPausePreviaReels);

  return modal;
}

function construirSequenciaPreviaReels(painel) {
  return [...painel.querySelectorAll(".trecho-revisao")]
    .map((card) => {
      const tipoMidia = card.dataset.tipoMidia;
      const nomeEl = card.querySelector(".nome-arquivo-trecho");
      const nome = nomeEl ? nomeEl.textContent : "";
      const midiaEl = card.querySelector("video, img");
      const url = midiaEl ? midiaEl.getAttribute("src") : "";
      if (tipoMidia === "imagem") {
        const duracao = Number(card.querySelector(".duracao-foto").value) || 0;
        return { tipoMidia, nome, url, duracao };
      }
      const inicio = Number(card.querySelector(".inicio-trecho").value) || 0;
      const fim = Number(card.querySelector(".fim-trecho").value) || 0;
      return { tipoMidia, nome, url, inicio, fim };
    })
    .filter((itemPrevia) =>
      itemPrevia.tipoMidia === "imagem" ? itemPrevia.duracao > 0 : itemPrevia.fim > itemPrevia.inicio
    );
}

function abrirPreviaSequenciaReels(painel) {
  sequenciaPreviaReels = construirSequenciaPreviaReels(painel);
  if (!sequenciaPreviaReels.length) {
    alert("Nenhum item válido para pré-visualizar (verifique início/fim dos vídeos e a duração das fotos).");
    return;
  }
  const modal = garantirModalPreviaReels();
  modal.hidden = false;
  previaReelsTocando = false;
  carregarItemPreviaReels(0);
  atualizarBotaoPlayPausePreviaReels();
}

function fecharPreviaSequenciaReels() {
  const modal = document.getElementById("modal-previa-reels");
  if (!modal) return;
  const video = modal.querySelector("#previa-reels-video");
  video.pause();
  video.removeAttribute("src");
  video.load();
  limparTimerFotoPreviaReels();
  previaReelsTocando = false;
  modal.hidden = true;
}

function atualizarBotaoPlayPausePreviaReels() {
  const modal = document.getElementById("modal-previa-reels");
  modal.querySelector("#previa-reels-playpause").textContent = previaReelsTocando ? "⏸ Pausar" : "▶ Play";
}

function alternarPlayPausePreviaReels() {
  const modal = document.getElementById("modal-previa-reels");
  const video = modal.querySelector("#previa-reels-video");
  const itemAtual = sequenciaPreviaReels[indicePreviaReelsAtual];
  previaReelsTocando = !previaReelsTocando;
  atualizarBotaoPlayPausePreviaReels();
  if (!itemAtual) return;
  if (itemAtual.tipoMidia === "video") {
    if (previaReelsTocando) video.play();
    else video.pause();
  } else if (previaReelsTocando) {
    iniciarTimerFotoPreviaReels(fotoPreviaReelsRestanteMs, geracaoPreviaReels);
  } else {
    pausarTimerFotoPreviaReels();
  }
}

function avancarAutoPreviaReels() {
  if (indicePreviaReelsAtual < sequenciaPreviaReels.length - 1) {
    carregarItemPreviaReels(indicePreviaReelsAtual + 1);
  } else {
    previaReelsTocando = false;
    atualizarBotaoPlayPausePreviaReels();
    limparTimerFotoPreviaReels();
    const modal = document.getElementById("modal-previa-reels");
    modal.querySelector("#previa-reels-video").pause();
  }
}

function carregarItemPreviaReels(indice) {
  indicePreviaReelsAtual = indice;
  geracaoPreviaReels += 1;
  const geracaoAlvo = geracaoPreviaReels;
  const itemAtual = sequenciaPreviaReels[indice];
  const modal = garantirModalPreviaReels();
  const video = modal.querySelector("#previa-reels-video");
  const imagem = modal.querySelector("#previa-reels-imagem");

  modal.querySelector("#previa-reels-titulo").textContent = `Item ${indice + 1} de ${sequenciaPreviaReels.length}`;
  modal.querySelector("#previa-reels-nome").textContent = itemAtual.nome;
  const badge = modal.querySelector("#previa-reels-badge");
  badge.textContent = itemAtual.tipoMidia === "imagem" ? "FOTO" : "VÍDEO";
  badge.className = "badge-tipo-midia " + (itemAtual.tipoMidia === "imagem" ? "badge-foto" : "badge-video");
  modal.querySelector("#previa-reels-anterior").disabled = indice === 0;
  modal.querySelector("#previa-reels-proxima").disabled = indice === sequenciaPreviaReels.length - 1;

  limparTimerFotoPreviaReels();
  video.pause();

  if (itemAtual.tipoMidia === "imagem") {
    video.hidden = true;
    imagem.hidden = false;
    imagem.src = itemAtual.url;
    fotoPreviaReelsRestanteMs = itemAtual.duracao * 1000;
    if (previaReelsTocando) iniciarTimerFotoPreviaReels(fotoPreviaReelsRestanteMs, geracaoAlvo);
    return;
  }

  imagem.hidden = true;
  video.hidden = false;
  const iniciarNoTrecho = () => {
    if (geracaoAlvo !== geracaoPreviaReels) return;
    seekEmAndamentoPreviaReels = true;
    let seekFinalizado = false;
    const finalizarSeek = () => {
      if (seekFinalizado) return;
      seekFinalizado = true;
      video.removeEventListener("seeked", finalizarSeek);
      seekEmAndamentoPreviaReels = false;
      if (geracaoAlvo !== geracaoPreviaReels) return;
      if (previaReelsTocando) video.play();
    };
    video.addEventListener("seeked", finalizarSeek, { once: true });
    video.currentTime = itemAtual.inicio;
    // Salvaguarda: alguns navegadores não disparam "seeked" quando o valor
    // pedido já é (ou está muito perto de) o currentTime atual.
    setTimeout(finalizarSeek, 300);
  };
  if (video.src !== itemAtual.url) {
    video.src = itemAtual.url;
    video.addEventListener("loadedmetadata", iniciarNoTrecho, { once: true });
  } else {
    iniciarNoTrecho();
  }
}

function formatarTempoVideo(segundos) {
  const valor = Math.max(0, Number(segundos) || 0);
  const minutos = Math.floor(valor / 60);
  const restante = valor - minutos * 60;
  return `${String(minutos).padStart(2, "0")}:${restante.toFixed(2).padStart(5, "0")}`;
}

function urlPreviaMidia(producaoId, trecho) {
  // Itens já salvos no relatório da revisão em andamento usam o endpoint
  // antigo (que exige o arquivo já estar no relatório). Fotos e itens novos
  // (ainda não renderizados) usam o endpoint novo, que autoriza por
  // ancestralidade real no Drive em vez de checar o relatório.
  if (trecho.tipo_midia === "imagem" || trecho.novo) {
    return `${API_PRODUCAO}/${producaoId}/midia-original/${encodeURIComponent(trecho.drive_file_id)}`;
  }
  return `${API_PRODUCAO}/${producaoId}/video-original/${encodeURIComponent(trecho.drive_file_id)}`;
}

function criarTrechoRevisaoFoto(trecho, producaoId) {
  const card = document.createElement("article");
  card.className = "trecho-revisao";
  card.dataset.fileId = trecho.drive_file_id;
  card.dataset.tipoMidia = "imagem";
  const duracao = Number(trecho.duracao_segundos ?? 3.0);
  const encaixe = trecho.encaixe === "cobrir" ? "cobrir" : "conter";
  card.innerHTML = `
    <div class="trecho-cabecalho">
      <strong class="ordem-trecho">Trecho ${trecho.ordem}</strong>
      <span class="badge-tipo-midia badge-foto">FOTO</span>
      <span class="nome-arquivo-trecho">${escaparHtml(trecho.arquivo)}</span>
    </div>
    <img class="previa-foto" loading="lazy" alt="${escaparHtml(trecho.arquivo)}"
      src="${urlPreviaMidia(producaoId, trecho)}">
    <div class="campos-trecho">
      <label>Duração (s)
        <input class="duracao-foto" type="number" min="2" max="8" step="0.1" value="${duracao}">
      </label>
      <label>Encaixe
        <select class="encaixe-foto">
          <option value="conter" ${encaixe === "conter" ? "selected" : ""}>Conter</option>
          <option value="cobrir" ${encaixe === "cobrir" ? "selected" : ""}>Cobrir</option>
        </select>
      </label>
    </div>
    <div class="metadados-trecho">
      <span class="duracao-trecho">${duracao.toFixed(3)}s</span>
    </div>
    <div class="acoes-trecho">
      <button type="button" class="mover-cima">Mover para cima</button>
      <button type="button" class="mover-baixo">Mover para baixo</button>
      <button type="button" class="remover-trecho">Remover trecho</button>
    </div>
  `;
  card.querySelector(".mover-cima").addEventListener("click", () => {
    if (card.previousElementSibling) card.parentElement.insertBefore(card, card.previousElementSibling);
    atualizarResumoRevisao(card.closest(".revisao-trechos"));
  });
  card.querySelector(".mover-baixo").addEventListener("click", () => {
    if (card.nextElementSibling) card.parentElement.insertBefore(card.nextElementSibling, card);
    atualizarResumoRevisao(card.closest(".revisao-trechos"));
  });
  card.querySelector(".remover-trecho").addEventListener("click", () => {
    const painel = card.closest(".revisao-trechos");
    card.remove();
    atualizarResumoRevisao(painel);
  });
  return card;
}

function criarTrechoRevisao(trecho, producaoId) {
  if (trecho.tipo_midia === "imagem") {
    return criarTrechoRevisaoFoto(trecho, producaoId);
  }
  const card = document.createElement("article");
  card.className = "trecho-revisao";
  card.dataset.fileId = trecho.drive_file_id;
  card.dataset.tipoMidia = "video";
  const alternativas = trecho.alternativas || [];
  const inicioInicial = trecho.inicio_segundos ?? 0;
  const fimInicial = trecho.fim_segundos ?? 1;
  card.innerHTML = `
    <div class="trecho-cabecalho">
      <strong class="ordem-trecho">Trecho ${trecho.ordem}</strong>
      <span class="badge-tipo-midia badge-video">VÍDEO</span>
      <span class="nome-arquivo-trecho">${escaparHtml(trecho.arquivo)}</span>
    </div>
    <video class="previa-trecho" controls preload="none"
      src="${urlPreviaMidia(producaoId, trecho)}"></video>
    <div class="tempo-atual">Tempo atual: 00:00.00</div>
    <div class="marcadores-trecho">
      <button type="button" class="marcar-inicio">Marcar início aqui</button>
      <button type="button" class="marcar-fim">Marcar fim aqui</button>
    </div>
    <div class="selecao-visual">
      <span>Início selecionado: <strong class="inicio-formatado">${formatarTempoVideo(inicioInicial)}</strong></span>
      <span>Fim selecionado: <strong class="fim-formatado">${formatarTempoVideo(fimInicial)}</strong></span>
      <span>Duração: <strong class="duracao-formatada">${(fimInicial - inicioInicial).toFixed(2)}s</strong></span>
    </div>
    <div class="campos-trecho">
      <label>Início <input class="inicio-trecho" type="number" min="0" step="0.001" value="${inicioInicial}"></label>
      <label>Fim <input class="fim-trecho" type="number" min="1" step="0.001" value="${fimInicial}"></label>
    </div>
    <div class="metadados-trecho">
      <span class="duracao-trecho">${(fimInicial - inicioInicial).toFixed(3)}s</span>
      <span>Movimento: ${trecho.pontuacao_movimento == null ? "—" : Number(trecho.pontuacao_movimento).toFixed(2)}</span>
      <span>Áudio: ${trecho.audio_original == null ? "—" : (trecho.audio_original ? "sim" : "não")}</span>
    </div>
    <label class="alternativas-trecho">
      Usar outro trecho deste vídeo
      <select ${alternativas.length ? "" : "disabled"}>
        <option value="">Selecione uma alternativa</option>
        ${alternativas.map((alternativa) => `
          <option value="${alternativa.inicio_segundos}|${alternativa.fim_segundos}">
            ${Number(alternativa.inicio_segundos).toFixed(3)}s–${Number(alternativa.fim_segundos).toFixed(3)}s · movimento ${Number(alternativa.pontuacao_movimento || 0).toFixed(2)}
          </option>`).join("")}
      </select>
      ${alternativas.length ? "" : `<small>${trecho.novo ? "Vídeo adicionado manualmente — sem alternativas automáticas; use os marcadores abaixo." : "Alternativas não registradas nesta versão antiga; ajuste início e fim manualmente."}</small>`}
    </label>
    <button type="button" class="previsualizar-selecao">Pré-visualizar trecho</button>
    <div class="acoes-trecho">
      <button type="button" class="mover-cima">Mover para cima</button>
      <button type="button" class="mover-baixo">Mover para baixo</button>
      <button type="button" class="remover-trecho">Remover trecho</button>
    </div>
  `;
  const player = card.querySelector(".previa-trecho");
  player.addEventListener("timeupdate", () => {
    card.querySelector(".tempo-atual").textContent = `Tempo atual: ${formatarTempoVideo(player.currentTime)}`;
    if (
      card.dataset.previsualizando === "true" &&
      player.currentTime >= Number(card.querySelector(".fim-trecho").value)
    ) {
      player.pause();
      card.dataset.previsualizando = "false";
    }
  });
  card.querySelector(".marcar-inicio").addEventListener("click", () => {
    card.querySelector(".inicio-trecho").value = player.currentTime.toFixed(3);
    card.dispatchEvent(new Event("input", { bubbles: true }));
  });
  card.querySelector(".marcar-fim").addEventListener("click", () => {
    card.querySelector(".fim-trecho").value = player.currentTime.toFixed(3);
    card.dispatchEvent(new Event("input", { bubbles: true }));
  });
  card.querySelector(".previsualizar-selecao").addEventListener("click", async () => {
    const inicio = Number(card.querySelector(".inicio-trecho").value);
    const fim = Number(card.querySelector(".fim-trecho").value);
    if (inicio < 0 || fim <= inicio || (Number.isFinite(player.duration) && fim > player.duration + 0.05)) {
      alert("Defina um início e um fim válidos dentro da duração do vídeo.");
      return;
    }
    player.pause();
    player.currentTime = inicio;
    card.dataset.previsualizando = "true";
    try {
      await player.play();
    } catch (erro) {
      card.dataset.previsualizando = "false";
      alert("Não foi possível reproduzir a seleção.");
    }
  });
  const select = card.querySelector("select");
  select.addEventListener("change", () => {
    if (!select.value) return;
    const [inicio, fim] = select.value.split("|");
    card.querySelector(".inicio-trecho").value = inicio;
    card.querySelector(".fim-trecho").value = fim;
    card.dispatchEvent(new Event("input", { bubbles: true }));
  });
  card.querySelector(".mover-cima").addEventListener("click", () => {
    if (card.previousElementSibling) card.parentElement.insertBefore(card, card.previousElementSibling);
    atualizarResumoRevisao(card.closest(".revisao-trechos"));
  });
  card.querySelector(".mover-baixo").addEventListener("click", () => {
    if (card.nextElementSibling) card.parentElement.insertBefore(card.nextElementSibling, card);
    atualizarResumoRevisao(card.closest(".revisao-trechos"));
  });
  card.querySelector(".remover-trecho").addEventListener("click", () => {
    const painel = card.closest(".revisao-trechos");
    card.remove();
    atualizarResumoRevisao(painel);
  });
  return card;
}

function atualizarResumoRevisao(painel) {
  if (!painel) return;
  let total = 0;
  painel.querySelectorAll(".trecho-revisao").forEach((card, indice) => {
    card.querySelector(".ordem-trecho").textContent = `Trecho ${indice + 1}`;
    let duracao;
    if (card.dataset.tipoMidia === "imagem") {
      duracao = Math.max(0, Number(card.querySelector(".duracao-foto").value) || 0);
    } else {
      duracao = Math.max(0, Number(card.querySelector(".fim-trecho").value) - Number(card.querySelector(".inicio-trecho").value));
      card.querySelector(".inicio-formatado").textContent = formatarTempoVideo(card.querySelector(".inicio-trecho").value);
      card.querySelector(".fim-formatado").textContent = formatarTempoVideo(card.querySelector(".fim-trecho").value);
    }
    card.querySelector(".duracao-trecho").textContent = `${duracao.toFixed(3)}s`;
    const duracaoFormatada = card.querySelector(".duracao-formatada");
    if (duracaoFormatada) duracaoFormatada.textContent = `${duracao.toFixed(2)}s`;
    total += duracao;
  });
  const resumo = painel.querySelector(".total-revisao");
  resumo.textContent = `${painel.querySelectorAll(".trecho-revisao").length} itens · ${total.toFixed(3)} segundos`;
  resumo.classList.toggle("total-invalido", total > 60);
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

setInterval(() => {
  if (document.visibilityState === "visible" && !revisaoEmAndamento) {
    carregarProducao();
  }
}, 15000);
