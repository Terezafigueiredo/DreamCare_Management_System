"""CRUD do manifesto do Vídeo Institucional ROPE + navegação/preview no Google Drive.

Fase 1: esqueleto de dados (seleção editorial + identidade/narrativa).
Fase 2: navegação pelos sonhos/vídeos do Drive e preview dos vídeos originais.
Ainda sem FFmpeg, renderização, palavras, logo ou música.
"""

import os
from typing import Literal

import psycopg2
from psycopg2.extras import Json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, model_validator

from api.video_institucional_drive import (
    DriveAutorizacaoError,
    listar_videos_do_sonho,
    obter_preview_em_cache,
)
from api.video_institucional_render import (
    DURACAO_TRANSICAO_MAXIMA_SEGUNDOS,
    DURACAO_TRANSICAO_PADRAO_SEGUNDOS,
    renderizar_producao_institucional,
)


router = APIRouter(prefix="/institucional", tags=["video-institucional"])


SECOES_VALIDAS = (
    "DREAMS",
    "PURPOSE_EACH_PERSON",
    "SACRED_FAITH",
    "JOY_FULFILLMENT",
    "ROPE_ENCERRAMENTO",
)


# =========================================================
# BANCO
# =========================================================

def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT"),
    )


# =========================================================
# MODELOS
# =========================================================

class TrechoEditorial(BaseModel):
    """Um recorte de vídeo dentro da seleção editorial da produção."""

    sonho_id: int
    drive_folder_id: str
    drive_file_id: str
    nome_arquivo: str | None = None
    inicio_segundos: float = Field(ge=0)
    fim_segundos: float
    ordem: int
    secao: Literal[SECOES_VALIDAS]
    manter_audio_original: bool = False
    encaixe: Literal["cobrir", "conter"] = "cobrir"
    # Compatibilidade com produções antigas: um trecho salvo antes da Fase 5
    # não tem estes dois campos no JSONB. Como não há "reload" explícito desses
    # dados pelo Pydantic (GET devolve o JSONB cru), os padrões abaixo só
    # entram em vigor quando o trecho passa de novo por este modelo (ex.: um
    # PATCH que reenvia a seleção editorial inteira). O motor de renderização
    # e a interface aplicam o mesmo padrão de compatibilidade por conta própria
    # ao ler diretamente do JSONB (ver video_institucional_render.py e
    # institucional.js).
    transicao_entrada: Literal["corte", "dissolve"] = "corte"
    duracao_transicao: float = Field(
        default=DURACAO_TRANSICAO_PADRAO_SEGUNDOS,
        gt=0,
        le=DURACAO_TRANSICAO_MAXIMA_SEGUNDOS,
    )

    @model_validator(mode="after")
    def _validar_intervalo(self):
        if self.fim_segundos <= self.inicio_segundos:
            raise ValueError("fim_segundos deve ser maior que inicio_segundos.")
        return self


class ProducaoInstitucionalCriar(BaseModel):
    titulo: str
    selecao_editorial: list[TrechoEditorial] = Field(default_factory=list)
    identidade_narrativa: dict = Field(default_factory=dict)


class ProducaoInstitucionalAtualizar(BaseModel):
    titulo: str | None = None
    selecao_editorial: list[TrechoEditorial] | None = None
    identidade_narrativa: dict | None = None


# =========================================================
# CRIAR
# =========================================================

@router.post("")
def criar_producao_institucional(entrada: ProducaoInstitucionalCriar):
    if not entrada.titulo.strip():
        raise HTTPException(status_code=400, detail="Informe um título para a produção.")

    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO producoes_institucionais (
                titulo, selecao_editorial, identidade_narrativa
            )
            VALUES (%s, %s, %s)
            RETURNING id, titulo, status, selecao_editorial, identidade_narrativa,
                      video_vertical_path, video_horizontal_path, erro_automacao,
                      data_criacao, data_atualizacao;
            """,
            (
                entrada.titulo.strip(),
                Json([trecho.model_dump() for trecho in entrada.selecao_editorial]),
                Json(entrada.identidade_narrativa),
            ),
        )
        linha = cursor.fetchone()
        conexao.commit()
        return _linha_para_dict(cursor, linha)
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# LISTAR
# =========================================================

@router.get("")
def listar_producoes_institucionais():
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, titulo, status, selecao_editorial, identidade_narrativa,
                   video_vertical_path, video_horizontal_path, erro_automacao,
                   data_criacao, data_atualizacao
            FROM producoes_institucionais
            ORDER BY data_criacao DESC;
            """
        )
        linhas = cursor.fetchall()
        resultados = []
        for linha in linhas:
            item = _linha_para_dict(cursor, linha)
            item["quantidade_trechos"] = len(item.pop("selecao_editorial"))
            item.pop("identidade_narrativa", None)
            resultados.append(item)
        return {"total": len(resultados), "resultados": resultados}
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# SONHOS DISPONÍVEIS (reaproveita a tabela `sonhos` já existente)
# =========================================================
#
# Importante: estas rotas de caminho fixo ("/sonhos", "/sonhos/{sonho_id}/videos")
# precisam ser registradas ANTES de "/{producao_id}" abaixo — senão o FastAPI
# tentaria casar "/institucional/sonhos" com a rota genérica de detalhe e falharia
# ao converter "sonhos" para inteiro.

