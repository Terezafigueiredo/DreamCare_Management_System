const API_BASE = "http://127.0.0.1:8080";
const API_INSTITUCIONAL = `${API_BASE}/institucional`;

const LIMIAR_TRECHO_CURTO_SEGUNDOS = 1.0;
const DURACAO_ALVO_MINIMA_SEGUNDOS = 105; // 1min45s
const DURACAO_ALVO_MAXIMA_SEGUNDOS = 135; // 2min15s
const ATRASO_AUTOSAVE_MS = 1500;

// Mesmo padrão de compatibilidade do backend (video_institucional_render.py):
// trecho antigo sem transicao_entrada/duracao_transicao é tratado como corte
// simples com a duração padrão abaixo.
const TRANSICAO_PADRAO = "corte";
const DURACAO_TRANSICAO_PADRAO_SEGUNDOS = 0.6;
const OPCOES_DURACAO_TRANSICAO = [0.4, 0.6, 0.8, 1.0];

const SECOES = [
  { valor: "DREAMS", rotulo: "DREAMS (abertura)" },
  { valor: "PURPOSE_EACH_PERSON", rotulo: "PURPOSE / EACH / PERSON" },
  { valor: "SACRED_FAITH", rotulo: "SACRED / FAITH" },
  { valor: "JOY_FULFILLMENT", rotulo: "JOY / FULFILLMENT" },
  { valor: "ROPE_ENCERRAMENTO", rotulo: "ROPE / Encerramento" },
];

// =========================================================
// ESTADO
// =========================================================

let producaoAtual = null; // objeto completo retornado pela API
let trechos = []; // cópia local da seleção editorial em edição
let sonhos = []; // cache de /institucional/sonhos
let sonhoSelecionado = null;
let videos = []; // vídeos do sonho selecionado
let videoSelecionado = null;
let termoBusca = "";
let temAlteracoesPendentes = false;
let timerAutosave = null;

// =========================================================
// UTILITÁRIOS
// =========================================================

function escaparHtml(valor) {
  const elemento = document.createElement("span");
  elemento.textContent = String(valor ?? "");
  return elemento.innerHTML;
}

function formatarTempo(segundos) {
  const valor = Math.max(0, Number(segundos) || 0);
  const minutos = Math.floor(valor / 60);
  const restante = valor - minutos * 60;
  return `${String(minutos).padStart(2, "0")}:${restante.toFixed(2).padStart(5, "0")}`;
}

function formatarTamanho(bytes) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

function mostrarMensagemGlobal(texto) {
  const elemento = document.getElementById("mensagem-global");
  if (!texto) {
    elemento.hidden = true;
    elemento.textContent = "";
    return;
  }
  elemento.hidden = false;
  elemento.textContent = texto;
}

function preencherSelectSecoes(select) {
  select.innerHTML = "";
  SECOES.forEach(({ valor, rotulo }) => {
    const opcao = document.createElement("option");
    opcao.value = valor;
    opcao.textContent = rotulo;
    select.appendChild(opcao);
  });
}

function atualizarUrl(id) {
  const url = new URL(window.location.href);
  if (id) {
    url.searchParams.set("id", id);
  } else {
    url.searchParams.delete("id");
  }
  window.history.replaceState({}, "", url);
}

// =========================================================
// PRODUÇÃO INSTITUCIONAL (criar/abrir)
// =========================================================

async function carregarProducoes(selecionarId) {
  const select = document.getElementById("select-producao");
  try {
    const resposta = await fetch(API_INSTITUCIONAL);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível listar as produções.");

    select.innerHTML = '<option value="">Selecione...</option>';
    (dados.resultados || []).forEach((producao) => {
      const opcao = document.createElement("option");
      opcao.value = producao.id;
      opcao.textContent = `#${producao.id} — ${producao.titulo} (${producao.quantidade_trechos} trechos)`;
      select.appendChild(opcao);
    });

    if (selecionarId) {
      select.value = String(selecionarId);
    }
  } catch (erro) {
    mostrarMensagemGlobal(erro.message);
  }
}

async function criarNovaProducao() {
  const titulo = window.prompt("Título da nova produção institucional:");
  if (!titulo || !titulo.trim()) return;

  try {
    const resposta = await fetch(API_INSTITUCIONAL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: titulo.trim() }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível criar a produção.");

    await carregarProducoes(dados.id);
    await selecionarProducao(dados.id);
  } catch (erro) {
    alert(erro.message);
  }
}

