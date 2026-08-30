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

// Mesma validação de video_institucional_render.py (PADRAO_TEXTO_SEGURO_PALAVRA):
// letras (inclusive acentuadas), números, espaços e pontuação básica.
const PADRAO_TEXTO_SEGURO_PALAVRA = /^[\p{L}\p{N}\s.,!?-]+$/u;

// Preset "Aplicar narrativa ROPE" — espelha gerar_preset_narrativa_rope() em
// api/video_institucional_render.py. Os tempos são proporcionais a uma
// produção de referência de 105s (1min45s), nunca segundos absolutos fixos.
const PRESET_ROPE_REFERENCIA_SEGUNDOS = 105.0;
const PRESET_ROPE_PALAVRAS_REFERENCIA = [
  { texto: "DREAMS", inicio: 3, fim: 9, impacto: "forte", posicao: "centro" },
  { texto: "PURPOSE", inicio: 17, fim: 21, impacto: "normal", posicao: "centro" },
  { texto: "EACH.", inicio: 26, fim: 29, impacto: "normal", posicao: "centro" },
  { texto: "PERSON.", inicio: 30, fim: 34, impacto: "normal", posicao: "centro" },
  { texto: "SACRED", inicio: 44, fim: 49, impacto: "normal", posicao: "superior" },
  { texto: "FAITH", inicio: 66, fim: 73, impacto: "forte", posicao: "centro" },
  { texto: "JOY", inicio: 79, fim: 83, impacto: "normal", posicao: "inferior" },
  { texto: "FULFILLMENT", inicio: 96, fim: 104, impacto: "forte", posicao: "centro" },
];

// Mesmo padrão de compatibilidade do backend (_normalizar_encerramento em
// video_institucional_render.py): produção sem esse bloco = encerramento
// ativo com estes defaults.
const ENCERRAMENTO_PADRAO = {
  ativo: true,
  duracao_segundos: 6.0,
  fade_entrada: 1.0,
  fade_saida: 1.0,
};

// Mesmo padrão de compatibilidade do backend (_normalizar_musica em
// video_institucional_render.py): produção sem esse bloco (ou sem arquivo
// enviado ainda) = sem música.
const MUSICA_PADRAO = {
  ativa: false,
  arquivo: null,
  nome_original: null,
  duracao_segundos: null,
  volume_base: 0.8,
  fade_in: 2.0,
  fade_out: 3.0,
  curva_emocional: "padrao",
  ducking: { nivel_musica_durante_fala: 0.3, ataque_segundos: 0.6, retorno_segundos: 1.2 },
};

// =========================================================
// ESTADO
// =========================================================

function identidadeNarrativaVazia() {
  return {
    palavras: [],
    encerramento: { ...ENCERRAMENTO_PADRAO },
    musica: { ...MUSICA_PADRAO },
  };
}

function construirIdentidadeNarrativaLocal(identidadeServidor) {
  const bruta = identidadeServidor || {};
  return {
    palavras: (bruta.palavras || []).map((palavra) => ({ ...palavra })),
    encerramento: { ...ENCERRAMENTO_PADRAO, ...(bruta.encerramento || {}) },
    musica: {
      ...MUSICA_PADRAO,
      ...(bruta.musica || {}),
      ducking: { ...MUSICA_PADRAO.ducking, ...((bruta.musica || {}).ducking || {}) },
    },
  };
}

let producaoAtual = null; // objeto completo retornado pela API
let trechos = []; // cópia local da seleção editorial em edição
let identidadeNarrativa = identidadeNarrativaVazia(); // cópia local da narrativa/encerramento em edição
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

function construirPreviewUrlTrecho(trecho) {
  return producaoAtual
    ? `${API_INSTITUCIONAL}/${producaoAtual.id}/sonhos/${trecho.sonho_id}/video-original/${encodeURIComponent(
        trecho.drive_file_id
      )}`
    : "";
}

