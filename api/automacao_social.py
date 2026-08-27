import io
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from googleapiclient.http import MediaIoBaseDownload

from google_drive import conectar_drive


BASE_DIR = Path(__file__).resolve().parent.parent
PASTA_EDITADOS = BASE_DIR / "landing" / "media" / "editados"
MIME_PASTA = "application/vnd.google-apps.folder"
MAX_VIDEOS_DOWNLOAD = 8
MAX_TAMANHO_VIDEO = 300 * 1024 * 1024
MAX_TOTAL_DOWNLOAD = 900 * 1024 * 1024
MAX_DURACAO_ANALISE = 90.0
TRECHO_SEGUNDOS = 6.5
CACHE_ORIGINAIS = Path(tempfile.gettempdir()) / "dreamcare_revisao_originais"
CACHE_ORIGINAIS_TTL = 24 * 60 * 60


@dataclass
class ResultadoEdicao:
    caminho: Path
    relatorio: Path
    duracao: float
    tamanho_bytes: int
    quantidade_videos: int
    quantidade_trechos: int


def _chave_ordem_natural(nome):
    """Extrai a sequência numérica do nome para preservar a cronologia dos arquivos."""
    return tuple(int(numero) for numero in re.findall(r"\d+", Path(nome).stem))


def _listar_videos(service, pasta_id):
    """Lista somente os vídeos diretamente contidos na pasta, na ordem do Drive."""
    pasta = service.files().get(fileId=pasta_id, fields="id,name").execute()
    nome_pasta = pasta.get("name", pasta_id)
    videos = []
    token = None
    while True:
        resposta = service.files().list(
            q=f"'{pasta_id}' in parents and trashed=false",
            fields=(
                "nextPageToken, files("
                "id,name,mimeType,size,modifiedTime,parents,videoMediaMetadata)"
            ),
            pageToken=token,
            pageSize=1000,
        ).execute()
        for arquivo in resposta.get("files", []):
            if arquivo["mimeType"].startswith("video/"):
                arquivo["pasta_origem_id"] = pasta_id
                arquivo["pasta_origem_nome"] = nome_pasta
                videos.append(arquivo)
        token = resposta.get("nextPageToken")
        if not token:
            break
    videos.sort(
        key=lambda arquivo: _chave_ordem_natural(arquivo["name"]),
        reverse=True,
    )
    for posicao, arquivo in enumerate(videos, start=1):
        arquivo["posicao_original"] = posicao
    return videos


def _baixar_video(service, arquivo, destino):
    request = service.files().get_media(fileId=arquivo["id"])
    memoria = io.BytesIO()
    downloader = MediaIoBaseDownload(memoria, request)
    concluido = False
    while not concluido:
        _, concluido = downloader.next_chunk()
    destino.write_bytes(memoria.getvalue())


def obter_video_original_em_cache(drive_folder_id, drive_file_id):
    """Valida e guarda temporariamente um vídeo direto da pasta autorizada."""
    service = conectar_drive()
    arquivo = service.files().get(
        fileId=drive_file_id,
        fields="id,name,mimeType,size,modifiedTime,parents",
    ).execute()
    if drive_folder_id not in arquivo.get("parents", []):
        raise RuntimeError("O vídeo não pertence diretamente à pasta autorizada.")
    if not arquivo.get("mimeType", "").startswith("video/"):
        raise RuntimeError("O arquivo solicitado não é um vídeo autorizado.")
    tamanho = int(arquivo.get("size") or 0)
    if tamanho <= 0 or tamanho > MAX_TAMANHO_VIDEO:
        raise RuntimeError("O vídeo original excede o limite seguro de tamanho.")

    CACHE_ORIGINAIS.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    for item_cache in CACHE_ORIGINAIS.iterdir():
        if item_cache.is_file() and agora - item_cache.stat().st_mtime > CACHE_ORIGINAIS_TTL:
            item_cache.unlink(missing_ok=True)

    assinatura = hashlib.sha256(
        f"{drive_file_id}:{arquivo.get('modifiedTime')}:{tamanho}".encode("utf-8")
    ).hexdigest()[:24]
    extensao = Path(arquivo["name"]).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", extensao):
        extensao = ".mp4"
    destino = CACHE_ORIGINAIS / f"{assinatura}{extensao}"
    if destino.exists() and destino.stat().st_size == tamanho:
        destino.touch()
        return destino, arquivo

    temporario = CACHE_ORIGINAIS / f"{assinatura}.{uuid.uuid4().hex}.part"
    try:
        request = service.files().get_media(fileId=drive_file_id)
        with temporario.open("wb") as arquivo_local:
            downloader = MediaIoBaseDownload(arquivo_local, request)
            concluido = False
            while not concluido:
                _, concluido = downloader.next_chunk()
        if temporario.stat().st_size != tamanho:
            raise RuntimeError("O download do vídeo original ficou incompleto.")
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)
    return destino, arquivo