async function selecionarProducao(id) {
  if (timerAutosave) {
    clearTimeout(timerAutosave);
    timerAutosave = null;
  }

  if (!id) {
    producaoAtual = null;
    trechos = [];
    sonhoSelecionado = null;
    esconderPlayer();
    document.getElementById("status-producao").textContent = "Nenhuma produção selecionada.";
    document.getElementById("lista-videos-sonho").innerHTML = "";
    document.getElementById("titulo-sonho-selecionado").textContent =
      "Selecione um sonho à esquerda para ver os vídeos.";
    atualizarUrl(null);
    atualizarListaSonhos();
    renderizarTrechos();
    return;
  }

  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/${id}`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível carregar a produção.");

    producaoAtual = dados;
    trechos = (dados.selecao_editorial || []).map((trecho) => ({ ...trecho }));
    document.getElementById("status-producao").textContent =
      `#${dados.id} — ${dados.titulo} (status: ${dados.status})`;
    document.getElementById("select-producao").value = String(id);
    atualizarUrl(id);
    marcarComoSalvo();
    renderizarTrechos();
    mostrarMensagemGlobal(null);
  } catch (erro) {
    mostrarMensagemGlobal(erro.message);
  }
}

// =========================================================
// SONHOS DISPONÍVEIS
// =========================================================

async function carregarSonhos() {
  const container = document.getElementById("lista-sonhos");
  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/sonhos`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível carregar os sonhos.");

    sonhos = dados.resultados || [];
    atualizarListaSonhos();
  } catch (erro) {
    container.innerHTML = `<div class="vazio">${escaparHtml(erro.message)}</div>`;
  }
}

function sonhosVisiveis() {
  if (!termoBusca) return sonhos;
  return sonhos.filter(
    (sonho) =>
      (sonho.nome || "").toLowerCase().includes(termoBusca) ||
      (sonho.sonho || "").toLowerCase().includes(termoBusca)
  );
}

function atualizarListaSonhos() {
  renderizarSonhos(sonhosVisiveis());
}

function renderizarSonhos(lista) {
  const container = document.getElementById("lista-sonhos");
  container.innerHTML = "";

  if (!lista.length) {
    container.innerHTML = '<div class="vazio">Nenhum sonho encontrado.</div>';
    return;
  }

  lista.forEach((sonho) => {
    const item = document.createElement("div");
    item.className = "item-sonho";
    if (sonhoSelecionado && sonhoSelecionado.id === sonho.id) {
      item.classList.add("selecionado");
    }
    item.innerHTML = `
      <strong>${escaparHtml(sonho.nome || "Sem nome")}${
      sonho.idade != null ? ` (${sonho.idade} anos)` : ""
    }</strong>
      <span>${escaparHtml(sonho.sonho || "")}</span>
    `;
    item.addEventListener("click", () => selecionarSonho(sonho));
    container.appendChild(item);
  });
}

async function selecionarSonho(sonho) {
  if (!producaoAtual) {
    alert("Crie ou selecione uma produção institucional antes de escolher um sonho.");
    return;
  }

  sonhoSelecionado = sonho;
  atualizarListaSonhos();
  document.getElementById("titulo-sonho-selecionado").textContent = `Vídeos de: ${sonho.nome}`;
  esconderPlayer();

  const listaVideos = document.getElementById("lista-videos-sonho");
  listaVideos.innerHTML = '<div class="vazio">Carregando vídeos...</div>';

  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/sonhos/${sonho.id}/videos`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível carregar os vídeos.");
    renderizarVideos(dados.videos || []);
  } catch (erro) {
    listaVideos.innerHTML = `<div class="vazio">${escaparHtml(erro.message)}</div>`;
  }
}

// =========================================================
// VÍDEOS DO SONHO + PLAYER PRINCIPAL
// =========================================================

function renderizarVideos(lista) {
  videos = lista;
  const container = document.getElementById("lista-videos-sonho");
  container.innerHTML = "";

  if (!lista.length) {
    container.innerHTML = '<div class="vazio">Nenhum vídeo encontrado nesta pasta.</div>';
    return;
  }

  lista.forEach((video) => {
    const item = document.createElement("div");
    item.className = "item-video";
    if (videoSelecionado && videoSelecionado.drive_file_id === video.drive_file_id) {
      item.classList.add("selecionado");
    }
    item.innerHTML = `
      <span class="caminho-video">${escaparHtml(video.caminho_relativo)}</span>
      <span class="tamanho-video">${formatarTamanho(video.tamanho_bytes)}</span>
    `;
    item.addEventListener("click", () => selecionarVideo(video));
    container.appendChild(item);
  });
}

