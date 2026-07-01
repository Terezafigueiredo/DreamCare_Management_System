async function carregarMetricas() {
  try {
    const resposta = await fetch("http://127.0.0.1:8000/sonhos");
    const dados = await resposta.json();

    document.getElementById("total-sonhos").textContent = dados.total;
  } catch (erro) {
    console.error("Erro ao carregar métricas:", erro);
  }
}

carregarMetricas();