def _resolver_binario(nome):
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


def _executar(comando, timeout=900):
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
    resultado = _executar([
        ffprobe, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(caminho),
    ], timeout=60)
    dados = json.loads(resultado.stdout)
    video = next((item for item in dados.get("streams", []) if item.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError(f"Arquivo sem faixa de vídeo: {caminho.name}")
    duracao = float(video.get("duration") or dados.get("format", {}).get("duration") or 0)
    return {
        "duracao": duracao,
        "largura": int(video.get("width") or 0),
        "altura": int(video.get("height") or 0),
        "tem_audio": any(
            item.get("codec_type") == "audio" for item in dados.get("streams", [])
        ),
    }


def _pontuar_movimento(ffmpeg, caminho, inicio, duracao):
    filtro = (
        "fps=2,scale=160:-2,tblend=all_mode=difference,"
        "signalstats,metadata=print:key=lavfi.signalstats.YAVG,"
        "freezedetect=n=-50dB:d=1.2"
    )
    resultado = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}",
            "-i", str(caminho), "-an", "-vf", filtro, "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    valores = [
        float(valor)
        for valor in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", resultado.stderr)
    ]
    congelamentos = sum(
        float(valor)
        for valor in re.findall(r"lavfi\.freezedetect\.freeze_duration: ([0-9.]+)", resultado.stderr)
    )
    movimento = sum(valores) / len(valores) if valores else 0.0
    proporcao_congelada = min(1.0, congelamentos / max(duracao, 0.1))
    return round(max(0.0, movimento * (1.0 - proporcao_congelada)), 4)


def _candidatos_de_trechos(ffmpeg, arquivo_local, metadados):
    duracao_video = min(metadados["duracao"], MAX_DURACAO_ANALISE)
    duracao_trecho = min(TRECHO_SEGUNDOS, duracao_video)
    limite_inicio = max(0.0, duracao_video - duracao_trecho)
    pontos = sorted({
        round(limite_inicio * 0.12, 3),
        round(limite_inicio * 0.48, 3),
        round(limite_inicio * 0.82, 3),
    })
    return [
        {
            "inicio": inicio,
            "duracao": duracao_trecho,
            "movimento": _pontuar_movimento(
                ffmpeg, arquivo_local, inicio, duracao_trecho
            ),
        }
        for inicio in pontos
    ]


def _selecionar_arquivos_para_download(videos):
    elegiveis = [
        item for item in videos
        if int(item.get("size") or 0) <= MAX_TAMANHO_VIDEO
    ]
    if not elegiveis:
        raise RuntimeError("Nenhum vídeo está dentro do limite de tamanho configurado.")

    selecionados = []
    total = 0
    for arquivo in elegiveis:
        if len(selecionados) >= MAX_VIDEOS_DOWNLOAD:
            break
        tamanho = int(arquivo.get("size") or 0)
        if selecionados and total + tamanho > MAX_TOTAL_DOWNLOAD:
            break
        selecionados.append(arquivo)
        total += tamanho
    return selecionados