function selecionarVideo(video) {
  videoSelecionado = video;
  renderizarVideos(videos);

  const area = document.getElementById("area-player");
  area.hidden = false;
  document.getElementById("titulo-video-selecionado").textContent = video.caminho_relativo;

  const player = document.getElementById("player-principal");
  player.src = `${API_INSTITUCIONAL}/${producaoAtual.id}/sonhos/${sonhoSelecionado.id}/video-original/${encodeURIComponent(
    video.drive_file_id
  )}`;

  document.getElementById("inicio-novo").value = "0";
  document.getElementById("fim-novo").value = "0";
  document.getElementById("audio-novo").checked = false;
  document.getElementById("alerta-novo-trecho").hidden = true;
  document.getElementById("botao-adicionar-trecho").disabled = false;
}

function esconderPlayer() {
  videoSelecionado = null;
  videos = [];
  document.getElementById("area-player").hidden = true;
  const player = document.getElementById("player-principal");
  player.pause();
  player.removeAttribute("src");
  player.load();
}

const playerPrincipal = document.getElementById("player-principal");
playerPrincipal.addEventListener("timeupdate", () => {
  document.getElementById("tempo-atual-principal").textContent =
    `Tempo atual: ${formatarTempo(playerPrincipal.currentTime)}`;
});

document.getElementById("marcar-inicio-principal").addEventListener("click", () => {
  document.getElementById("inicio-novo").value = playerPrincipal.currentTime.toFixed(3);
  validarNovoTrecho();
});

document.getElementById("marcar-fim-principal").addEventListener("click", () => {
  document.getElementById("fim-novo").value = playerPrincipal.currentTime.toFixed(3);
  validarNovoTrecho();
});

document.getElementById("inicio-novo").addEventListener("input", validarNovoTrecho);
document.getElementById("fim-novo").addEventListener("input", validarNovoTrecho);

function validarNovoTrecho() {
  const inicio = Number(document.getElementById("inicio-novo").value);
  const fim = Number(document.getElementById("fim-novo").value);
  const alerta = document.getElementById("alerta-novo-trecho");
  const botao = document.getElementById("botao-adicionar-trecho");

  if (!(fim > inicio)) {
    alerta.hidden = false;
    alerta.className = "alerta alerta-erro";
    alerta.textContent = "O fim deve ser maior que o início.";
    botao.disabled = true;
    return false;
  }

  if (fim - inicio < LIMIAR_TRECHO_CURTO_SEGUNDOS) {
    alerta.hidden = false;
    alerta.className = "alerta alerta-atencao";
    alerta.textContent = `Trecho muito curto (${(fim - inicio).toFixed(2)}s). Considere ampliar o intervalo.`;
    botao.disabled = false;
    return true;
  }

  alerta.hidden = true;
  botao.disabled = false;
  return true;
}

document.getElementById("botao-adicionar-trecho").addEventListener("click", () => {
  if (!validarNovoTrecho() || !videoSelecionado || !sonhoSelecionado || !producaoAtual) return;

  const inicio = Number(document.getElementById("inicio-novo").value);
  const fim = Number(document.getElementById("fim-novo").value);

  trechos.push({
    sonho_id: sonhoSelecionado.id,
    drive_folder_id: sonhoSelecionado.drive_folder_id,
    drive_file_id: videoSelecionado.drive_file_id,
    nome_arquivo: videoSelecionado.caminho_relativo,
    inicio_segundos: inicio,
    fim_segundos: fim,
    ordem: trechos.length + 1,
    secao: document.getElementById("secao-novo").value,
    manter_audio_original: document.getElementById("audio-novo").checked,
    encaixe: document.getElementById("encaixe-novo").value,
    transicao_entrada: TRANSICAO_PADRAO,
    duracao_transicao: DURACAO_TRANSICAO_PADRAO_SEGUNDOS,
  });

  renderizarTrechos();
  marcarAlteracaoPendente();

  // Deixa pronto para marcar o próximo trecho a partir daqui, útil para
  // selecionar vários recortes seguidos do mesmo vídeo.
  document.getElementById("inicio-novo").value = fim.toFixed(3);
  document.getElementById("fim-novo").value = fim.toFixed(3);
  document.getElementById("audio-novo").checked = false;
  validarNovoTrecho();
});