function estaForaDoTrecho(tempo, trecho) {
  return tempo < trecho.inicio_segundos || tempo >= trecho.fim_segundos;
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
    identidadeNarrativa = identidadeNarrativaVazia();
    sonhoSelecionado = null;
    esconderPlayer();
    document.getElementById("status-producao").textContent = "Nenhuma produção selecionada.";
    document.getElementById("lista-videos-sonho").innerHTML = "";
    document.getElementById("titulo-sonho-selecionado").textContent =
      "Selecione um sonho à esquerda para ver os vídeos.";
    atualizarUrl(null);
    atualizarListaSonhos();
    renderizarTrechos();
    renderizarPalavras();
    renderizarEncerramento();
    renderizarMusica();
    return;
  }

  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/${id}`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível carregar a produção.");

    producaoAtual = dados;
    trechos = (dados.selecao_editorial || []).map((trecho) => ({ ...trecho }));
    identidadeNarrativa = construirIdentidadeNarrativaLocal(dados.identidade_narrativa);
    document.getElementById("status-producao").textContent =
      `#${dados.id} — ${dados.titulo} (status: ${dados.status})`;
    document.getElementById("select-producao").value = String(id);
    atualizarUrl(id);
    marcarComoSalvo();
    renderizarTrechos();
    renderizarPalavras();
    renderizarEncerramento();
    renderizarMusica();
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

  const previewUrl = construirPreviewUrlTrecho(trecho);

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
    if (player.currentTime >= trecho.fim_segundos) {
      player.pause();
      player.currentTime = trecho.fim_segundos;
    }
  });

  player.addEventListener("loadedmetadata", () => {
    player.currentTime = trecho.inicio_segundos;
  });

  player.addEventListener("play", () => {
    if (estaForaDoTrecho(player.currentTime, trecho)) {
      player.currentTime = trecho.inicio_segundos;
    }
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

// =========================================================
// PRÉVIA SEQUENCIAL DA SELEÇÃO EDITORIAL
// =========================================================
// Reaproduz, em ordem, os trechos já salvos localmente em `trechos` usando o
// mesmo endpoint de preview do vídeo original já usado nos cards
// (construirPreviewUrlTrecho). Não gera nenhum arquivo novo nem chama a
// renderização — apenas controla currentTime/eventos de um único <video> do
// modal. Fechar a prévia nunca altera `trechos`.

let sequenciaPrevia = [];
let indicePreviaAtual = 0;
// Incrementada a cada chamada de irParaTrechoPrevia. Cliques rápidos em
// Anterior/Próximo (ou avanço automático seguido de navegação manual) podem
// trocar o `src` do player antes do `loadedmetadata` de uma troca anterior
// disparar; esse número identifica qual troca ainda é a "atual" quando o
// evento chega, evitando que um carregamento abandonado reposicione o player
// no trecho errado.
let geracaoPrevia = 0;

function abrirPreviaSequencia() {
  sequenciaPrevia = trechos.filter((trecho) => trecho.fim_segundos > trecho.inicio_segundos);
  if (!sequenciaPrevia.length) {
    mostrarMensagemGlobal("Nenhum trecho válido para pré-visualizar (verifique fim > início).");
    return;
  }
  mostrarMensagemGlobal(null);
  document.getElementById("modal-previa-sequencia").hidden = false;
  irParaTrechoPrevia(0);
}

function fecharPreviaSequencia() {
  const player = document.getElementById("player-previa-sequencia");
  player.pause();
  player.removeAttribute("src");
  player.load();
  document.getElementById("modal-previa-sequencia").hidden = true;
}

function irParaTrechoPrevia(indice) {
  if (indice < 0 || indice >= sequenciaPrevia.length) return;
  indicePreviaAtual = indice;
  geracaoPrevia += 1;
  const geracaoAlvo = geracaoPrevia;

  const trecho = sequenciaPrevia[indicePreviaAtual];
  const sonhoInfo = sonhos.find((item) => item.id === trecho.sonho_id);
  const nomeSonho = sonhoInfo ? sonhoInfo.nome : `Sonho #${trecho.sonho_id}`;
  const player = document.getElementById("player-previa-sequencia");
  const url = construirPreviewUrlTrecho(trecho);

  document.getElementById("previa-titulo-trecho").textContent =
    `#${trecho.ordem} · ${nomeSonho} · ${trecho.secao}`;
  document.getElementById("previa-posicao").textContent =
    `${indicePreviaAtual + 1} / ${sequenciaPrevia.length}`;
  document.getElementById("previa-anterior").disabled = indicePreviaAtual === 0;
  document.getElementById("previa-proxima").disabled = indicePreviaAtual === sequenciaPrevia.length - 1;

  const iniciarNoTrecho = () => {
    if (geracaoAlvo !== geracaoPrevia) return;
    player.currentTime = trecho.inicio_segundos;
    player.play();
  };

  if (player.src !== url) {
    player.src = url;
    player.addEventListener("loadedmetadata", iniciarNoTrecho, { once: true });
  } else {
    iniciarNoTrecho();
  }
}

document.getElementById("player-previa-sequencia").addEventListener("timeupdate", () => {
  const player = document.getElementById("player-previa-sequencia");
  const trecho = sequenciaPrevia[indicePreviaAtual];
  if (!trecho || player.readyState < 1) return;

  document.getElementById("tempo-atual-previa-sequencia").textContent =
    `Tempo atual: ${formatarTempo(player.currentTime)}`;

  if (player.currentTime >= trecho.fim_segundos) {
    if (indicePreviaAtual < sequenciaPrevia.length - 1) {
      irParaTrechoPrevia(indicePreviaAtual + 1);
    } else {
      player.pause();
      player.currentTime = trecho.fim_segundos;
    }
  }
});

document.getElementById("player-previa-sequencia").addEventListener("play", () => {
  const player = document.getElementById("player-previa-sequencia");
  const trecho = sequenciaPrevia[indicePreviaAtual];
  if (trecho && estaForaDoTrecho(player.currentTime, trecho)) {
    player.currentTime = trecho.inicio_segundos;
  }
});

document.getElementById("botao-previa-sequencia").addEventListener("click", abrirPreviaSequencia);
document.getElementById("fechar-previa-sequencia").addEventListener("click", fecharPreviaSequencia);
document.getElementById("previa-anterior").addEventListener("click", () => {
  irParaTrechoPrevia(indicePreviaAtual - 1);
});
document.getElementById("previa-proxima").addEventListener("click", () => {
  irParaTrechoPrevia(indicePreviaAtual + 1);
});

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

function calcularDuracaoTotalComEncerramento(lista, encerramento) {
  // Mesma fórmula de calcular_duracao_total_com_encerramento em
  // video_institucional_render.py: conteúdo dos sonhos + duração do
  // encerramento (só se ativo). Retorna os três números que a interface
  // mostra separadamente (item 8 da Fase 7).
  const duracaoConteudo = calcularDuracaoEstimadaProducao(lista);
  const config = encerramento || ENCERRAMENTO_PADRAO;
  const duracaoEncerramento = config.ativo
    ? Number(config.duracao_segundos ?? ENCERRAMENTO_PADRAO.duracao_segundos)
    : 0;
  return {
    duracaoConteudo,
    duracaoEncerramento,
    duracaoTotal: duracaoConteudo + duracaoEncerramento,
  };
}

function atualizarResumoDuracao() {
  const { duracaoConteudo, duracaoEncerramento, duracaoTotal } = calcularDuracaoTotalComEncerramento(
    trechos,
    identidadeNarrativa.encerramento
  );

  document.getElementById("total-trechos").textContent = `${trechos.length} trecho${
    trechos.length === 1 ? "" : "s"
  }`;
  document.getElementById("duracao-conteudo").textContent = formatarTempo(duracaoConteudo);
  document.getElementById("duracao-encerramento").textContent = formatarTempo(duracaoEncerramento);
  document.getElementById("duracao-total").textContent = formatarTempo(duracaoTotal);

  const alerta = document.getElementById("alerta-duracao");
  if (!trechos.length) {
    alerta.hidden = true;
    return;
  }

  alerta.hidden = false;
  if (duracaoTotal < DURACAO_ALVO_MINIMA_SEGUNDOS) {
    alerta.className = "alerta alerta-atencao";
    alerta.textContent = `Duração final estimada (${formatarTempo(
      duracaoTotal
    )}) abaixo da faixa recomendada de 1:45–2:15. Isso não impede salvar.`;
  } else if (duracaoTotal > DURACAO_ALVO_MAXIMA_SEGUNDOS) {
    alerta.className = "alerta alerta-atencao";
    alerta.textContent = `Duração final estimada (${formatarTempo(
      duracaoTotal
    )}) acima da faixa recomendada de 1:45–2:15. Isso não impede salvar.`;
  } else {
    alerta.className = "alerta alerta-ok";
    alerta.textContent = "Duração final estimada dentro da faixa recomendada (1:45–2:15).";
  }
}

// =========================================================
// NARRATIVA / PALAVRAS (Fase 6)
// =========================================================

function gerarPresetNarrativaRope(duracaoEstimada) {
  // Mesma fórmula de gerar_preset_narrativa_rope() em
  // video_institucional_render.py — tempos proporcionais à duração estimada
  // da produção, nunca segundos absolutos fixos.
  const fator = duracaoEstimada > 0 ? duracaoEstimada / PRESET_ROPE_REFERENCIA_SEGUNDOS : 1.0;
  return PRESET_ROPE_PALAVRAS_REFERENCIA.map((item) => ({
    texto: item.texto,
    inicio_segundos: Math.round(item.inicio * fator * 100) / 100,
    fim_segundos: Math.round(item.fim * fator * 100) / 100,
    impacto: item.impacto,
    posicao: item.posicao,
    ativa: true,
  }));
}

function renderizarPalavras() {
  const corpo = document.getElementById("lista-palavras");
  const vazio = document.getElementById("palavras-vazio");
  corpo.innerHTML = "";

  const palavras = identidadeNarrativa.palavras || [];
  vazio.hidden = palavras.length > 0;

  palavras.forEach((palavra, indice) => {
    corpo.appendChild(criarLinhaPalavra(palavra, indice));
  });
}

function criarLinhaPalavra(palavra, indice) {
  const textoAtual = (palavra.texto || "").trim();
  const invalida =
    !(palavra.fim_segundos > palavra.inicio_segundos) || !PADRAO_TEXTO_SEGURO_PALAVRA.test(textoAtual);

  const linha = document.createElement("tr");
  linha.className =
    "linha-palavra" +
    (palavra.ativa === false ? " linha-palavra-inativa" : "") +
    (invalida ? " linha-palavra-invalida" : "");

  linha.innerHTML = `
    <td><input type="checkbox" class="palavra-ativa" ${palavra.ativa !== false ? "checked" : ""}></td>
    <td><input type="text" class="palavra-texto" value="${escaparHtml(palavra.texto || "")}" maxlength="30"></td>
    <td><input type="number" class="palavra-inicio" step="0.1" min="0" value="${palavra.inicio_segundos}"></td>
    <td><input type="number" class="palavra-fim" step="0.1" min="0" value="${palavra.fim_segundos}"></td>
    <td>
      <select class="palavra-impacto">
        <option value="normal">Normal</option>
        <option value="forte">Forte</option>
      </select>
    </td>
    <td>
      <select class="palavra-posicao">
        <option value="centro">Centro</option>
        <option value="superior">Superior</option>
        <option value="inferior">Inferior</option>
      </select>
    </td>
    <td><button type="button" class="botao-remover-palavra" title="Remover">✕</button></td>
  `;

  linha.querySelector(".palavra-impacto").value = palavra.impacto || "normal";
  linha.querySelector(".palavra-posicao").value = palavra.posicao || "centro";

  linha.querySelector(".palavra-ativa").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { ativa: evento.target.checked });
  });
  linha.querySelector(".palavra-texto").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { texto: evento.target.value });
  });
  linha.querySelector(".palavra-inicio").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { inicio_segundos: Number(evento.target.value) });
  });
  linha.querySelector(".palavra-fim").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { fim_segundos: Number(evento.target.value) });
  });
  linha.querySelector(".palavra-impacto").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { impacto: evento.target.value });
  });
  linha.querySelector(".palavra-posicao").addEventListener("change", (evento) => {
    aplicarEdicaoPalavra(indice, { posicao: evento.target.value });
  });
  linha.querySelector(".botao-remover-palavra").addEventListener("click", () => {
    identidadeNarrativa.palavras.splice(indice, 1);
    renderizarPalavras();
    marcarAlteracaoPendente();
  });

  return linha;
}

