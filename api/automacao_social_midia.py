"""Navegação/validação somente-leitura no Google Drive para adicionar mídia
(vídeo ou foto) manualmente à seleção de um Reel, na tela de revisão.

Este módulo é independente da automação de Reels (`api/automacao_social.py`): não
importa nem é importado por nenhum helper prefixado com "_" de lá (aqueles são
detalhes internos do fluxo 100% automático — escolha de vídeos, pontuação de
movimento, cache de revisão — que não pode mudar de comportamento). Também não
importa nem é importado por `video_institucional_drive.py`/`video_institucional_render.py`
— mesmo racional já documentado naquele módulo: duplicar aqui a listagem
recursiva e a autorização por ancestralidade evita acoplar dois fluxos que
precisam evoluir sem afetar um ao outro.

Reaproveita só utilitários genéricos já usados por 3+ módulos:
`google_drive.conectar_drive` e `analisar_sonho_drive.listar_itens_pasta`.
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
MIME_IMAGENS_SUPORTADAS = ("image/jpeg", "image/png", "image/webp")
PROFUNDIDADE_MAXIMA_SUBPASTAS = 8
PROFUNDIDADE_MAXIMA_VERIFICACAO_ANCESTRAL = 8

# Mesmo teto de vídeo já usado pela automação (automacao_social.MAX_TAMANHO_VIDEO);
# fotos usam um teto bem menor, generoso para fotos de celular em alta resolução.
MAX_TAMANHO_VIDEO_MIDIA = 300 * 1024 * 1024
MAX_TAMANHO_IMAGEM_MIDIA = 30 * 1024 * 1024

CACHE_MIDIA_MANUAL = Path(tempfile.gettempdir()) / "dreamcare_reels_midia_manual"
CACHE_TTL_SEGUNDOS = 24 * 60 * 60


class MidiaAutorizacaoError(Exception):
    """Falha de validação/autorização de um item do Drive, com status HTTP sugerido."""

    def __init__(self, mensagem, status_code=400):
        super().__init__(mensagem)
        self.status_code = status_code


def _tipo_midia_por_mime(mime_type):
    """'video', 'imagem' ou None (arquivo ignorado pela navegação manual)."""
    if not mime_type:
        return None
    if mime_type.startswith("video/"):
        return "video"
    if mime_type in MIME_IMAGENS_SUPORTADAS:
        return "imagem"
    return None


# =========================================================
# LISTAGEM RECURSIVA (vídeo + foto, percorre subpastas)
# =========================================================

def _listar_midias_recursivo(service, pasta_id, nome_pasta, caminho="", profundidade=0):
    if profundidade > PROFUNDIDADE_MAXIMA_SUBPASTAS:
        return []

    midias = []
    itens = listar_itens_pasta(service, pasta_id)

    for item in itens:
        nome = item.get("name", "Sem nome")
        mime_type = item.get("mimeType", "")
        caminho_item = f"{caminho}/{nome}" if caminho else nome

        if mime_type == MIME_PASTA:
            midias.extend(
                _listar_midias_recursivo(
                    service, item["id"], nome, caminho_item, profundidade + 1
                )
            )
            continue

        tipo_midia = _tipo_midia_por_mime(mime_type)
        if tipo_midia is None:
            continue

        midias.append({
            "drive_file_id": item["id"],
            "nome": nome,
            "tipo_midia": tipo_midia,
            "mime_type": mime_type,
            "tamanho_bytes": int(item["size"]) if item.get("size") else None,
            "caminho_relativo": caminho_item,
            "pasta_origem_id": pasta_id,
            "pasta_origem_nome": nome_pasta,
        })

    return midias


def listar_midias_do_sonho(drive_folder_id):
    """Retorna (nome_da_pasta_raiz, lista_de_midias) percorrendo a pasta e suas
    subpastas, incluindo vídeos e fotos (jpeg/png/webp)."""
    service = conectar_drive()
    try:
        pasta = service.files().get(
            fileId=drive_folder_id, fields="id,name,mimeType"
        ).execute()
    except HttpError as erro:
        if erro.resp.status == 404:
            raise MidiaAutorizacaoError(
                "A pasta do Drive vinculada a este sonho não foi encontrada.", 404
            ) from erro
        raise

    if pasta.get("mimeType") != MIME_PASTA:
        raise MidiaAutorizacaoError(
            "O identificador vinculado a este sonho não é uma pasta do Drive.", 400
        )

    nome_pasta_raiz = pasta.get("name", drive_folder_id)
    midias = _listar_midias_recursivo(service, drive_folder_id, nome_pasta_raiz)
    midias.sort(key=lambda midia: midia["caminho_relativo"].lower())
    return nome_pasta_raiz, midias


# =========================================================
# AUTORIZAÇÃO POR ANCESTRALIDADE (evita confiar em dados do frontend)
# =========================================================

def _midia_pertence_a_pasta(service, drive_file_id, pasta_raiz_id):
    """Confere, subindo a árvore de pais do arquivo, que ele está dentro da
    pasta raiz do sonho — direto ou em qualquer subpasta. Nunca confia em um
    `pasta_origem_id`/`drive_folder_id` enviado pelo cliente: sempre resolve a
    partir do próprio `drive_file_id`."""
    try:
        arquivo = service.files().get(
            fileId=drive_file_id,
            fields="id,name,mimeType,size,parents,modifiedTime",
        ).execute()
    except HttpError as erro:
        if erro.resp.status == 404:
            raise MidiaAutorizacaoError(
                "A mídia solicitada não foi encontrada no Drive.", 404
            ) from erro
        raise

    tipo_midia = _tipo_midia_por_mime(arquivo.get("mimeType", ""))
    if tipo_midia is None:
        raise MidiaAutorizacaoError(
            "O arquivo solicitado não é um vídeo ou foto suportada.", 400
        )

    nivel_atual = set(arquivo.get("parents") or [])
    profundidade = 0

    while nivel_atual:
        if pasta_raiz_id in nivel_atual:
            arquivo["tipo_midia"] = tipo_midia
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

    raise MidiaAutorizacaoError(
        "A mídia solicitada não pertence à pasta autorizada deste sonho.", 403
    )


# =========================================================
# CACHE LOCAL (pasta própria, não compartilhada com os Reels/institucional)
# =========================================================

def obter_midia_em_cache(drive_folder_id, drive_file_id):
    """Valida a autorização/tamanho e devolve (caminho_local_em_cache, metadados,
    tipo_midia)."""
    service = conectar_drive()
    arquivo = _midia_pertence_a_pasta(service, drive_file_id, drive_folder_id)
    tipo_midia = arquivo["tipo_midia"]

    tamanho = int(arquivo.get("size") or 0)
    limite = MAX_TAMANHO_VIDEO_MIDIA if tipo_midia == "video" else MAX_TAMANHO_IMAGEM_MIDIA
    if tamanho <= 0 or tamanho > limite:
        raise MidiaAutorizacaoError(
            "O arquivo excede o limite seguro de tamanho.", 400
        )

    CACHE_MIDIA_MANUAL.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    for item_cache in CACHE_MIDIA_MANUAL.iterdir():
        if item_cache.is_file() and agora - item_cache.stat().st_mtime > CACHE_TTL_SEGUNDOS:
            item_cache.unlink(missing_ok=True)

    # Assinatura derivada do próprio arquivo (nunca do nome enviado pelo cliente),
    # o que impede path traversal e reaproveita o cache quando o arquivo não mudou.
    assinatura = hashlib.sha256(
        f"{drive_file_id}:{arquivo.get('modifiedTime')}:{tamanho}".encode("utf-8")
    ).hexdigest()[:24]
    extensao = Path(arquivo["name"]).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", extensao):
        extensao = ".mp4" if tipo_midia == "video" else ".jpg"
    destino = CACHE_MIDIA_MANUAL / f"{assinatura}{extensao}"

    if destino.exists() and destino.stat().st_size == tamanho:
        destino.touch()
        return destino, arquivo, tipo_midia

    temporario = CACHE_MIDIA_MANUAL / f"{assinatura}.{uuid.uuid4().hex}.part"
    try:
        request = service.files().get_media(fileId=drive_file_id)
        with temporario.open("wb") as arquivo_local:
            downloader = MediaIoBaseDownload(arquivo_local, request)
            concluido = False
            while not concluido:
                _, concluido = downloader.next_chunk()
        if temporario.stat().st_size != tamanho:
            raise MidiaAutorizacaoError(
                "O download do arquivo original ficou incompleto.", 502
            )
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)

    return destino, arquivo, tipo_midia