@router.get("/sonhos")
def listar_sonhos_disponiveis():
    """Sonhos que podem ser usados no vídeo institucional (precisam ter pasta no Drive)."""
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, nome, idade, sonho, drive_folder_id, drive_folder_name
            FROM sonhos
            WHERE drive_folder_id IS NOT NULL
            ORDER BY nome ASC;
            """
        )
        linhas = cursor.fetchall()
        colunas = [descricao[0] for descricao in cursor.description]
        resultados = [dict(zip(colunas, linha)) for linha in linhas]
        return {"total": len(resultados), "resultados": resultados}
    finally:
        cursor.close()
        conexao.close()


def _buscar_pasta_do_sonho(sonho_id):
    """Busca no banco o drive_folder_id verdadeiro do sonho (nunca aceito do cliente)."""
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "SELECT nome, drive_folder_id FROM sonhos WHERE id = %s;", (sonho_id,)
        )
        linha = cursor.fetchone()
        if not linha:
            raise HTTPException(status_code=404, detail="Sonho não encontrado.")
        nome, drive_folder_id = linha
        if not drive_folder_id:
            raise HTTPException(
                status_code=400,
                detail="Este sonho não possui pasta vinculada no Drive.",
            )
        return drive_folder_id, nome
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# VÍDEOS DE UM SONHO (percorre a pasta e subpastas no Drive)
# =========================================================

@router.get("/sonhos/{sonho_id}/videos")
def listar_videos_do_sonho_institucional(sonho_id: int):
    drive_folder_id, nome_sonho = _buscar_pasta_do_sonho(sonho_id)
    try:
        nome_pasta, videos = listar_videos_do_sonho(drive_folder_id)
    except DriveAutorizacaoError as erro:
        raise HTTPException(status_code=erro.status_code, detail=str(erro)) from erro
    except HttpError as erro:
        raise HTTPException(
            status_code=502, detail="Falha ao acessar o Google Drive."
        ) from erro
    except Exception as erro:
        raise HTTPException(
            status_code=502, detail=f"Não foi possível autenticar no Google Drive: {erro}"
        ) from erro

    return {
        "sonho_id": sonho_id,
        "nome_sonho": nome_sonho,
        "drive_folder_id": drive_folder_id,
        "drive_folder_nome": nome_pasta,
        "total": len(videos),
        "videos": videos,
    }


# =========================================================
# DETALHE
# =========================================================

@router.get("/{producao_id}")
def obter_producao_institucional(producao_id: int):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        registro = _buscar_ou_404(cursor, producao_id)
        return registro
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# ATUALIZAR
# =========================================================

@router.patch("/{producao_id}")
def atualizar_producao_institucional(
    producao_id: int, entrada: ProducaoInstitucionalAtualizar
):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        _buscar_ou_404(cursor, producao_id)

        campos = []
        valores = []

        if entrada.titulo is not None:
            if not entrada.titulo.strip():
                raise HTTPException(status_code=400, detail="O título não pode ficar vazio.")
            campos.append("titulo = %s")
            valores.append(entrada.titulo.strip())

        if entrada.selecao_editorial is not None:
            campos.append("selecao_editorial = %s")
            valores.append(Json([trecho.model_dump() for trecho in entrada.selecao_editorial]))

        if entrada.identidade_narrativa is not None:
            campos.append("identidade_narrativa = %s")
            valores.append(Json(entrada.identidade_narrativa))

        if not campos:
            raise HTTPException(status_code=400, detail="Nenhuma alteração enviada.")

        campos.append("data_atualizacao = CURRENT_TIMESTAMP")
        valores.append(producao_id)

        cursor.execute(
            f"""
            UPDATE producoes_institucionais
            SET {", ".join(campos)}
            WHERE id = %s
            RETURNING id, titulo, status, selecao_editorial, identidade_narrativa,
                      video_vertical_path, video_horizontal_path, erro_automacao,
                      data_criacao, data_atualizacao;
            """,
            valores,
        )
        linha = cursor.fetchone()
        conexao.commit()
        return _linha_para_dict(cursor, linha)
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# REMOVER
# =========================================================

@router.delete("/{producao_id}")
def remover_producao_institucional(producao_id: int):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        _buscar_ou_404(cursor, producao_id)
        cursor.execute(
            "DELETE FROM producoes_institucionais WHERE id = %s;", (producao_id,)
        )
        conexao.commit()
        return {"mensagem": "Produção institucional removida.", "producao_id": producao_id}
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# RENDERIZAÇÃO (Fase 4: somente vertical, corte seco)
# =========================================================

def executar_renderizacao_institucional(producao_id, selecao_editorial):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        resultado = renderizar_producao_institucional(producao_id, selecao_editorial)
        cursor.execute(
            """
            UPDATE producoes_institucionais
            SET status = 'PRONTO',
                video_vertical_path = %s,
                video_horizontal_path = %s,
                erro_automacao = NULL,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s;
            """,
            (str(resultado.caminho_vertical), str(resultado.caminho_horizontal), producao_id),
        )
        conexao.commit()
    except Exception as erro:
        conexao.rollback()
        cursor.execute(
            """
            UPDATE producoes_institucionais
            SET status = 'ERRO',
                erro_automacao = %s,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s;
            """,
            (str(erro)[:3000], producao_id),
        )
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()


@router.post("/{producao_id}/renderizar")
def solicitar_renderizacao_institucional(producao_id: int, tarefas: BackgroundTasks):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        registro = _buscar_ou_404(cursor, producao_id)
        if not registro["selecao_editorial"]:
            raise HTTPException(
                status_code=400,
                detail="A seleção editorial está vazia. Adicione trechos antes de renderizar.",
            )

        # Atualização condicional: só entra em PROCESSANDO se não estiver lá já.
        # Isso é a trava de concorrência desta fase (sem fila complexa).
        cursor.execute(
            """
            UPDATE producoes_institucionais
            SET status = 'PROCESSANDO',
                erro_automacao = NULL,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s AND status != 'PROCESSANDO'
            RETURNING selecao_editorial;
            """,
            (producao_id,),
        )
        linha = cursor.fetchone()
        if not linha:
            raise HTTPException(
                status_code=409,
                detail="Esta produção já está sendo renderizada no momento.",
            )
        conexao.commit()

        tarefas.add_task(executar_renderizacao_institucional, producao_id, linha[0])
        return {
            "mensagem": "Renderização iniciada.",
            "producao_id": producao_id,
            "status": "PROCESSANDO",
        }
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# PREVIEW DO VÍDEO ORIGINAL (somente leitura, com cache local)
# =========================================================

@router.get("/{producao_id}/sonhos/{sonho_id}/video-original/{drive_file_id}")
def obter_preview_video_original(producao_id: int, sonho_id: int, drive_file_id: str):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        _buscar_ou_404(cursor, producao_id)
    finally:
        cursor.close()
        conexao.close()

    drive_folder_id, _ = _buscar_pasta_do_sonho(sonho_id)

    try:
        caminho_cache, arquivo = obter_preview_em_cache(drive_folder_id, drive_file_id)
    except DriveAutorizacaoError as erro:
        raise HTTPException(status_code=erro.status_code, detail=str(erro)) from erro
    except HttpError as erro:
        raise HTTPException(
            status_code=502, detail="Falha ao acessar o Google Drive."
        ) from erro
    except Exception as erro:
        raise HTTPException(
            status_code=502, detail=f"Não foi possível autenticar no Google Drive: {erro}"
        ) from erro

    return FileResponse(
        caminho_cache,
        media_type=arquivo.get("mimeType") or "video/mp4",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# =========================================================
# AUXILIARES
# =========================================================

def _linha_para_dict(cursor, linha):
    colunas = [descricao[0] for descricao in cursor.description]
    item = dict(zip(colunas, linha))
    for chave, valor in item.items():
        if hasattr(valor, "isoformat"):
            item[chave] = valor.isoformat()
    return item


def _buscar_ou_404(cursor, producao_id):
    cursor.execute(
        """
        SELECT id, titulo, status, selecao_editorial, identidade_narrativa,
               video_vertical_path, video_horizontal_path, erro_automacao,
               data_criacao, data_atualizacao
        FROM producoes_institucionais
        WHERE id = %s;
        """,
        (producao_id,),
    )
    linha = cursor.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Produção institucional não encontrada.")
    return _linha_para_dict(cursor, linha)