function aplicarEdicaoPalavra(indice, alteracoes) {
  Object.assign(identidadeNarrativa.palavras[indice], alteracoes);
  renderizarPalavras();
  marcarAlteracaoPendente();
}

document.getElementById("botao-nova-palavra").addEventListener("click", () => {
  if (!producaoAtual) {
    alert("Crie ou selecione uma produção institucional antes de adicionar palavras.");
    return;
  }
  identidadeNarrativa.palavras.push({
    texto: "PALAVRA",
    inicio_segundos: 0,
    fim_segundos: 3,
    impacto: "normal",
    posicao: "centro",
    ativa: true,
  });
  renderizarPalavras();
  marcarAlteracaoPendente();
});

document.getElementById("botao-preset-rope").addEventListener("click", () => {
  if (!producaoAtual) {
    alert("Crie ou selecione uma produção institucional antes de aplicar a narrativa.");
    return;
  }
  if ((identidadeNarrativa.palavras || []).length > 0) {
    const confirmar = confirm(
      "Isso substitui as palavras atuais pela narrativa padrão ROPE (tempos proporcionais à duração estimada). Continuar?"
    );
    if (!confirmar) return;
  }
  const duracaoEstimada = calcularDuracaoEstimadaProducao(trechos);
  identidadeNarrativa.palavras = gerarPresetNarrativaRope(duracaoEstimada);
  renderizarPalavras();
  marcarAlteracaoPendente();
});

