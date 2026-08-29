"""Acesso somente-leitura ao Google Drive para o Vídeo Institucional ROPE.

Este módulo é independente da automação de Reels (`api/automacao_social.py`). Ele
reaproveita apenas funções públicas e inalteradas:

- `google_drive.conectar_drive` — autenticação/serviço do Drive.
- `analisar_sonho_drive.listar_itens_pasta` — listagem de uma pasta (já usada na
  análise de conteúdo, já traz `size` no retorno).

Não importa nenhum helper prefixado com "_" de `automacao_social.py`: aqueles helpers
são detalhes internos do fluxo de Reels (autorização "arquivo é filho direto da pasta
de um Reel já gerado", cache próprio dos Reels) e reaproveitá-los aqui criaria um
acoplamento frágil com uma automação que não pode mudar de comportamento. Em vez disso,
este módulo implementa sua própria varredura recursiva e seu próprio cache, cada um
adequado às regras do vídeo institucional (múltiplos sonhos, subpastas, sem relatório de
Reel associado).
"""

import hashlib
import re
import tempfile
import time
import uuid
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from analisar_sonho_drive import listar_itens_pasta
from google_drive import conectar_drive


MIME_PASTA = "application/vnd.google-apps.folder"
MAX_TAMANHO_VIDEO_PREVIEW = 500 * 1024 * 1024
PROFUNDIDADE_MAXIMA_SUBPASTAS = 8
PROFUNDIDADE_MAXIMA_VERIFICACAO_ANCESTRAL = 8

CACHE_ORIGINAIS_INSTITUCIONAL = Path(tempfile.gettempdir()) / "dreamcare_institucional_originais"
CACHE_TTL_SEGUNDOS = 24 * 60 * 60


class DriveAutorizacaoError(Exception):
    """Falha de validação/autorização de um item do Drive, com status HTTP sugerido."""

    def __init__(self, mensagem, status_code=400):
        super().__init__(mensagem)
        self.status_code = status_code


# =========================================================
# LISTAGEM RECURSIVA (percorre subpastas, como o exemplo pedido)
# =========================================================

def _listar_videos_recursivo(service, pasta_id, caminho="", profundidade=0):
    if profundidade > PROFUNDIDADE_MAXIMA_SUBPASTAS:
        return []

    videos = []
    itens = listar_itens_pasta(service, pasta_id)

    for item in itens:
        nome = item.get("name", "Sem nome")
        mime_type = item.get("mimeType", "")
        caminho_item = f"{caminho}/{nome}" if caminho else nome

        if mime_type == MIME_PASTA:
            videos.extend(
                _listar_videos_recursivo(service, item["id"], caminho_item, profundidade + 1)
            )
        elif mime_type.startswith("video/"):
            videos.append({
                "drive_file_id": item["id"],
                "nome": nome,
                "mime_type": mime_type,
                "tamanho_bytes": int(item["size"]) if item.get("size") else None,
                "caminho_relativo": caminho_item,
            })

    return videos


def listar_videos_do_sonho(drive_folder_id):
    """Retorna (nome_da_pasta, lista_de_videos) percorrendo a pasta e suas subpastas."""
    service = conectar_drive()
    try:
        pasta = service.files().get(
            fileId=drive_folder_id, fields="id,name,mimeType"
        ).execute()
    except HttpError as erro:
        if erro.resp.status == 404:
            raise DriveAutorizacaoError(
                "A pasta do Drive vinculada a este sonho não foi encontrada.", 404
            ) from erro
        raise

    if pasta.get("mimeType") != MIME_PASTA:
        raise DriveAutorizacaoError(
            "O identificador vinculado a este sonho não é uma pasta do Drive.", 400
        )

    videos = _listar_videos_recursivo(service, drive_folder_id)
    videos.sort(key=lambda video: video["caminho_relativo"].lower())
    return pasta.get("name", drive_folder_id), videos


# =========================================================
# AUTORIZAÇÃO POR ANCESTRALIDADE (evita confiar em dados do frontend)
# =========================================================