def _normalizar_trecho(ffmpeg, origem, destino, inicio, duracao, tem_audio):
    fade_saida = max(0.0, duracao - 0.15)
    video_filtro = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,"
        "format=yuv420p,fade=t=in:st=0:d=0.15,"
        f"fade=t=out:st={fade_saida:.3f}:d=0.15"
    )
    comando = [
        ffmpeg, "-y", "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}",
        "-i", str(origem),
    ]
    if tem_audio:
        comando += [
            "-vf", video_filtro,
            "-af", f"afade=t=in:st=0:d=0.15,afade=t=out:st={fade_saida:.3f}:d=0.15,aresample=48000",
            "-map", "0:v:0", "-map", "0:a:0", "-shortest",
        ]
    else:
        comando += [
            "-f", "lavfi", "-t", f"{duracao:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
            "-filter_complex", f"[0:v]{video_filtro}[v]",
            "-map", "[v]", "-map", "1:a:0", "-shortest",
        ]
    comando += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", str(destino),
    ]
    _executar(comando)


def _montar_reel(ffmpeg, segmentos, saida, duracao_maxima):
    lista = saida.with_suffix(".concat.txt")
    try:
        lista.write_text(
            "\n".join(
                f"file '{str(caminho).replace(chr(39), chr(39) * 2)}'"
                for caminho in segmentos
            ),
            encoding="utf-8",
        )
        _executar([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-t", f"{duracao_maxima:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart", str(saida),
        ])
    finally:
        lista.unlink(missing_ok=True)


def _validar_reel(ffprobe, caminho, duracao_maxima):
    metadados = _obter_metadados_video(ffprobe, caminho)
    if (metadados["largura"], metadados["altura"]) != (1080, 1920):
        raise RuntimeError("A prévia gerada não possui resolução 1080x1920.")
    if not 1 <= metadados["duracao"] <= duracao_maxima + 0.1:
        raise RuntimeError("A duração da prévia está fora do limite solicitado.")
    if caminho.stat().st_size <= 0:
        raise RuntimeError("A prévia gerada está vazia.")
    return metadados


def _validar_trechos_manuais(trechos, relatorio_atual, drive_folder_id):
    """Valida a revisão contra os arquivos já usados, sem aceitar outra pasta."""
    originais = {
        item["drive_file_id"]: item
        for item in relatorio_atual.get("trechos", [])
        if item.get("pasta_origem_id") == drive_folder_id
    }
    if not trechos:
        raise RuntimeError("A revisão precisa manter pelo menos um trecho.")
    if len(trechos) > MAX_VIDEOS_DOWNLOAD:
        raise RuntimeError("A revisão excede o limite de trechos permitido.")

    validados = []
    duracao_total = 0.0
    for ordem, trecho in enumerate(trechos, start=1):
        arquivo_id = trecho.get("drive_file_id")
        original = originais.get(arquivo_id)
        if not original:
            raise RuntimeError("A revisão contém um vídeo que não pertence ao Reel atual.")
        inicio = float(trecho.get("inicio_segundos", 0))
        fim = float(trecho.get("fim_segundos", 0))
        duracao = fim - inicio
        if inicio < 0 or duracao < 1.0:
            raise RuntimeError("Cada trecho deve ter início válido e ao menos 1 segundo.")
        duracao_total += duracao
        validados.append({
            "ordem": ordem,
            "drive_file_id": arquivo_id,
            "inicio": inicio,
            "fim": fim,
            "duracao": duracao,
            "original": original,
        })
    if duracao_total > 60.0 + 0.001:
        raise RuntimeError("A soma dos trechos não pode ultrapassar 60 segundos.")
    return validados


def renderizar_reel_revisado(
    drive_folder_id, producao_id, relatorio_atual_path, trechos, duracao_maxima=60
):
    """Cria uma nova versão usando somente intervalos revisados do Reel atual."""
    ffmpeg = _resolver_binario("ffmpeg")
    ffprobe = _resolver_binario("ffprobe")
    duracao_maxima = max(10.0, min(float(duracao_maxima), 60.0))
    relatorio_atual_path = Path(relatorio_atual_path)
    relatorio_atual = json.loads(relatorio_atual_path.read_text(encoding="utf-8"))
    if (
        relatorio_atual.get("producao_id") != producao_id
        or relatorio_atual.get("drive_folder_id") != drive_folder_id
    ):
        raise RuntimeError("O relatório não corresponde a esta produção e pasta.")
    revisados = _validar_trechos_manuais(trechos, relatorio_atual, drive_folder_id)

    service = conectar_drive()
    PASTA_EDITADOS.mkdir(parents=True, exist_ok=True)
    identificador = uuid.uuid4().hex
    saida = PASTA_EDITADOS / f"reel_{identificador}.mp4"
    caminho_relatorio = saida.with_suffix(".json")

    with tempfile.TemporaryDirectory(prefix="dreamcare_revisao_") as temporaria:
        pasta_temporaria = Path(temporaria)
        baixados = {}
        total_download = 0
        segmentos = []
        relatorio_trechos = []
        for item in revisados:
            arquivo_id = item["drive_file_id"]
            if arquivo_id not in baixados:
                arquivo = service.files().get(
                    fileId=arquivo_id,
                    fields="id,name,mimeType,size,parents",
                ).execute()
                if drive_folder_id not in arquivo.get("parents", []):
                    raise RuntimeError("Um vídeo revisado não pertence diretamente à pasta autorizada.")
                if not arquivo.get("mimeType", "").startswith("video/"):
                    raise RuntimeError("A revisão contém um arquivo que não é vídeo.")
                tamanho = int(arquivo.get("size") or 0)
                if tamanho > MAX_TAMANHO_VIDEO or total_download + tamanho > MAX_TOTAL_DOWNLOAD:
                    raise RuntimeError("A revisão excede o limite seguro de download.")
                destino = pasta_temporaria / f"fonte_{len(baixados) + 1}{Path(arquivo['name']).suffix or '.mp4'}"
                _baixar_video(service, arquivo, destino)
                baixados[arquivo_id] = (arquivo, destino, _obter_metadados_video(ffprobe, destino))
                total_download += tamanho

            arquivo, origem, metadados = baixados[arquivo_id]
            if item["fim"] > metadados["duracao"] + 0.05:
                raise RuntimeError(f"O trecho ultrapassa a duração de {arquivo['name']}.")
            segmento = pasta_temporaria / f"trecho_{item['ordem']:02d}.mp4"
            _normalizar_trecho(
                ffmpeg, origem, segmento, item["inicio"], item["duracao"], metadados["tem_audio"]
            )
            segmentos.append(segmento)
            relatorio_trechos.append({
                "ordem": item["ordem"],
                "drive_file_id": arquivo_id,
                "arquivo": arquivo["name"],
                "posicao_original": item["original"].get("posicao_original"),
                "pasta_origem_id": drive_folder_id,
                "pasta_origem_nome": item["original"].get("pasta_origem_nome"),
                "inicio_segundos": round(item["inicio"], 3),
                "fim_segundos": round(item["fim"], 3),
                "duracao_segundos": round(item["duracao"], 3),
                "pontuacao_movimento": _pontuar_movimento(
                    ffmpeg, origem, item["inicio"], item["duracao"]
                ),
                "audio_original": metadados["tem_audio"],
                "resolucao_original": f"{metadados['largura']}x{metadados['altura']}",
                "duracao_video_original": round(metadados["duracao"], 3),
            })
        _montar_reel(ffmpeg, segmentos, saida, duracao_maxima)

    validacao = _validar_reel(ffprobe, saida, duracao_maxima)
    relatorio = {
        "versao_editor": 3,
        "tipo_edicao": "REVISAO_MANUAL",
        "versao_anterior": str(relatorio_atual_path),
        "producao_id": producao_id,
        "drive_folder_id": drive_folder_id,
        "arquivo_saida": str(saida),
        "resolucao": f"{validacao['largura']}x{validacao['altura']}",
        "duracao_segundos": round(validacao["duracao"], 3),
        "tamanho_bytes": saida.stat().st_size,
        "logo_aplicada": False,
        "pastas_permitidas": [drive_folder_id],
        "videos_baixados": len(baixados),
        "videos_utilizados": len({item["drive_file_id"] for item in relatorio_trechos}),
        "trechos_utilizados": len(relatorio_trechos),
        "trechos": relatorio_trechos,
        "publicacao_automatica": False,
        "status_destino": "AGUARDANDO_APROVACAO",
    }
    caminho_relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return ResultadoEdicao(
        caminho=saida,
        relatorio=caminho_relatorio,
        duracao=validacao["duracao"],
        tamanho_bytes=saida.stat().st_size,
        quantidade_videos=relatorio["videos_utilizados"],
        quantidade_trechos=relatorio["trechos_utilizados"],
    )


def preparar_reel(drive_folder_id, producao_id, duracao_maxima=60):
    ffmpeg = _resolver_binario("ffmpeg")
    ffprobe = _resolver_binario("ffprobe")
    duracao_maxima = max(10.0, min(float(duracao_maxima), 60.0))

    service = conectar_drive()
    videos = _listar_videos(service, drive_folder_id)
    if not videos:
        raise RuntimeError("Nenhum vídeo foi encontrado nesta pasta do Drive.")

    arquivos_escolhidos = _selecionar_arquivos_para_download(videos)
    PASTA_EDITADOS.mkdir(parents=True, exist_ok=True)
    identificador = uuid.uuid4().hex
    saida = PASTA_EDITADOS / f"reel_{identificador}.mp4"
    caminho_relatorio = PASTA_EDITADOS / f"reel_{identificador}.json"

    with tempfile.TemporaryDirectory(prefix="dreamcare_edicao_") as temporaria:
        pasta_temporaria = Path(temporaria)
        analisados = []
        for indice, arquivo in enumerate(arquivos_escolhidos, start=1):
            extensao = Path(arquivo["name"]).suffix or ".mp4"
            destino = pasta_temporaria / f"video_{indice}{extensao}"
            _baixar_video(service, arquivo, destino)
            metadados = _obter_metadados_video(ffprobe, destino)
            if metadados["duracao"] < 1.0:
                continue
            candidatos = _candidatos_de_trechos(ffmpeg, destino, metadados)
            melhor = max(candidatos, key=lambda item: item["movimento"])
            analisados.append({
                "arquivo_drive": arquivo,
                "arquivo_local": destino,
                "metadados": metadados,
                "trecho": melhor,
                "candidatos": candidatos,
            })

        if not analisados:
            raise RuntimeError("Nenhum vídeo válido permaneceu após a análise.")

        conteudo_disponivel = duracao_maxima
        escolhidos = []
        acumulado = 0.0
        for item in analisados:
            if acumulado >= conteudo_disponivel - 0.1:
                break
            trecho = dict(item["trecho"])
            trecho["duracao"] = min(trecho["duracao"], conteudo_disponivel - acumulado)
            if trecho["duracao"] < 1.0:
                break
            escolhidos.append((item, trecho))
            acumulado += trecho["duracao"]

        segmentos = []
        relatorio_trechos = []
        for indice, (item, trecho) in enumerate(escolhidos, start=1):
            segmento = pasta_temporaria / f"trecho_{indice:02d}.mp4"
            _normalizar_trecho(
                ffmpeg,
                item["arquivo_local"],
                segmento,
                trecho["inicio"],
                trecho["duracao"],
                item["metadados"]["tem_audio"],
            )
            segmentos.append(segmento)
            relatorio_trechos.append({
                "ordem": indice,
                "drive_file_id": item["arquivo_drive"]["id"],
                "arquivo": item["arquivo_drive"]["name"],
                "posicao_original": item["arquivo_drive"]["posicao_original"],
                "pasta_origem_id": item["arquivo_drive"]["pasta_origem_id"],
                "pasta_origem_nome": item["arquivo_drive"]["pasta_origem_nome"],
                "inicio_segundos": round(trecho["inicio"], 3),
                "fim_segundos": round(trecho["inicio"] + trecho["duracao"], 3),
                "duracao_segundos": round(trecho["duracao"], 3),
                "pontuacao_movimento": trecho["movimento"],
                "audio_original": item["metadados"]["tem_audio"],
                "resolucao_original": (
                    f"{item['metadados']['largura']}x{item['metadados']['altura']}"
                ),
                "duracao_video_original": round(item["metadados"]["duracao"], 3),
                "alternativas": [
                    {
                        "inicio_segundos": round(candidato["inicio"], 3),
                        "fim_segundos": round(
                            candidato["inicio"] + candidato["duracao"], 3
                        ),
                        "duracao_segundos": round(candidato["duracao"], 3),
                        "pontuacao_movimento": candidato["movimento"],
                    }
                    for candidato in item["candidatos"]
                ],
            })
        _montar_reel(ffmpeg, segmentos, saida, duracao_maxima)

    validacao = _validar_reel(ffprobe, saida, duracao_maxima)
    relatorio = {
        "versao_editor": 2,
        "producao_id": producao_id,
        "drive_folder_id": drive_folder_id,
        "arquivo_saida": str(saida),
        "resolucao": f"{validacao['largura']}x{validacao['altura']}",
        "duracao_segundos": round(validacao["duracao"], 3),
        "tamanho_bytes": saida.stat().st_size,
        "logo_aplicada": False,
        "pastas_permitidas": [drive_folder_id],
        "limites": {
            "max_videos_download": MAX_VIDEOS_DOWNLOAD,
            "max_tamanho_video_bytes": MAX_TAMANHO_VIDEO,
            "max_total_download_bytes": MAX_TOTAL_DOWNLOAD,
        },
        "videos_baixados": len(arquivos_escolhidos),
        "videos_utilizados": len({item["drive_file_id"] for item in relatorio_trechos}),
        "trechos_utilizados": len(relatorio_trechos),
        "trechos": relatorio_trechos,
        "publicacao_automatica": False,
        "status_destino": "AGUARDANDO_APROVACAO",
    }
    caminho_relatorio.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ResultadoEdicao(
        caminho=saida,
        relatorio=caminho_relatorio,
        duracao=validacao["duracao"],
        tamanho_bytes=saida.stat().st_size,
        quantidade_videos=relatorio["videos_utilizados"],
        quantidade_trechos=relatorio["trechos_utilizados"],
    )


def _post_form(url, dados):
    requisicao = Request(url, data=urlencode(dados).encode("utf-8"), method="POST")
    try:
        with urlopen(requisicao, timeout=60) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except HTTPError as erro:
        corpo = erro.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"A Meta recusou a publicação: {corpo}") from erro
    except URLError as erro:
        raise RuntimeError(f"Não foi possível acessar a API da Meta: {erro}") from erro


