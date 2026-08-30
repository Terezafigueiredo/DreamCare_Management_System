"""Motor de renderização FFmpeg do Vídeo Institucional ROPE.

Fase 4: pipeline vertical básico, corte seco.
Fase 5: transições configuráveis por trecho (corte/dissolve) e segunda
orientação horizontal (16:9), ambas a partir dos mesmos trechos-fonte
normalizados (nunca "vertical pronto -> cortar -> horizontal").
Fase 6: palavras cinematográficas (drawtext) aplicadas na ETAPA FINAL do
pipeline, depois da montagem/transições — os tempos das palavras usam a
timeline final, não a de cada trecho-fonte.
Fase 7: encerramento institucional (logo oficial do ROPE) — um card final
gerado programaticamente (fundo limpo + logo com fade) e anexado como mais um
"segmento" na mesma cadeia de segmentos+transições da Fase 5, entrando com
corte seco (a suavidade vem do fade da própria logo, não de um dissolve de
vídeo) — assim "duração dos sonhos + duração do encerramento" bate exatamente
com a duração final, sem código novo de mescla.
Fase 8: trilha sonora com curva emocional + ducking sobre o áudio original.
Implementada como um PASSO FINAL SEPARADO (nova chamada de ffmpeg) que recebe
o vídeo já pronto da Fase 7 (vídeo + áudio original com transições/silêncio)
como entrada 0 e a música como entrada 1: o vídeo é copiado sem reencode
(`-c:v copy`) e só o áudio é remixado — preserva a separação lógica pedida
("cortes -> transições -> palavras -> encerramento -> mixagem musical") sem
duplicar nenhum código de mescla de vídeo.

Este módulo é independente da automação de Reels (`api/automacao_social.py`):
não importa nenhum helper de lá nem altera seu comportamento. A única coisa que
reaproveita é o próprio cache/autorização de vídeos originais do institucional
(`api/video_institucional_drive.py`, criado na Fase 2) — assim, um vídeo já
baixado para preview/renderização anterior não precisa ser baixado de novo.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from api.video_institucional_drive import DriveAutorizacaoError, obter_preview_em_cache


BASE_DIR = Path(__file__).resolve().parent.parent
PASTA_INSTITUCIONAL = BASE_DIR / "landing" / "media" / "institucional"

# Parâmetros de vídeo/áudio da V1 — mesmos para as duas orientações.
FPS_SAIDA = 30
PRESET_VIDEO = "medium"
CRF_VIDEO = 20
BITRATE_AUDIO = "192k"
SAMPLE_RATE_AUDIO = 48000
CANAIS_AUDIO = 2

# Cada orientação define seu canvas de saída e a margem de "safe area" para o
# texto (fração da altura reservada no topo/rodapé — o vertical reserva mais
# porque é o formato publicado como Reels, cuja interface do Instagram cobre
# boa parte do topo e do rodapé da tela). Ponto de extensão futuro: aceitar
# `focus_x`/`focus_y` (ou `focus_position`) por trecho E por orientação, em vez
# de crop/pad sempre centralizados como nesta V1.
ORIENTACOES = {
    "vertical": {"largura": 1080, "altura": 1920, "margem_segura_fracao": 0.14},
    "horizontal": {"largura": 1920, "altura": 1080, "margem_segura_fracao": 0.08},
}

TOLERANCIA_DURACAO_TRECHO_SEGUNDOS = 0.1
TIMEOUT_FFMPEG_SEGUNDOS = 1800

DURACAO_TRANSICAO_PADRAO_SEGUNDOS = 0.6
DURACAO_TRANSICAO_MAXIMA_SEGUNDOS = 3.0
TRANSICOES_VALIDAS = ("corte", "dissolve")

# =========================================================
# PALAVRAS CINEMATOGRÁFICAS (identidade_narrativa.palavras)
# =========================================================

CAMINHO_FONTE_PALAVRAS = BASE_DIR / "assets" / "fonts" / "Montserrat-SemiBold.ttf"

IMPACTOS_VALIDOS = ("normal", "forte")
POSICOES_VALIDAS = ("centro", "superior", "inferior")

# Tamanho da fonte como fração da LARGURA do canvas (não da altura): a largura
# é a dimensão que realmente limita se uma palavra longa como "FULFILLMENT"
# cabe na tela, e usá-la mantém o texto proporcional nas duas orientações.
# Calibrado testando a palavra mais longa do preset ("FULFILLMENT", impacto
# forte): com 0.13 ela ficava a ~48px da borda em 1080px de largura (~4,4% —
# menos que a margem lateral que queríamos). 0.12 deixa ~8% de respiro de
# cada lado mesmo para essa palavra, sem precisar reduzir o texto dinamicamente.
FRACAO_FONTE_NORMAL = 0.095
FRACAO_FONTE_FORTE = 0.12

# Fade mais lento para palavras de impacto "forte" (item 5 da Fase 6).
FADE_PADRAO_SEGUNDOS = 0.5
FADE_FORTE_SEGUNDOS = 0.8

# Leve deslocamento vertical (opcional) durante o fade-in, como fração da
# altura do canvas — sutil, nunca um "bounce".
DESLOCAMENTO_ENTRADA_FRACAO = 0.02

# Lista de caracteres permitidos no texto de uma palavra. Ver
# `_validar_texto_palavra` para a explicação de por que validamos por uma
# lista de caracteres seguros em vez de tentar escapar caracteres livres.
PADRAO_TEXTO_SEGURO_PALAVRA = re.compile(r"^[\w\s.,!?\-]+$", re.UNICODE)


# =========================================================
# ENCERRAMENTO ROPE (identidade_narrativa.encerramento)
# =========================================================

# Logo oficial do Instituto ROPE. Encontrada no próprio projeto (idêntica em
# `imagens/logo.png` e `landing/assets/logo.png` — mesmo arquivo, dois
# lugares); referenciamos a cópia de `landing/assets` por já ser tratada como
# o asset "oficial" da identidade visual pelas páginas existentes
# (`landing/index.html`). Caminho fixo e resolvido no backend — o frontend
# nunca envia nem escolhe esse caminho (ver `_validar_logo_oficial`).
CAMINHO_LOGO_ROPE = BASE_DIR / "landing" / "assets" / "logo.png"
FORMATOS_LOGO_SUPORTADOS = (".png", ".jpg", ".jpeg")

# Cor de fundo do card de encerramento: amostrada diretamente dos cantos do
# próprio arquivo da logo (que não tem canal alfa — é uma imagem já composta
# sobre um fundo sólido). Usar essa mesma cor faz a logo aparecer "encaixada"
# sem nenhuma borda/caixa visível, sem inventar nenhuma cor nova de marca.
COR_FUNDO_ENCERRAMENTO = "0xF7F7F7"

# Tamanho da logo no encerramento: fração do canvas para manter uma aparência
# premium/institucional (bastante respiro, não uma logo gigante). No vertical
# a largura é a dimensão mais folgada; no horizontal, a altura é que é curta
# e por isso limita o tamanho — cada orientação usa a fração da dimensão que
# realmente a restringe. A proporção original da logo é sempre preservada
# (a outra dimensão é calculada a partir do aspect ratio real do arquivo,
# nunca esticada).
FRACAO_LARGURA_LOGO_VERTICAL = 0.55
FRACAO_ALTURA_LOGO_HORIZONTAL = 0.42

DURACAO_ENCERRAMENTO_PADRAO_SEGUNDOS = 6.0
FADE_ENTRADA_ENCERRAMENTO_PADRAO_SEGUNDOS = 1.0
FADE_SAIDA_ENCERRAMENTO_PADRAO_SEGUNDOS = 1.0
DURACAO_ENCERRAMENTO_MINIMA_SEGUNDOS = 3.0
DURACAO_ENCERRAMENTO_MAXIMA_SEGUNDOS = 10.0


# =========================================================
# TRILHA SONORA (identidade_narrativa.musica)
# =========================================================

# Pasta própria para trilhas — separada dos vídeos de saída — organizada por
# produção (cada upload vive em `audio/{producao_id}/`), o que também torna a
# limpeza trivial ao trocar/remover uma trilha.
PASTA_AUDIO_INSTITUCIONAL = BASE_DIR / "landing" / "media" / "institucional" / "audio"

FORMATOS_AUDIO_SUPORTADOS = (".mp3", ".wav", ".m4a", ".aac")
TAMANHO_MAXIMO_MUSICA_BYTES = 50 * 1024 * 1024  # 50MB — generoso para ~2min de áudio

# Referência de arquivo aceita no manifesto: exatamente o formato que o
# backend gera no upload (uuid hex + extensão suportada). Qualquer outro
# valor é rejeitado já no schema Pydantic — o frontend nunca escolhe nem
# envia um caminho livre (ver item 13 da Fase 8).
PADRAO_ARQUIVO_MUSICA_SEGURO = re.compile(
    r"^[0-9a-f]{32}(\.mp3|\.wav|\.m4a|\.aac)$", re.IGNORECASE
)

VOLUME_BASE_MUSICA_PADRAO = 0.8
FADE_IN_MUSICA_PADRAO_SEGUNDOS = 2.0
FADE_OUT_MUSICA_PADRAO_SEGUNDOS = 3.0

# Ducking: o quanto a música abaixa (fração do volume que ela já estaria
# tocando) durante um trecho com manter_audio_original=true, e a suavidade de
# entrada/saída dessa queda (nunca instantânea).
NIVEL_DUCKING_PADRAO = 0.3
ATAQUE_DUCKING_PADRAO_SEGUNDOS = 0.6
RETORNO_DUCKING_PADRAO_SEGUNDOS = 1.2

# Curva emocional padrão: pontos (fração da duração do CONTEÚDO, nível 0..1),
# espelhando a jornada DREAMS -> PURPOSE/EACH/PERSON -> SACRED/FAITH ->
# JOY/FULFILLMENT descrita no item 5/6 da Fase 8. Os últimos dois pontos usam
# a duração do ENCERRAMENTO (não mais uma fração do conteúdo) para a queda
# final ficar proporcional ao card, não ao vídeo inteiro.
CURVA_EMOCIONAL_PADRAO_CONTEUDO = (
    (0.00, 0.35),  # DREAMS — início delicado
    (0.25, 0.55),  # PURPOSE / EACH / PERSON — crescimento discreto
    (0.55, 0.70),  # SACRED / FAITH — aumento emocional
    (0.85, 1.00),  # JOY / FULFILLMENT — clímax
    (1.00, 0.80),  # fim do conteúdo, já cedendo espaço ao encerramento
)
CURVA_EMOCIONAL_PADRAO_ENCERRAMENTO_FRACAO_QUEDA = 0.4  # 40% do encerramento -> nível baixo
CURVA_EMOCIONAL_PADRAO_ENCERRAMENTO_NIVEL_QUEDA = 0.35


@dataclass
class ResultadoRenderInstitucional:
    caminho_vertical: Path
    caminho_horizontal: Path
    duracao_segundos: float
    tamanho_bytes_vertical: int
    tamanho_bytes_horizontal: int
    quantidade_trechos: int


def _resolver_binario(nome):
    """Localiza ffmpeg/ffprobe. Mesma estratégia usada em automacao_social.py,
    reimplementada aqui para não depender de um detalhe interno (prefixado com
    "_") daquele módulo."""
    configurado = os.getenv("FFMPEG_PATH") if nome == "ffmpeg" else None
    if configurado:
        candidato = Path(configurado)
        if nome == "ffprobe":
            candidato = candidato.with_name("ffprobe.exe")
        if candidato.exists():
            return str(candidato)

    encontrado = shutil.which(nome)
    if encontrado:
        return encontrado

    raiz_winget = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    padrao = f"Gyan.FFmpeg_*/ffmpeg-*/bin/{nome}.exe"
    candidatos = sorted(raiz_winget.glob(padrao), reverse=True)
    if candidatos:
        return str(candidatos[0])
    raise RuntimeError(f"{nome} não encontrado. Configure FFMPEG_PATH.")


def _executar(comando, timeout=TIMEOUT_FFMPEG_SEGUNDOS):
    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if resultado.returncode != 0:
        detalhe = resultado.stderr[-2000:]
        raise RuntimeError(f"Falha ao executar {Path(comando[0]).name}: {detalhe}")
    return resultado


def _obter_metadados_video(ffprobe, caminho):
    resultado = _executar(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(caminho)],
        timeout=60,
    )
    dados = json.loads(resultado.stdout)
    video = next((item for item in dados.get("streams", []) if item.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError(f"Arquivo sem faixa de vídeo: {Path(caminho).name}")
    duracao = float(video.get("duration") or dados.get("format", {}).get("duration") or 0)
    return {
        "duracao": duracao,
        "largura": int(video.get("width") or 0),
        "altura": int(video.get("height") or 0),
        "tem_audio": any(item.get("codec_type") == "audio" for item in dados.get("streams", [])),
    }


def _obter_metadados_audio(ffprobe, caminho):
    """Mesma ideia de `_obter_metadados_video`, mas para um arquivo só de
    áudio (trilha sonora) — procura uma faixa de áudio em vez de vídeo."""
    resultado = _executar(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(caminho)],
        timeout=60,
    )
    dados = json.loads(resultado.stdout)
    audio = next((item for item in dados.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not audio:
        raise RuntimeError(f"Arquivo sem faixa de áudio: {Path(caminho).name}")
    duracao = float(audio.get("duration") or dados.get("format", {}).get("duration") or 0)
    return {"duracao": duracao}


def _filtro_video(encaixe, largura, altura):
    """Filtro de normalização para o canvas de uma orientação (largura x altura).

    "conter": mostra o vídeo inteiro, com barras pretas (pad) quando a
    proporção não bate.
    "cobrir" (padrão): preenche todo o quadro cortando as bordas (crop),
    sempre centralizado nesta V1.
    """
    if encaixe == "conter":
        return (
            f"scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
            f"pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={FPS_SAIDA},format=yuv420p"
        )
    return (
        f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura},"
        f"fps={FPS_SAIDA},format=yuv420p"
    )


def _cortar_trecho(ffmpeg, origem, destino, inicio, duracao, manter_audio, encaixe, largura, altura):
    """Corta [inicio, inicio+duracao) do arquivo de origem e normaliza para o
    canvas informado. `-ss`/`-t` como opções de ENTRADA (antes do -i) usam o
    modo "accurate seek" (padrão do ffmpeg ao transcodificar): ele busca pelo
    keyframe mais próximo e decodifica-e-descarta até o ponto exato — rápido e
    preciso ao mesmo tempo, sem começar alguns frames antes/depois por causa
    de keyframes."""
    filtro_video = _filtro_video(encaixe, largura, altura)
    comando = [ffmpeg, "-y", "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}", "-i", str(origem)]

    if manter_audio:
        comando += [
            "-vf", filtro_video,
            "-af", f"aresample={SAMPLE_RATE_AUDIO}",
            "-map", "0:v:0", "-map", "0:a:0",
        ]
    else:
        # Mesmo sem áudio original, o segmento precisa de uma faixa de áudio
        # compatível (mesmos parâmetros) para poder ser mesclado com os outros.
        comando += [
            "-f", "lavfi", "-t", f"{duracao:.3f}", "-i", f"anullsrc=r={SAMPLE_RATE_AUDIO}:cl=stereo",
            "-filter_complex", f"[0:v]{filtro_video}[v]",
            "-map", "[v]", "-map", "1:a:0",
        ]

    comando += [
        "-c:v", "libx264", "-preset", PRESET_VIDEO, "-crf", str(CRF_VIDEO),
        "-c:a", "aac", "-b:a", BITRATE_AUDIO, "-ar", str(SAMPLE_RATE_AUDIO), "-ac", str(CANAIS_AUDIO),
        "-shortest", str(destino),
    ]
    _executar(comando)


# =========================================================
# TRANSIÇÕES
# =========================================================

def _normalizar_transicoes(trechos_ordenados):
    """Lê `transicao_entrada`/`duracao_transicao` de cada trecho, aplicando os
    padrões de compatibilidade para manifestos antigos que não têm esses
    campos: ausência de `transicao_entrada` -> "corte"; ausência de
    `duracao_transicao` -> DURACAO_TRANSICAO_PADRAO_SEGUNDOS. O primeiro
    trecho nunca tem transição de entrada (não existe um trecho anterior)."""
    transicoes = []
    for indice, trecho in enumerate(trechos_ordenados):
        if indice == 0:
            transicoes.append({"tipo": "corte", "duracao": 0.0})
            continue
        tipo = trecho.get("transicao_entrada") or "corte"
        duracao = float(trecho.get("duracao_transicao") or DURACAO_TRANSICAO_PADRAO_SEGUNDOS)
        transicoes.append({"tipo": tipo, "duracao": duracao})
    return transicoes


def _validar_transicoes(trechos_ordenados, transicoes):
    """Valida as transições ANTES de montar qualquer filter_complex. Levanta
    RuntimeError com mensagem indicando claramente quais trechos estão
    envolvidos."""
    for indice in range(1, len(trechos_ordenados)):
        transicao = transicoes[indice]
        trecho_atual = trechos_ordenados[indice]
        ordem_atual = trecho_atual.get("ordem", indice + 1)

        if transicao["tipo"] not in TRANSICOES_VALIDAS:
            raise RuntimeError(
                f"Trecho #{ordem_atual}: transicao_entrada inválida ({transicao['tipo']!r})."
            )
        if transicao["tipo"] != "dissolve":
            continue

        trecho_anterior = trechos_ordenados[indice - 1]
        ordem_anterior = trecho_anterior.get("ordem", indice)
        duracao_transicao = transicao["duracao"]
        duracao_anterior = float(trecho_anterior["fim_segundos"]) - float(trecho_anterior["inicio_segundos"])
        duracao_atual = float(trecho_atual["fim_segundos"]) - float(trecho_atual["inicio_segundos"])

        if duracao_transicao <= 0:
            raise RuntimeError(
                f"Trecho #{ordem_atual}: a duração da transição deve ser maior que zero."
            )
        if duracao_transicao > DURACAO_TRANSICAO_MAXIMA_SEGUNDOS:
            raise RuntimeError(
                f"Trecho #{ordem_atual}: a duração da transição ({duracao_transicao:.2f}s) "
                f"excede o limite de {DURACAO_TRANSICAO_MAXIMA_SEGUNDOS:.2f}s."
            )
        if duracao_transicao >= duracao_anterior:
            raise RuntimeError(
                f"Transição entre os trechos #{ordem_anterior} e #{ordem_atual}: "
                f"{duracao_transicao:.2f}s é maior ou igual à duração do trecho anterior "
                f"#{ordem_anterior} ({duracao_anterior:.2f}s)."
            )
        if duracao_transicao >= duracao_atual:
            raise RuntimeError(
                f"Transição entre os trechos #{ordem_anterior} e #{ordem_atual}: "
                f"{duracao_transicao:.2f}s é maior ou igual à duração do próprio trecho "
                f"#{ordem_atual} ({duracao_atual:.2f}s)."
            )


def calcular_duracao_estimada_producao(selecao_editorial):
    """Função explícita para a duração esperada da produção INTEIRA, a partir
    das durações nominais (fim - início) do manifesto: soma dos trechos menos
    a soma das durações de cada dissolve (que sobrepõe dois trechos). Usada
    para estimativa antes de renderizar (ex.: alerta de faixa 1:45-2:15 na
    interface). A duração usada de fato durante a renderização é recalculada
    com as durações REAIS de cada segmento já cortado (ver
    `_construir_filtro_transicoes`), para não acumular arredondamento."""
    if not selecao_editorial:
        return 0.0
    trechos_ordenados = sorted(selecao_editorial, key=lambda item: item.get("ordem", 0))
    transicoes = _normalizar_transicoes(trechos_ordenados)
    duracao_total = 0.0
    for indice, trecho in enumerate(trechos_ordenados):
        duracao_total += float(trecho["fim_segundos"]) - float(trecho["inicio_segundos"])
        if indice > 0 and transicoes[indice]["tipo"] == "dissolve":
            duracao_total -= transicoes[indice]["duracao"]
    return max(0.0, duracao_total)


def _construir_filtro_transicoes(duracoes_reais, transicoes):
    """Monta a cadeia de filtros que mescla os segmentos já cortados e
    normalizados (mesma resolução/fps/pix_fmt), respeitando a ordem editorial:
    "corte" vira um `concat` (sem sobreposição alguma); "dissolve" vira um
    `xfade` (vídeo) + `acrossfade` (áudio) com o offset calculado a partir da
    duração REAL acumulada do trecho já mesclado até aqui. Espera que os
    rótulos de entrada de vídeo/áudio já normalizados existam como `[v{i}n]`/
    `[a{i}n]` (feito por `_mesclar_com_transicoes` antes de chamar esta
    função)."""
    filtros = []
    acc_v = "[v0n]"
    acc_a = "[a0n]"
    acc_duracao = duracoes_reais[0]

    for indice in range(1, len(duracoes_reais)):
        transicao = transicoes[indice]
        rotulo_v = f"v{indice}m"
        rotulo_a = f"a{indice}m"
        entrada_v = f"[v{indice}n]"
        entrada_a = f"[a{indice}n]"

        if transicao["tipo"] == "dissolve":
            duracao_transicao = transicao["duracao"]
            offset = max(0.0, acc_duracao - duracao_transicao)
            filtros.append(
                f"{acc_v}{entrada_v}xfade=transition=fade:duration={duracao_transicao:.3f}:"
                f"offset={offset:.3f}[{rotulo_v}]"
            )
            filtros.append(
                f"{acc_a}{entrada_a}acrossfade=d={duracao_transicao:.3f}:c1=tri:c2=tri[{rotulo_a}]"
            )
            acc_duracao = acc_duracao + duracoes_reais[indice] - duracao_transicao
        else:
            filtros.append(f"{acc_v}{entrada_v}concat=n=2:v=1:a=0[{rotulo_v}]")
            filtros.append(f"{acc_a}{entrada_a}concat=n=2:v=0:a=1[{rotulo_a}]")
            acc_duracao = acc_duracao + duracoes_reais[indice]

        acc_v = f"[{rotulo_v}]"
        acc_a = f"[{rotulo_a}]"

    return ";".join(filtros), acc_v, acc_a, acc_duracao


def _formatar_caminho_para_filtro(caminho):
    """Converte um Path absoluto num valor seguro para usar dentro de uma
    opção de filtro do ffmpeg (ex.: `drawtext=fontfile=...`). No Windows, o
    ":" depois da letra da unidade (ex.: "C:") quebraria o parser de filtros
    (":" separa opções) e as barras invertidas confundem o parser — por isso
    convertemos para barras normais (o ffmpeg aceita) e escapamos o ":"."""
    texto = str(caminho).replace("\\", "/")
    return texto.replace(":", "\\:")


def _validar_texto_palavra(texto):
    """Valida o texto de uma palavra da narrativa ANTES de ele entrar em
    qualquer filtro do ffmpeg.

    Em vez de tentar escapar caracteres livres (apóstrofo, dois-pontos, barra,
    "%", etc.) para uso seguro dentro de `drawtext=text='...'`, validamos que
    o texto só contém um conjunto de caracteres claramente seguros (letras —
    incluindo acentuadas —, números, espaços e pontuação básica). Testamos na
    prática tentar escapar caracteres arbitrários e confirmamos que é frágil:
    um dois-pontos mal escapado quebra o parser de filtros e o restante da
    cadeia de opções do ffmpeg passa a ser desenhado como texto literal. Como
    o vocabulário desta fase é pequeno e conhecido (DREAMS, PURPOSE, EACH.,
    PERSON., SACRED, FAITH, JOY, FULFILLMENT), rejeitar com uma mensagem clara
    qualquer coisa fora desse conjunto seguro é mais robusto do que tentar
    escapar corretamente cada caractere especial do parser de filtros."""
    texto = (texto or "").strip()
    if not texto:
        raise RuntimeError("Uma palavra da narrativa está com o texto vazio.")
    if not PADRAO_TEXTO_SEGURO_PALAVRA.match(texto):
        raise RuntimeError(
            f"O texto da palavra {texto!r} contém caracteres não suportados. "
            "Use apenas letras, números, espaços e pontuação básica (. , ! ? -)."
        )
    return texto


def _validar_palavras(palavras):
    """Valida a lista inteira de palavras ANTES de montar qualquer filtro.
    Levanta RuntimeError com mensagem clara identificando a palavra
    envolvida. Palavras com `ativa: false` são ignoradas por completo (nem
    chegam a ser validadas quanto ao texto/tempos)."""
    for palavra in palavras:
        if not palavra.get("ativa", True):
            continue
        texto = _validar_texto_palavra(palavra.get("texto"))
        inicio = float(palavra.get("inicio_segundos", 0))
        fim = float(palavra.get("fim_segundos", 0))
        if fim <= inicio:
            raise RuntimeError(
                f"Palavra '{texto}': fim_segundos deve ser maior que inicio_segundos."
            )
        if inicio < 0:
            raise RuntimeError(f"Palavra '{texto}': inicio_segundos não pode ser negativo.")
        impacto = palavra.get("impacto") or "normal"
        if impacto not in IMPACTOS_VALIDOS:
            raise RuntimeError(f"Palavra '{texto}': impacto inválido ({impacto!r}).")
        posicao = palavra.get("posicao") or "centro"
        if posicao not in POSICOES_VALIDAS:
            raise RuntimeError(f"Palavra '{texto}': posição inválida ({posicao!r}).")


def _construir_filtro_palavra(palavra, indice, entrada_label, largura, altura, margem_segura_fracao):
    """Monta um único filtro `drawtext` para uma palavra, encadeado a partir
    de `entrada_label`. Fonte/posição/deslocamento são calculados
    proporcionalmente ao canvas (largura/altura), nunca com coordenadas
    absolutas — a mesma palavra fica visualmente equivalente no vertical e no
    horizontal."""
    texto = _validar_texto_palavra(palavra.get("texto"))
    inicio = float(palavra["inicio_segundos"])
    fim = float(palavra["fim_segundos"])
    duracao = fim - inicio
    impacto = palavra.get("impacto") or "normal"
    posicao = palavra.get("posicao") or "centro"

    # Fade nunca maior que 40% da duração da palavra, e nunca zero — garante
    # que uma palavra muito curta não gere uma expressão de alpha inválida
    # (divisão por um intervalo de tempo inexistente).
    fade_base = FADE_FORTE_SEGUNDOS if impacto == "forte" else FADE_PADRAO_SEGUNDOS
    fade = max(0.05, min(fade_base, duracao * 0.4))

    fracao_fonte = FRACAO_FONTE_FORTE if impacto == "forte" else FRACAO_FONTE_NORMAL
    fontsize = max(18, round(largura * fracao_fonte))
    borderw = max(1, round(fontsize * 0.035))

    margem_segura_px = altura * margem_segura_fracao
    if posicao == "superior":
        y_base = f"{margem_segura_px:.1f}"
    elif posicao == "inferior":
        y_base = f"(h-text_h-{margem_segura_px:.1f})"
    else:
        y_base = "(h-text_h)/2"

    deslocamento_px = altura * DESLOCAMENTO_ENTRADA_FRACAO
    y_expr = f"{y_base}+({deslocamento_px:.1f}*max(0,min(1,1-(t-{inicio:.3f})/{fade:.3f})))"

    alpha_expr = (
        f"if(lt(t,{inicio:.3f}),0,"
        f"if(lt(t,{inicio:.3f}+{fade:.3f}),(t-{inicio:.3f})/{fade:.3f},"
        f"if(lt(t,{fim:.3f}-{fade:.3f}),1,"
        f"if(lt(t,{fim:.3f}),({fim:.3f}-t)/{fade:.3f},0))))"
    )

    caminho_fonte = _formatar_caminho_para_filtro(CAMINHO_FONTE_PALAVRAS)
    rotulo_saida = f"txt{indice}"

    filtro = (
        f"{entrada_label}drawtext="
        f"fontfile='{caminho_fonte}':"
        f"text='{texto}':"
        f"fontsize={fontsize}:"
        f"fontcolor=white:"
        f"borderw={borderw}:bordercolor=black@0.5:"
        f"x='(w-text_w)/2':"
        f"y='{y_expr}':"
        f"alpha='{alpha_expr}':"
        f"enable='between(t,{inicio:.3f},{fim:.3f})'"
        f"[{rotulo_saida}]"
    )
    return filtro, f"[{rotulo_saida}]"


def _construir_filtros_palavras(palavras, entrada_label, largura, altura, margem_segura_fracao):
    """Encadeia um `drawtext` por palavra ATIVA, um em cima do outro, a
    partir do vídeo já mesclado (pós-transições). Retorna (lista_de_filtros,
    rotulo_final) — lista vazia e o próprio `entrada_label` se não houver
    nenhuma palavra ativa."""
    palavras_ativas = [palavra for palavra in palavras if palavra.get("ativa", True)]
    filtros = []
    atual = entrada_label
    for indice, palavra in enumerate(palavras_ativas):
        filtro, saida = _construir_filtro_palavra(
            palavra, indice, atual, largura, altura, margem_segura_fracao
        )
        filtros.append(filtro)
        atual = saida
    return filtros, atual


def _normalizar_encerramento(identidade_narrativa):
    """Lê `identidade_narrativa.encerramento`, aplicando os mesmos padrões de
    compatibilidade das outras seções: uma produção sem esse bloco (ou vinda
    de antes da Fase 7) é tratada como encerramento ativo com os defaults."""
    bruto = (identidade_narrativa or {}).get("encerramento") or {}
    return {
        "ativo": bruto.get("ativo", True),
        "duracao_segundos": float(bruto.get("duracao_segundos") or DURACAO_ENCERRAMENTO_PADRAO_SEGUNDOS),
        "fade_entrada": float(bruto.get("fade_entrada") or FADE_ENTRADA_ENCERRAMENTO_PADRAO_SEGUNDOS),
        "fade_saida": float(bruto.get("fade_saida") or FADE_SAIDA_ENCERRAMENTO_PADRAO_SEGUNDOS),
    }


def _validar_encerramento(encerramento):
    """Valida a configuração do encerramento ANTES de montar qualquer
    filter_complex — mesmo espírito de `_validar_transicoes`.

    A entrada no encerramento é sempre um CORTE seco (não um dissolve): o
    conteúdo dos sonhos toca por inteiro e o card é anexado na sequência sem
    tirar nenhum tempo dele — é assim que "duração dos sonhos + duração do
    encerramento = duração final" bate exatamente (item 7 da Fase 7). A
    suavidade da transição ("não quero brusco") vem do PRÓPRIO card: ele
    começa já no fundo limpo (sem vídeo nenhum por trás) e a logo entra com
    fade suave a partir daí — nunca de uma sobreposição com a cena anterior."""
    duracao = encerramento["duracao_segundos"]
    fade_entrada = encerramento["fade_entrada"]
    fade_saida = encerramento["fade_saida"]

    if duracao < DURACAO_ENCERRAMENTO_MINIMA_SEGUNDOS or duracao > DURACAO_ENCERRAMENTO_MAXIMA_SEGUNDOS:
        raise RuntimeError(
            f"Encerramento: duração ({duracao:.2f}s) fora da faixa permitida "
            f"({DURACAO_ENCERRAMENTO_MINIMA_SEGUNDOS:.0f}s a {DURACAO_ENCERRAMENTO_MAXIMA_SEGUNDOS:.0f}s)."
        )
    if fade_entrada <= 0 or fade_saida <= 0:
        raise RuntimeError("Encerramento: fade_entrada e fade_saida devem ser maiores que zero.")
    if fade_entrada + fade_saida >= duracao:
        raise RuntimeError(
            f"Encerramento: fade_entrada ({fade_entrada:.2f}s) + fade_saida ({fade_saida:.2f}s) "
            f"deve ser menor que a duração do encerramento ({duracao:.2f}s)."
        )


def calcular_duracao_total_com_encerramento(selecao_editorial, identidade_narrativa=None):
    """Função explícita para a duração final da produção, já somando o
    encerramento. Retorna (duracao_conteudo, duracao_encerramento,
    duracao_total) — os três números que a interface mostra separadamente
    (item 8 da Fase 7)."""
    duracao_conteudo = calcular_duracao_estimada_producao(selecao_editorial)
    encerramento = _normalizar_encerramento(identidade_narrativa)
    duracao_encerramento = encerramento["duracao_segundos"] if encerramento["ativo"] else 0.0
    return duracao_conteudo, duracao_encerramento, duracao_conteudo + duracao_encerramento


def _validar_logo_oficial(ffprobe):
    """Confirma que a logo oficial existe, tem um formato suportado e
    dimensões legíveis. O caminho é sempre o fixo (`CAMINHO_LOGO_ROPE`),
    resolvido aqui no backend — nunca aceito do frontend."""
    if not CAMINHO_LOGO_ROPE.exists():
        raise RuntimeError(f"Logo oficial do ROPE não encontrada em {CAMINHO_LOGO_ROPE}.")
    if CAMINHO_LOGO_ROPE.suffix.lower() not in FORMATOS_LOGO_SUPORTADOS:
        raise RuntimeError(f"Formato de logo não suportado: {CAMINHO_LOGO_ROPE.suffix}.")
    metadados = _obter_metadados_video(ffprobe, CAMINHO_LOGO_ROPE)
    if metadados["largura"] <= 0 or metadados["altura"] <= 0:
        raise RuntimeError("Não foi possível ler as dimensões da logo oficial do ROPE.")
    return metadados["largura"], metadados["altura"]


def obter_info_logo_oficial():
    """Informação pública sobre a logo oficial configurada (caminho relativo
    ao projeto, nunca o caminho absoluto do disco, e dimensões), para exibição
    somente-leitura na interface — ver item 12 da Fase 7."""
    ffprobe = _resolver_binario("ffprobe")
    largura, altura = _validar_logo_oficial(ffprobe)
    caminho_relativo = CAMINHO_LOGO_ROPE.relative_to(BASE_DIR)
    return {
        "arquivo": str(caminho_relativo).replace("\\", "/"),
        "largura": largura,
        "altura": altura,
    }


def _normalizar_musica(identidade_narrativa):
    """Lê `identidade_narrativa.musica`, aplicando os mesmos padrões de
    compatibilidade das outras seções: uma produção sem esse bloco (ou de
    antes da Fase 8) é tratada como "sem música" (ativa=False), nunca como
    erro."""
    bruto = (identidade_narrativa or {}).get("musica") or {}
    ducking_bruto = bruto.get("ducking") or {}
    arquivo = bruto.get("arquivo")
    return {
        "ativa": bool(bruto.get("ativa", False)) and bool(arquivo),
        "arquivo": arquivo,
        "volume_base": float(bruto.get("volume_base") or VOLUME_BASE_MUSICA_PADRAO),
        "fade_in": float(bruto.get("fade_in") or FADE_IN_MUSICA_PADRAO_SEGUNDOS),
        "fade_out": float(bruto.get("fade_out") or FADE_OUT_MUSICA_PADRAO_SEGUNDOS),
        "ducking": {
            "nivel_musica_durante_fala": float(
                ducking_bruto.get("nivel_musica_durante_fala") or NIVEL_DUCKING_PADRAO
            ),
            "ataque_segundos": float(ducking_bruto.get("ataque_segundos") or ATAQUE_DUCKING_PADRAO_SEGUNDOS),
            "retorno_segundos": float(ducking_bruto.get("retorno_segundos") or RETORNO_DUCKING_PADRAO_SEGUNDOS),
        },
    }


def _validar_referencia_musica(nome_arquivo):
    """Recusa qualquer coisa que não seja um nome de arquivo simples — sem
    barras, sem "..", sem caminho nenhum. A referência real só pode ter sido
    gerada pelo próprio backend no upload (ver `PADRAO_ARQUIVO_MUSICA_SEGURO`
    no schema Pydantic), mas validamos de novo aqui, no ponto onde o caminho é
    efetivamente montado, como segunda camada de defesa contra path
    traversal."""
    if not nome_arquivo or "/" in nome_arquivo or "\\" in nome_arquivo or ".." in nome_arquivo:
        raise RuntimeError("Referência de música inválida.")


def _resolver_musica(producao_id, nome_arquivo, ffprobe):
    """Resolve e valida o arquivo de música referenciado no manifesto,
    garantindo que o caminho final está mesmo dentro da pasta de áudio
    daquela produção (nunca aceito como caminho absoluto do frontend)."""
    _validar_referencia_musica(nome_arquivo)
    pasta_producao = (PASTA_AUDIO_INSTITUCIONAL / str(producao_id)).resolve()
    caminho = (pasta_producao / nome_arquivo).resolve()
    try:
        caminho.relative_to(pasta_producao)
    except ValueError:
        raise RuntimeError("Referência de música fora da pasta permitida.")
    if not caminho.exists():
        raise RuntimeError(f"Arquivo de música não encontrado: {nome_arquivo}.")
    if caminho.suffix.lower() not in FORMATOS_AUDIO_SUPORTADOS:
        raise RuntimeError(f"Formato de música não suportado: {caminho.suffix}.")
    metadados = _obter_metadados_audio(ffprobe, caminho)
    if metadados["duracao"] <= 0:
        raise RuntimeError("Não foi possível ler a duração do arquivo de música.")
    return caminho, metadados


def validar_arquivo_audio_upload(caminho):
    """Validação pública usada pelo endpoint de upload logo após salvar o
    arquivo em disco: confirma que é realmente um áudio legível, num formato
    suportado. Não compara com a duração do vídeo — isso só é conhecido no
    momento de renderizar (ver item 12 da Fase 8)."""
    if caminho.suffix.lower() not in FORMATOS_AUDIO_SUPORTADOS:
        raise RuntimeError(
            f"Formato de música não suportado: {caminho.suffix}. Use MP3, WAV ou M4A/AAC."
        )
    ffprobe = _resolver_binario("ffprobe")
    metadados = _obter_metadados_audio(ffprobe, caminho)
    if metadados["duracao"] <= 0:
        raise RuntimeError("Não foi possível ler a duração deste arquivo de áudio.")
    return metadados


def resolver_musica_institucional(producao_id, nome_arquivo):
    """Wrapper público de `_resolver_musica` para uso fora deste módulo (ex.:
    a rota de preview do áudio) sem precisar conhecer nem resolver o
    ffprobe."""
    ffprobe = _resolver_binario("ffprobe")
    return _resolver_musica(producao_id, nome_arquivo, ffprobe)


def _calcular_janelas_ducking(trechos_ordenados, transicoes, metadados_por_arquivo):
    """Calcula, na timeline final (nominal, mesma lógica de acumulação de
    `_construir_filtro_transicoes`), as janelas [início, fim] de cada trecho
    que efetivamente toca áudio original (manter_audio_original=true E o
    vídeo de origem realmente tem faixa de áudio — mesma regra usada ao
    cortar os trechos). Também devolve a duração nominal total do conteúdo,
    de brinde, já que o cálculo já percorre todos os trechos."""
    janelas_ducking = []
    acc_fim = 0.0
    for indice, trecho in enumerate(trechos_ordenados):
        duracao_trecho = float(trecho["fim_segundos"]) - float(trecho["inicio_segundos"])
        if indice == 0:
            inicio = 0.0
        else:
            transicao = transicoes[indice]
            inicio = (acc_fim - transicao["duracao"]) if transicao["tipo"] == "dissolve" else acc_fim
        fim = inicio + duracao_trecho
        acc_fim = fim

        metadados_origem = metadados_por_arquivo[trecho["drive_file_id"]]
        manter_audio_efetivo = bool(trecho.get("manter_audio_original")) and metadados_origem["tem_audio"]
        if manter_audio_efetivo:
            janelas_ducking.append((inicio, fim))

    return janelas_ducking, acc_fim


def _construir_pontos_curva_musica(duracao_conteudo, duracao_encerramento):
    """Pontos (tempo_em_segundos, nível 0..1) da curva emocional padrão,
    escalados para a duração REAL desta produção — igual em espírito ao
    preset de palavras da Fase 6, mas usando frações diretamente (não precisa
    de uma "duração de referência" porque frações já são independentes de
    duração)."""
    pontos = [
        (fracao * duracao_conteudo, nivel) for fracao, nivel in CURVA_EMOCIONAL_PADRAO_CONTEUDO
    ]
    if duracao_encerramento > 0:
        pontos.append((
            duracao_conteudo + duracao_encerramento * CURVA_EMOCIONAL_PADRAO_ENCERRAMENTO_FRACAO_QUEDA,
            CURVA_EMOCIONAL_PADRAO_ENCERRAMENTO_NIVEL_QUEDA,
        ))
        pontos.append((duracao_conteudo + duracao_encerramento, 0.0))
    return pontos


def _construir_expressao_interpolacao(pontos):
    """Constrói uma expressão de eval do ffmpeg que interpola linearmente
    entre os pontos (tempo, nível) fornecidos — vale o último nível para
    qualquer t além do último ponto, e o primeiro segmento também cobre
    qualquer t anterior a ele (na prática sempre começamos em t=0)."""
    if len(pontos) == 1:
        return f"{pontos[0][1]:.4f}"
    expressao = f"{pontos[-1][1]:.4f}"
    for indice in range(len(pontos) - 2, -1, -1):
        t0, v0 = pontos[indice]
        t1, v1 = pontos[indice + 1]
        dt = max(1e-6, t1 - t0)
        segmento = f"({v0:.4f}+(({v1:.4f})-({v0:.4f}))*(t-{t0:.4f})/{dt:.4f})"
        expressao = f"if(lt(t,{t1:.4f}),{segmento},{expressao})"
    return expressao


def _construir_expressao_fade_musica(duracao_final, fade_in, fade_out):
    """Envelope de fade-in/fade-out da trilha inteira — garante início e fim
    em zero independentemente da forma da curva emocional."""
    inicio_fadeout = max(0.0, duracao_final - fade_out)
    return (
        f"if(lt(t,{fade_in:.4f}),max(0,t/{fade_in:.4f}),"
        f"if(lt(t,{inicio_fadeout:.4f}),1,"
        f"max(0,({duracao_final:.4f}-t)/{max(1e-6, fade_out):.4f})))"
    )


def _construir_expressao_janela_ducking(inicio, fim, nivel_baixo, ataque, retorno):
    """1.0 fora da janela [início, fim] (mais as rampas de ataque/retorno),
    `nivel_baixo` dentro dela — com transição suave, nunca instantânea, nas
    bordas (item 8 da Fase 8: "não quero uma queda instantânea agressiva")."""
    inicio_rampa = max(0.0, inicio - ataque)
    fim_rampa = fim + retorno
    rampa_entrada = (
        f"(1+(({nivel_baixo:.4f})-1)*(t-{inicio_rampa:.4f})/{max(1e-6, inicio - inicio_rampa):.4f})"
    )
    rampa_saida = (
        f"({nivel_baixo:.4f}+(1-({nivel_baixo:.4f}))*(t-{fim:.4f})/{max(1e-6, fim_rampa - fim):.4f})"
    )
    return (
        f"if(lt(t,{inicio_rampa:.4f}),1,"
        f"if(lt(t,{inicio:.4f}),{rampa_entrada},"
        f"if(lt(t,{fim:.4f}),{nivel_baixo:.4f},"
        f"if(lt(t,{fim_rampa:.4f}),{rampa_saida},1))))"
    )


def _combinar_janelas_ducking(expressoes):
    """Combina várias janelas de ducking pegando o MÍNIMO entre elas a cada
    instante — cada janela vale 1.0 longe de si mesma, então o mínimo só
    "morde" perto de alguma janela específica (elas não se sobrepõem na
    prática, já que vêm de trechos sequenciais)."""
    if not expressoes:
        return "1"
    resultado = expressoes[0]
    for expressao in expressoes[1:]:
        resultado = f"min({resultado},{expressao})"
    return resultado


def _aplicar_mixagem_musical(
    ffmpeg, video_entrada, caminho_musica, destino, duracao_final,
    duracao_conteudo, duracao_encerramento, musica, janelas_ducking,
):
    """Passo FINAL e SEPARADO: mescla a trilha (com curva emocional + fade +
    ducking) por cima do áudio que já existe no vídeo pronto da Fase 7
    (original nos trechos marcados, silêncio nos demais e no encerramento).
    O vídeo é copiado sem reencode (`-c:v copy`) — só o áudio é remixado."""
    pontos_curva = _construir_pontos_curva_musica(duracao_conteudo, duracao_encerramento)
    expressao_curva = _construir_expressao_interpolacao(pontos_curva)
    expressao_fade = _construir_expressao_fade_musica(duracao_final, musica["fade_in"], musica["fade_out"])

    ducking = musica["ducking"]
    expressoes_ducking = [
        _construir_expressao_janela_ducking(
            inicio, fim, ducking["nivel_musica_durante_fala"],
            ducking["ataque_segundos"], ducking["retorno_segundos"],
        )
        for inicio, fim in janelas_ducking
    ]
    expressao_ducking = _combinar_janelas_ducking(expressoes_ducking)

    expressao_volume = (
        f"{musica['volume_base']:.4f}*({expressao_fade})*({expressao_curva})*({expressao_ducking})"
    )

    # `normalize=0` no amix: preferimos controlar o ganho explicitamente pela
    # nossa própria expressão de volume (previsível, mensurável) em vez de
    # depender da normalização automática do ffmpeg. O `alimiter` no final é
    # só uma rede de segurança contra clipping, não um processamento de
    # loudness (ver item 11 do relatório da Fase 8).
    filtro = (
        f"[1:a]atrim=0:{duracao_final:.3f},asetpts=PTS-STARTPTS,"
        f"aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE_AUDIO}:channel_layouts=stereo,"
        f"volume=eval=frame:volume='{expressao_volume}'[musica];"
        f"[0:a][musica]amix=inputs=2:duration=first:normalize=0,"
        f"alimiter=limit=0.97:attack=5:release=50[aout]"
    )

    comando = [
        ffmpeg, "-y",
        "-i", str(video_entrada),
        "-i", str(caminho_musica),
        "-filter_complex", filtro,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", BITRATE_AUDIO, "-ar", str(SAMPLE_RATE_AUDIO), "-ac", str(CANAIS_AUDIO),
        "-movflags", "+faststart",
        str(destino),
    ]
    _executar(comando)


def _construir_segmento_encerramento(
    ffmpeg, destino, largura, altura, duracao, fade_entrada, fade_saida,
    largura_logo_original, altura_logo_original,
):
    """Gera o card de encerramento como um segmento de vídeo independente
    (fundo sólido + logo oficial com fade-in/permanência/fade-out), com os
    mesmos parâmetros de codec/fps/pix_fmt/áudio dos demais segmentos — assim
    ele entra na mesclagem (`_mesclar_com_transicoes`) como "só mais um
    segmento", reaproveitando o xfade/acrossfade da Fase 5 sem nenhum código
    novo de mescla. Preserva a proporção original da logo (nunca estica)."""
    aspecto_logo = largura_logo_original / altura_logo_original
    if altura >= largura:
        logo_w = round(largura * FRACAO_LARGURA_LOGO_VERTICAL)
        logo_h = round(logo_w / aspecto_logo)
    else:
        logo_h = round(altura * FRACAO_ALTURA_LOGO_HORIZONTAL)
        logo_w = round(logo_h * aspecto_logo)

    inicio_fade_saida = max(0.0, duracao - fade_saida)

    # A logo original não tem canal alfa (é uma imagem já composta sobre um
    # fundo sólido) — `format=rgba` cria um canal alfa opaco (255) para que o
    # `fade` com `alpha=1` tenha o que animar (fade da OPACIDADE da logo, não
    # um fade para preto).
    filtro_logo = (
        f"[1:v]scale={logo_w}:{logo_h},format=rgba,"
        f"fade=t=in:st=0:d={fade_entrada:.3f}:alpha=1,"
        f"fade=t=out:st={inicio_fade_saida:.3f}:d={fade_saida:.3f}:alpha=1[logo_anim]"
    )
    filtro_overlay = "[0:v][logo_anim]overlay=x=(W-w)/2:y=(H-h)/2:format=auto[cardv]"

    comando = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i",
        f"color=c={COR_FUNDO_ENCERRAMENTO}:s={largura}x{altura}:d={duracao:.3f}:r={FPS_SAIDA}",
        "-loop", "1", "-t", f"{duracao:.3f}", "-i", str(CAMINHO_LOGO_ROPE),
        "-f", "lavfi", "-t", f"{duracao:.3f}", "-i", f"anullsrc=r={SAMPLE_RATE_AUDIO}:cl=stereo",
        "-filter_complex", f"{filtro_logo};{filtro_overlay}",
        "-map", "[cardv]", "-map", "2:a:0",
        "-c:v", "libx264", "-preset", PRESET_VIDEO, "-crf", str(CRF_VIDEO), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", BITRATE_AUDIO, "-ar", str(SAMPLE_RATE_AUDIO), "-ac", str(CANAIS_AUDIO),
        "-shortest", str(destino),
    ]
    _executar(comando)


def _mesclar_com_transicoes(
    ffmpeg, segmentos, transicoes, duracoes_reais, palavras, largura, altura, margem_segura_fracao, saida
):
    """Uma única chamada de ffmpeg com todos os segmentos como entradas,
    mesclando-os na ordem editorial via corte seco (`concat`) ou dissolve
    (`xfade`/`acrossfade`), conforme `transicoes`, e só então desenhando as
    palavras ativas por cima do resultado já mesclado (pipeline conceitual:
    cortes -> normalização -> transições -> palavras -> arquivo final, tudo
    dentro do mesmo grafo de filtros, sem uma etapa de encode extra). Retorna
    a duração estimada (real) do resultado."""
    comando = [ffmpeg, "-y"]
    for segmento in segmentos:
        comando += ["-i", str(segmento)]

    if len(segmentos) == 1:
        video_apos_transicoes = "[0:v]"
        audio_final = "0:a:0"
        duracao_estimada = duracoes_reais[0]
        filtros_palavras, video_final = _construir_filtros_palavras(
            palavras, video_apos_transicoes, largura, altura, margem_segura_fracao
        )
        if filtros_palavras:
            comando += ["-filter_complex", ";".join(filtros_palavras), "-map", video_final, "-map", audio_final]
        else:
            comando += ["-map", "0:v:0", "-map", audio_final]
    else:
        # Normaliza cada entrada antes de mesclar — evita dois problemas reais
        # observados ao encadear xfade/concat com arquivos vindos de -i
        # separados: (1) "input link parameters do not match" quando o
        # sample_fmt do áudio decodificado varia; (2) o xfade recusar a
        # combinação com "timebase does not match" quando o vídeo de um
        # segmento carrega o timebase original do container (ex.: 1/15360) e
        # o de outro já passou por um filtro (que usa timebase 1/1000000) —
        # `settb=AVTB` força um timebase consistente em todas as entradas de
        # vídeo antes de qualquer xfade/concat.
        filtros_normalizacao_v = [
            f"[{indice}:v]settb=AVTB[v{indice}n]" for indice in range(len(segmentos))
        ]
        filtros_normalizacao_a = [
            f"[{indice}:a]aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE_AUDIO}:"
            f"channel_layouts=stereo[a{indice}n]"
            for indice in range(len(segmentos))
        ]
        filtro_mescla, rotulo_v, rotulo_a, duracao_estimada = _construir_filtro_transicoes(
            duracoes_reais, transicoes
        )
        filtros_palavras, rotulo_v_final = _construir_filtros_palavras(
            palavras, rotulo_v, largura, altura, margem_segura_fracao
        )
        filtro_complex = ";".join(
            filtros_normalizacao_v + filtros_normalizacao_a + [filtro_mescla] + filtros_palavras
        )
        comando += ["-filter_complex", filtro_complex, "-map", rotulo_v_final, "-map", rotulo_a]

    comando += [
        "-c:v", "libx264", "-preset", PRESET_VIDEO, "-crf", str(CRF_VIDEO), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", BITRATE_AUDIO, "-ar", str(SAMPLE_RATE_AUDIO), "-ac", str(CANAIS_AUDIO),
        "-movflags", "+faststart", str(saida),
    ]
    _executar(comando)
    return duracao_estimada


def _validar_video_final(ffprobe, caminho, duracao_esperada, largura_esperada, altura_esperada):
    metadados = _obter_metadados_video(ffprobe, caminho)
    if (metadados["largura"], metadados["altura"]) != (largura_esperada, altura_esperada):
        raise RuntimeError(
            f"Resolução final inesperada: {metadados['largura']}x{metadados['altura']} "
            f"(esperado {largura_esperada}x{altura_esperada})."
        )
    tolerancia = max(1.0, duracao_esperada * 0.05)
    if abs(metadados["duracao"] - duracao_esperada) > tolerancia:
        raise RuntimeError(
            f"Duração final ({metadados['duracao']:.2f}s) muito diferente da esperada "
            f"({duracao_esperada:.2f}s) considerando as transições."
        )
    if caminho.stat().st_size <= 0:
        raise RuntimeError("O vídeo final gerado está vazio.")
    return metadados


def renderizar_producao_institucional(producao_id, selecao_editorial, identidade_narrativa=None):
    """Renderiza as DUAS orientações (vertical 1080x1920 e horizontal
    1920x1080) do vídeo institucional a partir do `selecao_editorial` salvo no
    manifesto, aplicando as transições configuradas por trecho e, por cima do
    resultado já mesclado, as palavras ativas de `identidade_narrativa`.
    Levanta RuntimeError com mensagem clara em qualquer trecho/transição/
    palavra inválidos.

    Estratégia de atomicidade: as duas orientações são renderizadas e
    validadas inteiramente dentro da pasta temporária antes de qualquer
    arquivo ser publicado no destino final. Só depois que AMBAS tiverem
    sucesso é que os dois arquivos são movidos para
    `landing/media/institucional/{id}/`. Se qualquer uma das duas falhar
    (por exemplo, o horizontal falhar depois do vertical já ter sido gerado
    com sucesso na pasta temporária), a função inteira levanta a exceção sem
    publicar nada — o chamador (endpoint) marca a produção inteira como ERRO e
    nem `video_vertical_path` nem `video_horizontal_path` são atualizados.
    Isso é intencional: PRONTO deve sempre significar que as duas versões
    solicitadas existem, nunca uma mistura de versão nova + antiga ou de uma
    versão pronta + uma faltando."""
    if not selecao_editorial:
        raise RuntimeError(
            "A seleção editorial está vazia. Adicione ao menos um trecho antes de renderizar."
        )

    ffmpeg = _resolver_binario("ffmpeg")
    ffprobe = _resolver_binario("ffprobe")

    trechos_ordenados = sorted(selecao_editorial, key=lambda item: item.get("ordem", 0))
    transicoes = _normalizar_transicoes(trechos_ordenados)
    _validar_transicoes(trechos_ordenados, transicoes)

    # A filtragem por `ativa` acontece dentro de `_construir_filtros_palavras`;
    # aqui só validamos a lista inteira (mesmo as inativas precisam ter forma
    # válida caso sejam reativadas depois).
    palavras = list((identidade_narrativa or {}).get("palavras") or [])
    _validar_palavras(palavras)

    encerramento = _normalizar_encerramento(identidade_narrativa)
    largura_logo_original = altura_logo_original = None
    if encerramento["ativo"]:
        _validar_encerramento(encerramento)
        largura_logo_original, altura_logo_original = _validar_logo_oficial(ffprobe)

    # Música: resolvida e validada aqui (antes dos downloads) para falhar
    # cedo — inclusive a checagem de duração mínima (item 12 da Fase 8), que
    # já dá pra fazer com a duração NOMINAL do conteúdo, sem precisar baixar
    # nenhum vídeo-fonte ainda.
    musica = _normalizar_musica(identidade_narrativa)
    caminho_musica = None
    if musica["ativa"]:
        caminho_musica, metadados_musica = _resolver_musica(producao_id, musica["arquivo"], ffprobe)
        duracao_encerramento_ativa = encerramento["duracao_segundos"] if encerramento["ativo"] else 0.0
        duracao_final_esperada = calcular_duracao_estimada_producao(trechos_ordenados) + duracao_encerramento_ativa
        if metadados_musica["duracao"] < duracao_final_esperada - TOLERANCIA_DURACAO_TRECHO_SEGUNDOS:
            raise RuntimeError(
                f"A trilha sonora ({metadados_musica['duracao']:.1f}s) é mais curta que a duração "
                f"final prevista do vídeo ({duracao_final_esperada:.1f}s). Selecione uma trilha mais "
                "longa ou ajuste a duração da produção — esta V1 não repete a música em loop."
            )

    pasta_saida = PASTA_INSTITUCIONAL / str(producao_id)
    destino_vertical = pasta_saida / f"institucional_{producao_id}_vertical.mp4"
    destino_horizontal = pasta_saida / f"institucional_{producao_id}_horizontal.mp4"

    origem_por_arquivo = {}
    metadados_por_arquivo = {}

    with tempfile.TemporaryDirectory(prefix=f"dreamcare_institucional_render_{producao_id}_") as pasta:
        pasta_temporaria = Path(pasta)

        # 1) Baixar cada arquivo-fonte único apenas UMA VEZ — compartilhado
        #    pelas duas orientações (nenhum novo download entre elas).
        for trecho in trechos_ordenados:
            drive_file_id = trecho["drive_file_id"]
            if drive_file_id in origem_por_arquivo:
                continue
            ordem = trecho.get("ordem")
            nome_referencia = trecho.get("nome_arquivo") or drive_file_id
            try:
                caminho_cache, _arquivo_drive = obter_preview_em_cache(
                    trecho["drive_folder_id"], drive_file_id
                )
            except DriveAutorizacaoError as erro:
                raise RuntimeError(f"Trecho #{ordem} ({nome_referencia}): {erro}") from erro
            origem_por_arquivo[drive_file_id] = caminho_cache
            metadados_por_arquivo[drive_file_id] = _obter_metadados_video(ffprobe, caminho_cache)

        # 2) Validar cada intervalo contra a duração real do vídeo de origem.
        for trecho in trechos_ordenados:
            ordem = trecho.get("ordem")
            nome_referencia = trecho.get("nome_arquivo") or trecho["drive_file_id"]
            inicio = float(trecho["inicio_segundos"])
            fim = float(trecho["fim_segundos"])
            if fim <= inicio:
                raise RuntimeError(f"Trecho #{ordem} ({nome_referencia}) é inválido: fim <= início.")
            if inicio < 0:
                raise RuntimeError(f"Trecho #{ordem} ({nome_referencia}) tem início negativo.")
            metadados_origem = metadados_por_arquivo[trecho["drive_file_id"]]
            if fim > metadados_origem["duracao"] + TOLERANCIA_DURACAO_TRECHO_SEGUNDOS:
                raise RuntimeError(
                    f"Trecho #{ordem} ({nome_referencia}) vai até {fim:.2f}s, mas o vídeo "
                    f"original tem apenas {metadados_origem['duracao']:.2f}s."
                )

        # 2.5) Janelas de ducking na timeline final (nominal — a MESMA para
        #      as duas orientações, garantindo áudio idêntico entre elas,
        #      ver item 16 da Fase 8) e duração nominal do conteúdo, usada
        #      pela curva emocional da música.
        janelas_ducking, duracao_conteudo_nominal = _calcular_janelas_ducking(
            trechos_ordenados, transicoes, metadados_por_arquivo
        )
        duracao_encerramento_nominal = encerramento["duracao_segundos"] if encerramento["ativo"] else 0.0
        duracao_final_nominal = duracao_conteudo_nominal + duracao_encerramento_nominal

        # 3) Cortar+normalizar e mesclar para CADA orientação, a partir dos
        #    mesmos arquivos-fonte já baixados (nunca vertical -> horizontal).
        resultados_por_orientacao = {}
        for chave_orientacao, canvas in ORIENTACOES.items():
            segmentos = []
            duracoes_reais = []
            for posicao, trecho in enumerate(trechos_ordenados, start=1):
                origem = origem_por_arquivo[trecho["drive_file_id"]]
                metadados_origem = metadados_por_arquivo[trecho["drive_file_id"]]
                inicio = float(trecho["inicio_segundos"])
                fim = float(trecho["fim_segundos"])
                duracao = fim - inicio
                manter_audio = bool(trecho.get("manter_audio_original")) and metadados_origem["tem_audio"]
                encaixe = trecho.get("encaixe") or "cobrir"

                segmento = pasta_temporaria / f"segmento_{chave_orientacao}_{posicao:03d}.mp4"
                _cortar_trecho(
                    ffmpeg, origem, segmento, inicio, duracao, manter_audio, encaixe,
                    canvas["largura"], canvas["altura"],
                )
                segmentos.append(segmento)
                duracoes_reais.append(_obter_metadados_video(ffprobe, segmento)["duracao"])

            transicoes_com_encerramento = transicoes
            if encerramento["ativo"]:
                # O card de encerramento entra como só mais um segmento na
                # mesma cadeia, com um CORTE seco (não um dissolve): o
                # conteúdo dos sonhos toca por inteiro e o card é anexado
                # sem tirar nenhum tempo dele, para "duração dos sonhos +
                # duração do encerramento = duração final" bater exatamente
                # (item 7 da Fase 7). A suavidade ("não quero brusco") vem do
                # próprio card: ele já nasce no fundo limpo e a logo entra
                # com fade a partir daí — ver `_validar_encerramento`.
                segmento_encerramento = pasta_temporaria / f"encerramento_{chave_orientacao}.mp4"
                _construir_segmento_encerramento(
                    ffmpeg, segmento_encerramento, canvas["largura"], canvas["altura"],
                    encerramento["duracao_segundos"], encerramento["fade_entrada"],
                    encerramento["fade_saida"], largura_logo_original, altura_logo_original,
                )
                segmentos.append(segmento_encerramento)
                duracoes_reais.append(_obter_metadados_video(ffprobe, segmento_encerramento)["duracao"])
                transicoes_com_encerramento = transicoes + [{"tipo": "corte", "duracao": 0.0}]

            saida_temporaria = pasta_temporaria / f"saida_{chave_orientacao}.mp4"
            duracao_estimada = _mesclar_com_transicoes(
                ffmpeg, segmentos, transicoes_com_encerramento, duracoes_reais, palavras,
                canvas["largura"], canvas["altura"], canvas["margem_segura_fracao"],
                saida_temporaria,
            )
            metadados_finais = _validar_video_final(
                ffprobe, saida_temporaria, duracao_estimada, canvas["largura"], canvas["altura"]
            )

            resultado_arquivo = saida_temporaria
            if musica["ativa"]:
                # Passo FINAL e SEPARADO (item 15 da Fase 8): o vídeo pronto
                # da Fase 7 vira a entrada 0 (copiado sem reencode) e só o
                # áudio é remixado com a trilha. Usa a duração/janelas NOMINAIS
                # calculadas uma única vez acima — idênticas nas duas
                # orientações.
                saida_com_musica = pasta_temporaria / f"saida_{chave_orientacao}_musica.mp4"
                _aplicar_mixagem_musical(
                    ffmpeg, saida_temporaria, caminho_musica, saida_com_musica,
                    duracao_final_nominal, duracao_conteudo_nominal, duracao_encerramento_nominal,
                    musica, janelas_ducking,
                )
                metadados_com_musica = _obter_metadados_video(ffprobe, saida_com_musica)
                if abs(metadados_com_musica["duracao"] - metadados_finais["duracao"]) > 1.0:
                    raise RuntimeError(
                        f"Duração mudou inesperadamente após mixar a música "
                        f"({metadados_com_musica['duracao']:.2f}s vs {metadados_finais['duracao']:.2f}s)."
                    )
                resultado_arquivo = saida_com_musica

            resultados_por_orientacao[chave_orientacao] = (resultado_arquivo, metadados_finais)

        # 4) Só publica os arquivos finais depois que as DUAS orientações
        #    renderizaram e validaram com sucesso (ver docstring da função).
        pasta_saida.mkdir(parents=True, exist_ok=True)
        for destino in (destino_vertical, destino_horizontal):
            if destino.exists():
                destino.unlink()
        shutil.move(str(resultados_por_orientacao["vertical"][0]), str(destino_vertical))
        shutil.move(str(resultados_por_orientacao["horizontal"][0]), str(destino_horizontal))

    duracao_final = resultados_por_orientacao["vertical"][1]["duracao"]
    return ResultadoRenderInstitucional(
        caminho_vertical=destino_vertical,
        caminho_horizontal=destino_horizontal,
        duracao_segundos=duracao_final,
        tamanho_bytes_vertical=destino_vertical.stat().st_size,
        tamanho_bytes_horizontal=destino_horizontal.stat().st_size,
        quantidade_trechos=len(trechos_ordenados),
    )


# =========================================================
# PRESET "Aplicar narrativa ROPE"
# =========================================================

# Referência para uma produção de ~105s (1min45s, a ponta inferior da faixa
# recomendada). Todos os tempos abaixo são escalados por
# `duracao_producao / PRESET_ROPE_REFERENCIA_SEGUNDOS`, nunca usados como
# segundos absolutos fixos — uma produção de 1:50 ou 2:10 estica/comprime
# proporcionalmente a posição de cada palavra na timeline (item 12 da Fase 6).
# "EACH." e "PERSON." já incluem o ponto final propositalmente (efeito de
# frase sendo construída aos poucos, item 4).
PRESET_ROPE_REFERENCIA_SEGUNDOS = 105.0
PRESET_ROPE_PALAVRAS_REFERENCIA = (
    {"texto": "DREAMS", "inicio": 3, "fim": 9, "impacto": "forte", "posicao": "centro"},
    {"texto": "PURPOSE", "inicio": 17, "fim": 21, "impacto": "normal", "posicao": "centro"},
    {"texto": "EACH.", "inicio": 26, "fim": 29, "impacto": "normal", "posicao": "centro"},
    {"texto": "PERSON.", "inicio": 30, "fim": 34, "impacto": "normal", "posicao": "centro"},
    {"texto": "SACRED", "inicio": 44, "fim": 49, "impacto": "normal", "posicao": "superior"},
    {"texto": "FAITH", "inicio": 66, "fim": 73, "impacto": "forte", "posicao": "centro"},
    {"texto": "JOY", "inicio": 79, "fim": 83, "impacto": "normal", "posicao": "inferior"},
    {"texto": "FULFILLMENT", "inicio": 96, "fim": 104, "impacto": "forte", "posicao": "centro"},
)


def gerar_preset_narrativa_rope(duracao_estimada_producao):
    """Gera a lista de palavras do preset "Aplicar narrativa ROPE", com os
    tempos de cada palavra escalados proporcionalmente à duração estimada da
    produção (ver `calcular_duracao_estimada_producao`). Não fixa tempos
    absolutos — apenas a POSIÇÃO RELATIVA na timeline de referência de 105s.
    O resultado é um ponto de partida editável pelo usuário, não definitivo."""
    fator = (duracao_estimada_producao / PRESET_ROPE_REFERENCIA_SEGUNDOS) if duracao_estimada_producao > 0 else 1.0
    return [
        {
            "texto": item["texto"],
            "inicio_segundos": round(item["inicio"] * fator, 2),
            "fim_segundos": round(item["fim"] * fator, 2),
            "impacto": item["impacto"],
            "posicao": item["posicao"],
            "ativa": True,
        }
        for item in PRESET_ROPE_PALAVRAS_REFERENCIA
    ]