def _arquivo_pertence_a_pasta(service, drive_file_id, pasta_raiz_id):
    """Confere, subindo a árvore de pais do arquivo, que ele está dentro da pasta raiz.

    Isso evita duas coisas: (1) confiar num drive_folder_id enviado livremente pelo
    frontend, e (2) ter que revarrer a pasta inteira a cada preview só para confirmar
    associação — em vez disso, sobe a árvore a partir do próprio arquivo.
    """
    try:
        arquivo = service.files().get(
            fileId=drive_file_id,
            fields="id,name,mimeType,size,parents,modifiedTime",
        ).execute()
    except HttpError as erro:
        if erro.resp.status == 404:
            raise DriveAutorizacaoError(
                "O vídeo solicitado não foi encontrado no Drive.", 404
            ) from erro
        raise

    if not arquivo.get("mimeType", "").startswith("video/"):
        raise DriveAutorizacaoError("O arquivo solicitado não é um vídeo.", 400)

    nivel_atual = set(arquivo.get("parents") or [])
    profundidade = 0

    while nivel_atual:
        if pasta_raiz_id in nivel_atual:
            return arquivo

        if profundidade >= PROFUNDIDADE_MAXIMA_VERIFICACAO_ANCESTRAL:
            break

        proximo_nivel = set()
        for pasta_id in nivel_atual:
            try:
                pasta = service.files().get(fileId=pasta_id, fields="id,parents").execute()
            except HttpError:
                continue
            proximo_nivel.update(pasta.get("parents") or [])

        nivel_atual = proximo_nivel
        profundidade += 1

    raise DriveAutorizacaoError(
        "O vídeo solicitado não pertence à pasta autorizada deste sonho.", 403
    )


# =========================================================
# CACHE LOCAL (pasta própria, não compartilhada com os Reels)
# =========================================================

def obter_preview_em_cache(drive_folder_id, drive_file_id):
    """Valida a autorização do arquivo e devolve (caminho_local_em_cache, metadados)."""
    service = conectar_drive()
    arquivo = _arquivo_pertence_a_pasta(service, drive_file_id, drive_folder_id)

    tamanho = int(arquivo.get("size") or 0)
    if tamanho <= 0 or tamanho > MAX_TAMANHO_VIDEO_PREVIEW:
        raise DriveAutorizacaoError(
            "O vídeo excede o limite seguro de tamanho para preview.", 400
        )

    CACHE_ORIGINAIS_INSTITUCIONAL.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    for item_cache in CACHE_ORIGINAIS_INSTITUCIONAL.iterdir():
        if item_cache.is_file() and agora - item_cache.stat().st_mtime > CACHE_TTL_SEGUNDOS:
            item_cache.unlink(missing_ok=True)

    # Assinatura derivada do próprio arquivo (nunca do nome enviado pelo cliente),
    # o que impede path traversal e reaproveita o cache quando o arquivo não mudou.
    assinatura = hashlib.sha256(
        f"{drive_file_id}:{arquivo.get('modifiedTime')}:{tamanho}".encode("utf-8")
    ).hexdigest()[:24]
    extensao = Path(arquivo["name"]).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", extensao):
        extensao = ".mp4"
    destino = CACHE_ORIGINAIS_INSTITUCIONAL / f"{assinatura}{extensao}"

    if destino.exists() and destino.stat().st_size == tamanho:
        destino.touch()
        return destino, arquivo

    temporario = CACHE_ORIGINAIS_INSTITUCIONAL / f"{assinatura}.{uuid.uuid4().hex}.part"
    try:
        request = service.files().get_media(fileId=drive_file_id)
        with temporario.open("wb") as arquivo_local:
            downloader = MediaIoBaseDownload(arquivo_local, request)
            concluido = False
            while not concluido:
                _, concluido = downloader.next_chunk()
        if temporario.stat().st_size != tamanho:
            raise DriveAutorizacaoError(
                "O download do vídeo original ficou incompleto.", 502
            )
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)

    return destino, arquivo