// =========================================================
// TIMELINE EDITORIAL (coluna lateral)
// =========================================================

function renderizarTrechos() {
  const container = document.getElementById("lista-trechos");
  container.innerHTML = "";

  if (!trechos.length) {
    container.innerHTML = '<div class="vazio">Nenhum trecho selecionado ainda.</div>';
  } else {
    trechos.forEach((trecho, indice) => {
      trecho.ordem = indice + 1;
      container.appendChild(criarCardTrecho(trecho, indice));
    });
  }

  atualizarResumoDuracao();
}

function criarCardTrecho(trecho, indice) {
  const sonhoInfo = sonhos.find((item) => item.id === trecho.sonho_id);
  const nomeSonho = sonhoInfo ? sonhoInfo.nome : `Sonho #${trecho.sonho_id}`;
  const duracao = trecho.fim_segundos - trecho.inicio_segundos;
  const invalido = !(duracao > 0);
  const curto = !invalido && duracao < LIMIAR_TRECHO_CURTO_SEGUNDOS;

  const previewUrl = producaoAtual
    ? `${API_INSTITUCIONAL}/${producaoAtual.id}/sonhos/${trecho.sonho_id}/video-original/${encodeURIComponent(
        trecho.drive_file_id
      )}`
    : "";

  const card = document.createElement("article");
  card.className = "trecho-editorial" + (invalido ? " trecho-invalido" : "");

  card.innerHTML = `
    <div class="trecho-cabecalho">
      <strong>#${trecho.ordem} · ${escaparHtml(nomeSonho)}</strong>
      <span class="caminho-trecho">${escaparHtml(trecho.nome_arquivo || trecho.drive_file_id)}</span>
    </div>

    <video class="previa-trecho" controls preload="none" src="${previewUrl}"></video>
    <div class="tempo-atual">Tempo atual: 00:00.00</div>

    <div class="marcadores-trecho">
      <button type="button" class="marcar-inicio">Marcar início aqui</button>
      <button type="button" class="marcar-fim">Marcar fim aqui</button>
    </div>

    <div class="campos-trecho">
      <label>Início (s)
        <input type="number" class="inicio-trecho" min="0" step="0.001" value="${trecho.inicio_segundos}">
      </label>
      <label>Fim (s)
        <input type="number" class="fim-trecho" min="0" step="0.001" value="${trecho.fim_segundos}">
      </label>
    </div>

    <div class="campos-trecho">
      <label>Seção
        <select class="secao-trecho"></select>
      </label>
      <label>Encaixe
        <select class="encaixe-trecho">
          <option value="cobrir">Cobrir</option>
          <option value="conter">Conter</option>
        </select>
      </label>
    </div>

    <label class="linha-checkbox">
      <input type="checkbox" class="audio-trecho" ${trecho.manter_audio_original ? "checked" : ""}>
      Manter áudio original
    </label>

    ${
      indice === 0
        ? '<p class="nota-primeiro-trecho">Primeiro trecho — sem transição de entrada.</p>'
        : `
    <div class="campos-trecho">
      <label>Transição de entrada
        <select class="transicao-trecho">
          <option value="corte">Corte</option>
          <option value="dissolve">Dissolve</option>
        </select>
      </label>
      <label class="campo-duracao-transicao">Duração da transição
        <select class="duracao-transicao-trecho">
          ${OPCOES_DURACAO_TRANSICAO.map(
            (valor) => `<option value="${valor}">${valor.toFixed(1)}s</option>`
          ).join("")}
        </select>
      </label>
    </div>
    `
    }

    <div class="metadados-trecho">
      <span class="duracao-trecho">${duracao > 0 ? duracao.toFixed(2) : "0.00"}s</span>
      ${invalido ? '<span class="alerta-trecho">⚠ fim ≤ início</span>' : ""}
      ${curto ? '<span class="alerta-trecho">⚠ trecho curto</span>' : ""}
    </div>

    <div class="acoes-trecho">
      <button type="button" class="mover-cima">↑ Subir</button>
      <button type="button" class="mover-baixo">↓ Descer</button>
      <button type="button" class="remover-trecho">Remover</button>
    </div>
  `;

  const selectSecao = card.querySelector(".secao-trecho");
  preencherSelectSecoes(selectSecao);
  selectSecao.value = trecho.secao;

  card.querySelector(".encaixe-trecho").value = trecho.encaixe;

  if (indice > 0) {
    const selectTransicao = card.querySelector(".transicao-trecho");
    const campoDuracaoTransicao = card.querySelector(".campo-duracao-transicao");
    const selectDuracaoTransicao = card.querySelector(".duracao-transicao-trecho");

    const transicaoAtual = trecho.transicao_entrada || TRANSICAO_PADRAO;
    const duracaoTransicaoAtual = Number(
      trecho.duracao_transicao ?? DURACAO_TRANSICAO_PADRAO_SEGUNDOS
    );

    selectTransicao.value = transicaoAtual;
    selectDuracaoTransicao.value = String(duracaoTransicaoAtual);
    campoDuracaoTransicao.hidden = transicaoAtual !== "dissolve";

    selectTransicao.addEventListener("change", () => {
      campoDuracaoTransicao.hidden = selectTransicao.value !== "dissolve";
      aplicarEdicaoTrecho(indice, {
        transicao_entrada: selectTransicao.value,
        duracao_transicao: Number(selectDuracaoTransicao.value),
      });
    });

    selectDuracaoTransicao.addEventListener("change", () => {
      aplicarEdicaoTrecho(indice, { duracao_transicao: Number(selectDuracaoTransicao.value) });
    });
  }

  const inicioInput = card.querySelector(".inicio-trecho");
  const fimInput = card.querySelector(".fim-trecho");
  const player = card.querySelector(".previa-trecho");

  player.addEventListener("timeupdate", () => {
    card.querySelector(".tempo-atual").textContent = `Tempo atual: ${formatarTempo(player.currentTime)}`;
  });

  card.querySelector(".marcar-inicio").addEventListener("click", () => {
    aplicarEdicaoTrecho(indice, { inicio_segundos: Number(player.currentTime.toFixed(3)) });
  });
  card.querySelector(".marcar-fim").addEventListener("click", () => {
    aplicarEdicaoTrecho(indice, { fim_segundos: Number(player.currentTime.toFixed(3)) });
  });

  inicioInput.addEventListener("change", () => {
    aplicarEdicaoTrecho(indice, { inicio_segundos: Number(inicioInput.value) });
  });
  fimInput.addEventListener("change", () => {
    aplicarEdicaoTrecho(indice, { fim_segundos: Number(fimInput.value) });
  });
  selectSecao.addEventListener("change", () => {
    aplicarEdicaoTrecho(indice, { secao: selectSecao.value });
  });
  card.querySelector(".encaixe-trecho").addEventListener("change", (evento) => {
    aplicarEdicaoTrecho(indice, { encaixe: evento.target.value });
  });
  card.querySelector(".audio-trecho").addEventListener("change", (evento) => {
    aplicarEdicaoTrecho(indice, { manter_audio_original: evento.target.checked });
  });

  card.querySelector(".mover-cima").addEventListener("click", () => moverTrecho(indice, -1));
  card.querySelector(".mover-baixo").addEventListener("click", () => moverTrecho(indice, 1));
  card.querySelector(".remover-trecho").addEventListener("click", () => removerTrecho(indice));

  return card;
}