// =========================================================
// ENCERRAMENTO ROPE (Fase 7)
// =========================================================

function renderizarEncerramento() {
  const config = identidadeNarrativa.encerramento || ENCERRAMENTO_PADRAO;
  document.getElementById("encerramento-ativo").checked = config.ativo !== false;
  document.getElementById("encerramento-duracao").value = config.duracao_segundos;
  document.getElementById("encerramento-fade-entrada").value = config.fade_entrada;
  document.getElementById("encerramento-fade-saida").value = config.fade_saida;
  atualizarResumoDuracao();
}

function aplicarEdicaoEncerramento(alteracoes) {
  identidadeNarrativa.encerramento = {
    ...ENCERRAMENTO_PADRAO,
    ...identidadeNarrativa.encerramento,
    ...alteracoes,
  };
  atualizarResumoDuracao();
  marcarAlteracaoPendente();
}

document.getElementById("encerramento-ativo").addEventListener("change", (evento) => {
  aplicarEdicaoEncerramento({ ativo: evento.target.checked });
});
document.getElementById("encerramento-duracao").addEventListener("change", (evento) => {
  aplicarEdicaoEncerramento({ duracao_segundos: Number(evento.target.value) });
});
document.getElementById("encerramento-fade-entrada").addEventListener("change", (evento) => {
  aplicarEdicaoEncerramento({ fade_entrada: Number(evento.target.value) });
});
document.getElementById("encerramento-fade-saida").addEventListener("change", (evento) => {
  aplicarEdicaoEncerramento({ fade_saida: Number(evento.target.value) });
});