def _get_json(url, parametros):
    try:
        with urlopen(f"{url}?{urlencode(parametros)}", timeout=60) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except (HTTPError, URLError) as erro:
        raise RuntimeError(f"Não foi possível consultar a API da Meta: {erro}") from erro


def publicar_reel(video_url, legenda):
    conta_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    versao = os.getenv("META_GRAPH_API_VERSION")
    if not conta_id or not token or not versao:
        raise RuntimeError(
            "Configure INSTAGRAM_ACCOUNT_ID, INSTAGRAM_ACCESS_TOKEN e META_GRAPH_API_VERSION antes de publicar."
        )

    base = f"https://graph.facebook.com/{versao}/{conta_id}"
    container = _post_form(f"{base}/media", {
        "media_type": "REELS", "video_url": video_url, "caption": legenda,
        "share_to_feed": "true", "access_token": token,
    })
    container_id = container.get("id")
    if not container_id:
        raise RuntimeError("A Meta não retornou o identificador da mídia.")

    for _ in range(30):
        estado = _get_json(
            f"https://graph.facebook.com/{versao}/{container_id}",
            {"fields": "status_code,status", "access_token": token},
        )
        if estado.get("status_code") == "FINISHED":
            break
        if estado.get("status_code") in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"A Meta não processou o vídeo: {estado.get('status', estado)}")
        time.sleep(5)
    else:
        raise RuntimeError("A Meta ainda não terminou de processar o vídeo.")

    publicado = _post_form(f"{base}/media_publish", {
        "creation_id": container_id, "access_token": token,
    })
    if not publicado.get("id"):
        raise RuntimeError("A Meta não confirmou a publicação do Reel.")
    return publicado["id"]