function aplicarEdicaoTrecho(indice, alteracoes) {
  Object.assign(trechos[indice], alteracoes);
  renderizarTrechos();
  marcarAlteracaoPendente();
}

function moverTrecho(indice, direcao) {
  const novoIndice = indice + direcao;
  if (novoIndice < 0 || novoIndice >= trechos.length) return;
  const [item] = trechos.splice(indice, 1);
  trechos.splice(novoIndice, 0, item);
  renderizarTrechos();
  marcarAlteracaoPendente();
}

function removerTrecho(indice) {
  trechos.splice(indice, 1);
  renderizarTrechos();
  marcarAlteracaoPendente();
}

function calcularDuracaoEstimadaProducao(lista) {
  // Mesma fórmula de calcular_duracao_estimada_producao em
  // video_institucional_render.py: soma das durações nominais dos trechos
  // menos a duração de cada dissolve (que sobrepõe dois trechos). Cortes não
  // subtraem nada.
  let total = 0;
  lista.forEach((trecho, indice) => {
    const duracao = trecho.fim_segundos - trecho.inicio_segundos;
    total += duracao > 0 ? duracao : 0;
    if (indice > 0) {
      const transicao = trecho.transicao_entrada || TRANSICAO_PADRAO;
      if (transicao === "dissolve") {
        total -= Number(trecho.duracao_transicao ?? DURACAO_TRANSICAO_PADRAO_SEGUNDOS);
      }
    }
  });
  return Math.max(0, total);
}

