"""Motor de renderização FFmpeg do Vídeo Institucional ROPE.

Fase 4: pipeline vertical básico, corte seco.
Fase 5: transições configuráveis por trecho (corte/dissolve) e segunda
orientação horizontal (16:9), ambas a partir dos mesmos trechos-fonte
normalizados (nunca "vertical pronto -> cortar -> horizontal").

Este módulo é independente da automação de Reels (`api/automacao_social.py`):
não importa nenhum helper de lá nem altera seu comportamento. A única coisa que
reaproveita é o próprio cache/autorização de vídeos originais do institucional
(`api/video_institucional_drive.py`, criado na Fase 2) — assim, um vídeo já
baixado para preview/renderização anterior não precisa ser baixado de novo.
"""

import json
import os
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

# Cada orientação só muda o canvas de saída. Ponto de extensão futuro: aceitar
# `focus_x`/`focus_y` (ou `focus_position`) por trecho E por orientação, em vez
# de crop/pad sempre centralizados como nesta V1.
ORIENTACOES = {
    "vertical": {"largura": 1080, "altura": 1920},
    "horizontal": {"largura": 1920, "altura": 1080},
}

TOLERANCIA_DURACAO_TRECHO_SEGUNDOS = 0.1
TIMEOUT_FFMPEG_SEGUNDOS = 1800

DURACAO_TRANSICAO_PADRAO_SEGUNDOS = 0.6
DURACAO_TRANSICAO_MAXIMA_SEGUNDOS = 3.0
TRANSICOES_VALIDAS = ("corte", "dissolve")


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


def _mesclar_com_transicoes(ffmpeg, segmentos, transicoes, duracoes_reais, saida):
    """Uma única chamada de ffmpeg com todos os segmentos como entradas,
    mesclando-os na ordem editorial via corte seco (`concat`) ou dissolve
    (`xfade`/`acrossfade`), conforme `transicoes`. Retorna a duração estimada
    (real) do resultado."""
    comando = [ffmpeg, "-y"]
    for segmento in segmentos:
        comando += ["-i", str(segmento)]

    if len(segmentos) == 1:
        comando += ["-map", "0:v:0", "-map", "0:a:0"]
        duracao_estimada = duracoes_reais[0]
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
        filtro_complex = ";".join(filtros_normalizacao_v + filtros_normalizacao_a + [filtro_mescla])
        comando += ["-filter_complex", filtro_complex, "-map", rotulo_v, "-map", rotulo_a]

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


def renderizar_producao_institucional(producao_id, selecao_editorial):
    """Renderiza as DUAS orientações (vertical 1080x1920 e horizontal
    1920x1080) do vídeo institucional a partir do `selecao_editorial` salvo no
    manifesto, aplicando as transições configuradas por trecho. Levanta
    RuntimeError com mensagem clara em qualquer trecho/transição inválidos.

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

            saida_temporaria = pasta_temporaria / f"saida_{chave_orientacao}.mp4"
            duracao_estimada = _mesclar_com_transicoes(
                ffmpeg, segmentos, transicoes, duracoes_reais, saida_temporaria
            )
            metadados_finais = _validar_video_final(
                ffprobe, saida_temporaria, duracao_estimada, canvas["largura"], canvas["altura"]
            )
            resultados_por_orientacao[chave_orientacao] = (saida_temporaria, metadados_finais)

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