async function carregarInfoLogo() {
  const elemento = document.getElementById("info-logo");
  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/logo-info`);
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível carregar a logo.");
    elemento.textContent = `Logo utilizada: ${dados.arquivo} (${dados.largura}×${dados.altura}px, fornecida pelo projeto).`;
  } catch (erro) {
    elemento.textContent = `Não foi possível carregar a informação da logo: ${erro.message}`;
  }
}

// =========================================================
// TRILHA SONORA (Fase 8)
// =========================================================

function renderizarMusica() {
  const musica = identidadeNarrativa.musica || MUSICA_PADRAO;
  const bloco = document.getElementById("bloco-musica-atual");
  const status = document.getElementById("status-musica");
  const player = document.getElementById("preview-musica");

  if (!producaoAtual) {
    status.textContent = "Crie ou selecione uma produção institucional para enviar uma trilha.";
    bloco.hidden = true;
    player.removeAttribute("src");
    return;
  }

  if (!musica.arquivo) {
    status.textContent = "Nenhuma trilha enviada ainda.";
    bloco.hidden = true;
    player.removeAttribute("src");
    return;
  }

  status.textContent = "";
  bloco.hidden = false;
  document.getElementById("info-musica-atual").textContent =
    `Arquivo: ${musica.nome_original || musica.arquivo}` +
    (musica.duracao_segundos ? ` (${formatarTempo(musica.duracao_segundos)})` : "");
  document.getElementById("musica-ativa").checked = musica.ativa !== false;
  document.getElementById("musica-volume-base").value = musica.volume_base;

  const novoSrc = `${API_INSTITUCIONAL}/${producaoAtual.id}/musica/preview`;
  if (player.getAttribute("src") !== novoSrc) {
    player.src = novoSrc;
  }
}

document.getElementById("botao-enviar-musica").addEventListener("click", async () => {
  if (!producaoAtual) {
    alert("Crie ou selecione uma produção institucional antes de enviar uma trilha.");
    return;
  }
  const input = document.getElementById("musica-arquivo-input");
  const arquivo = input.files && input.files[0];
  if (!arquivo) {
    alert("Escolha um arquivo de áudio (MP3, WAV ou M4A/AAC) primeiro.");
    return;
  }

  const status = document.getElementById("status-musica");
  status.textContent = "Enviando trilha...";

  try {
    const formData = new FormData();
    formData.append("arquivo", arquivo);
    const resposta = await fetch(`${API_INSTITUCIONAL}/${producaoAtual.id}/musica`, {
      method: "POST",
      body: formData,
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      const detalhe = Array.isArray(dados.detail)
        ? dados.detail.map((erro) => erro.msg).join("; ")
        : dados.detail || "Não foi possível enviar a trilha.";
      throw new Error(detalhe);
    }

    producaoAtual = dados;
    identidadeNarrativa = construirIdentidadeNarrativaLocal(dados.identidade_narrativa);
    input.value = "";
    renderizarMusica();
    atualizarResumoDuracao();
    await carregarProducoes(producaoAtual.id);
    marcarComoSalvo();
  } catch (erro) {
    document.getElementById("status-musica").textContent = `Erro ao enviar trilha: ${erro.message}`;
  }
});

document.getElementById("botao-remover-musica").addEventListener("click", async () => {
  if (!producaoAtual) return;
  const confirmar = confirm("Remover a trilha sonora desta produção?");
  if (!confirmar) return;

  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/${producaoAtual.id}/musica`, { method: "DELETE" });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "Não foi possível remover a trilha.");

    producaoAtual = dados;
    identidadeNarrativa = construirIdentidadeNarrativaLocal(dados.identidade_narrativa);
    renderizarMusica();
    atualizarResumoDuracao();
    await carregarProducoes(producaoAtual.id);
    marcarComoSalvo();
  } catch (erro) {
    document.getElementById("status-musica").textContent = `Erro ao remover trilha: ${erro.message}`;
  }
});