function atualizarResumoDuracao() {
  const duracaoTotal = calcularDuracaoEstimadaProducao(trechos);

  document.getElementById("total-trechos").textContent = `${trechos.length} trecho${
    trechos.length === 1 ? "" : "s"
  }`;
  document.getElementById("duracao-total").textContent = formatarTempo(duracaoTotal);

  const alerta = document.getElementById("alerta-duracao");
  if (!trechos.length) {
    alerta.hidden = true;
    return;
  }

  alerta.hidden = false;
  if (duracaoTotal < DURACAO_ALVO_MINIMA_SEGUNDOS) {
    alerta.className = "alerta alerta-atencao";
    alerta.textContent = `Duração total (${formatarTempo(
      duracaoTotal
    )}) abaixo da faixa recomendada de 1:45–2:15. Isso não impede salvar.`;
  } else if (duracaoTotal > DURACAO_ALVO_MAXIMA_SEGUNDOS) {
    alerta.className = "alerta alerta-atencao";
    alerta.textContent = `Duração total (${formatarTempo(
      duracaoTotal
    )}) acima da faixa recomendada de 1:45–2:15. Isso não impede salvar.`;
  } else {
    alerta.className = "alerta alerta-ok";
    alerta.textContent = "Duração total dentro da faixa recomendada (1:45–2:15).";
  }
}

// =========================================================
// SALVAMENTO (autosave leve + botão)
// =========================================================

function marcarAlteracaoPendente() {
  temAlteracoesPendentes = true;
  document.getElementById("status-salvamento").textContent = "Alterações não salvas...";
  if (timerAutosave) clearTimeout(timerAutosave);
  timerAutosave = setTimeout(salvarSelecao, ATRASO_AUTOSAVE_MS);
}

function marcarComoSalvo() {
  temAlteracoesPendentes = false;
  document.getElementById("status-salvamento").textContent =
    `Tudo salvo (${new Date().toLocaleTimeString("pt-BR")}).`;
}

async function salvarSelecao() {
  if (timerAutosave) {
    clearTimeout(timerAutosave);
    timerAutosave = null;
  }
  if (!producaoAtual) return;

  const existeTrechoInvalido = trechos.some((trecho) => !(trecho.fim_segundos > trecho.inicio_segundos));
  if (existeTrechoInvalido) {
    document.getElementById("status-salvamento").textContent =
      "Corrija os trechos com fim ≤ início antes de salvar.";
    return;
  }

  document.getElementById("status-salvamento").textContent = "Salvando...";
  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/${producaoAtual.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selecao_editorial: trechos.map((trecho, indice) => ({ ...trecho, ordem: indice + 1 })),
      }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      const detalhe = Array.isArray(dados.detail)
        ? dados.detail.map((erro) => erro.msg).join("; ")
        : dados.detail || "Não foi possível salvar.";
      throw new Error(detalhe);
    }

    producaoAtual = dados;
    trechos = (dados.selecao_editorial || []).map((trecho) => ({ ...trecho }));
    marcarComoSalvo();
    await carregarProducoes(producaoAtual.id);
    renderizarTrechos();
  } catch (erro) {
    document.getElementById("status-salvamento").textContent = `Erro ao salvar: ${erro.message}`;
  }
}

document.getElementById("botao-salvar").addEventListener("click", salvarSelecao);

// =========================================================
// EVENTOS GERAIS + INICIALIZAÇÃO
// =========================================================

document.getElementById("select-producao").addEventListener("change", (evento) => {
  selecionarProducao(evento.target.value || null);
});

document.getElementById("botao-nova-producao").addEventListener("click", criarNovaProducao);

document.getElementById("busca-sonho").addEventListener("input", (evento) => {
  termoBusca = evento.target.value.trim().toLowerCase();
  atualizarListaSonhos();
});

async function iniciar() {
  preencherSelectSecoes(document.getElementById("secao-novo"));
  await carregarProducoes();
  await carregarSonhos();

  const parametros = new URLSearchParams(window.location.search);
  const idInicial = parametros.get("id");
  if (idInicial) {
    await selecionarProducao(idInicial);
  }
}

iniciar();
