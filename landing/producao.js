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
      Ajuste somente os intervalos dos vídeos já usados. A soma final deve ter até 60 segundos.
    </p>
    <div class="lista-trechos-revisao"></div>
    <div class="total-revisao"></div>
    <button type="button" class="botao-card botao-gerar-versao">Gerar nova versão</button>
  `;
  const lista = painel.querySelector(".lista-trechos-revisao");
  (revisao.trechos || []).forEach((trecho) => {
    lista.appendChild(criarTrechoRevisao(trecho, item.producao_id));
  });

  const atualizar = () => atualizarResumoRevisao(painel);
  lista.addEventListener("input", atualizar);
  lista.addEventListener("change", atualizar);
  painel.querySelector(".botao-gerar-versao").addEventListener("click", async (evento) => {
    const botao = evento.currentTarget;
    const trechos = [...lista.querySelectorAll(".trecho-revisao")].map((cardTrecho) => ({
      drive_file_id: cardTrecho.dataset.fileId,
      inicio_segundos: Number(cardTrecho.querySelector(".inicio-trecho").value),
      fim_segundos: Number(cardTrecho.querySelector(".fim-trecho").value),
    }));
    const total = trechos.reduce(
      (soma, trecho) => soma + trecho.fim_segundos - trecho.inicio_segundos,
      0
    );
    if (!trechos.length || trechos.some((trecho) => trecho.inicio_segundos < 0 || trecho.fim_segundos - trecho.inicio_segundos < 1)) {
      alert("Mantenha ao menos um trecho, todos com duração mínima de 1 segundo.");
      return;
    }
    if (total > 60.001) {
      alert("A soma dos trechos não pode ultrapassar 60 segundos.");
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

function formatarTempoVideo(segundos) {
  const valor = Math.max(0, Number(segundos) || 0);
  const minutos = Math.floor(valor / 60);
  const restante = valor - minutos * 60;
  return `${String(minutos).padStart(2, "0")}:${restante.toFixed(2).padStart(5, "0")}`;
}

function criarTrechoRevisao(trecho, producaoId) {
  const card = document.createElement("article");
  card.className = "trecho-revisao";
  card.dataset.fileId = trecho.drive_file_id;
  const alternativas = trecho.alternativas || [];
  card.innerHTML = `
    <div class="trecho-cabecalho">
      <strong class="ordem-trecho">Trecho ${trecho.ordem}</strong>
      <span>${escaparHtml(trecho.arquivo)}</span>
    </div>
    <video class="previa-trecho" controls preload="none"
      src="${API_PRODUCAO}/${producaoId}/video-original/${encodeURIComponent(trecho.drive_file_id)}"></video>
    <div class="tempo-atual">Tempo atual: 00:00.00</div>
    <div class="marcadores-trecho">
      <button type="button" class="marcar-inicio">Marcar início aqui</button>
      <button type="button" class="marcar-fim">Marcar fim aqui</button>
    </div>
    <div class="selecao-visual">
      <span>Início selecionado: <strong class="inicio-formatado">${formatarTempoVideo(trecho.inicio_segundos)}</strong></span>
      <span>Fim selecionado: <strong class="fim-formatado">${formatarTempoVideo(trecho.fim_segundos)}</strong></span>
      <span>Duração: <strong class="duracao-formatada">${Number(trecho.duracao_segundos).toFixed(2)}s</strong></span>
    </div>
    <div class="campos-trecho">
      <label>Início <input class="inicio-trecho" type="number" min="0" step="0.001" value="${trecho.inicio_segundos}"></label>
      <label>Fim <input class="fim-trecho" type="number" min="1" step="0.001" value="${trecho.fim_segundos}"></label>
    </div>
    <div class="metadados-trecho">
      <span class="duracao-trecho">${Number(trecho.duracao_segundos).toFixed(3)}s</span>
      <span>Movimento: ${Number(trecho.pontuacao_movimento || 0).toFixed(2)}</span>
      <span>Áudio: ${trecho.audio_original ? "sim" : "não"}</span>
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
      ${alternativas.length ? "" : "<small>Alternativas não registradas nesta versão antiga; ajuste início e fim manualmente.</small>"}
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
    const duracao = Math.max(0, Number(card.querySelector(".fim-trecho").value) - Number(card.querySelector(".inicio-trecho").value));
    card.querySelector(".duracao-trecho").textContent = `${duracao.toFixed(3)}s`;
    card.querySelector(".inicio-formatado").textContent = formatarTempoVideo(card.querySelector(".inicio-trecho").value);
    card.querySelector(".fim-formatado").textContent = formatarTempoVideo(card.querySelector(".fim-trecho").value);
    card.querySelector(".duracao-formatada").textContent = `${duracao.toFixed(2)}s`;
    total += duracao;
  });
  const resumo = painel.querySelector(".total-revisao");
  resumo.textContent = `${painel.querySelectorAll(".trecho-revisao").length} trechos · ${total.toFixed(3)} segundos`;
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