document.getElementById("musica-ativa").addEventListener("change", (evento) => {
  identidadeNarrativa.musica = { ...identidadeNarrativa.musica, ativa: evento.target.checked };
  marcarAlteracaoPendente();
});

document.getElementById("musica-volume-base").addEventListener("change", (evento) => {
  identidadeNarrativa.musica = {
    ...identidadeNarrativa.musica,
    volume_base: Number(evento.target.value),
  };
  marcarAlteracaoPendente();
});

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

  const existePalavraInvalida = (identidadeNarrativa.palavras || []).some(
    (palavra) =>
      palavra.ativa !== false &&
      (!(palavra.fim_segundos > palavra.inicio_segundos) ||
        !PADRAO_TEXTO_SEGURO_PALAVRA.test((palavra.texto || "").trim()))
  );
  if (existePalavraInvalida) {
    document.getElementById("status-salvamento").textContent =
      "Corrija as palavras com fim ≤ início ou texto/caracteres inválidos antes de salvar.";
    return;
  }

  const encerramento = identidadeNarrativa.encerramento || ENCERRAMENTO_PADRAO;
  if (encerramento.fade_entrada + encerramento.fade_saida >= encerramento.duracao_segundos) {
    document.getElementById("status-salvamento").textContent =
      "No encerramento, fade de entrada + fade de saída deve ser menor que a duração antes de salvar.";
    return;
  }

  document.getElementById("status-salvamento").textContent = "Salvando...";
  try {
    const resposta = await fetch(`${API_INSTITUCIONAL}/${producaoAtual.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selecao_editorial: trechos.map((trecho, indice) => ({ ...trecho, ordem: indice + 1 })),
        identidade_narrativa: identidadeNarrativa,
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
    identidadeNarrativa = construirIdentidadeNarrativaLocal(dados.identidade_narrativa);
    marcarComoSalvo();
    await carregarProducoes(producaoAtual.id);
    renderizarTrechos();
    renderizarPalavras();
    renderizarEncerramento();
    renderizarMusica();
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
  await carregarInfoLogo();
  renderizarEncerramento();
  renderizarMusica();

  const parametros = new URLSearchParams(window.location.search);
  const idInicial = parametros.get("id");
  if (idInicial) {
    await selecionarProducao(idInicial);
  }
}

iniciar();
