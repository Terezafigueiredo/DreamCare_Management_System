"""CRUD do manifesto do Vídeo Institucional ROPE + navegação/preview no Google Drive.

Fase 1: esqueleto de dados (seleção editorial + identidade/narrativa).
Fase 2: navegação pelos sonhos/vídeos do Drive e preview dos vídeos originais.
Ainda sem FFmpeg, renderização, palavras, logo ou música.
"""

import os
import uuid
from pathlib import Path
from typing import Literal

import psycopg2
from psycopg2.extras import Json
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, model_validator

from api.video_institucional_drive import (
    DriveAutorizacaoError,
    listar_videos_do_sonho,
    obter_preview_em_cache,
)
from api.video_institucional_render import (
    ATAQUE_DUCKING_PADRAO_SEGUNDOS,
    CAMINHO_LOGO_ROPE,
    DURACAO_ENCERRAMENTO_MAXIMA_SEGUNDOS,
    DURACAO_ENCERRAMENTO_MINIMA_SEGUNDOS,
    DURACAO_ENCERRAMENTO_PADRAO_SEGUNDOS,
    DURACAO_TRANSICAO_MAXIMA_SEGUNDOS,
    DURACAO_TRANSICAO_PADRAO_SEGUNDOS,
    FADE_ENTRADA_ENCERRAMENTO_PADRAO_SEGUNDOS,
    FADE_IN_MUSICA_PADRAO_SEGUNDOS,
    FADE_OUT_MUSICA_PADRAO_SEGUNDOS,
    FADE_SAIDA_ENCERRAMENTO_PADRAO_SEGUNDOS,
    FORMATOS_AUDIO_SUPORTADOS,
    IMPACTOS_VALIDOS,
    NIVEL_DUCKING_PADRAO,
    PADRAO_ARQUIVO_MUSICA_SEGURO,
    PADRAO_TEXTO_SEGURO_PALAVRA,
    PASTA_AUDIO_INSTITUCIONAL,
    POSICOES_VALIDAS,
    RETORNO_DUCKING_PADRAO_SEGUNDOS,
    TAMANHO_MAXIMO_MUSICA_BYTES,
    VOLUME_BASE_MUSICA_PADRAO,
    calcular_duracao_total_com_encerramento,
    obter_info_logo_oficial,
    renderizar_producao_institucional,
    resolver_musica_institucional,
    validar_arquivo_audio_upload,
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


class PalavraNarrativa(BaseModel):
    """Uma palavra da narrativa textual (drawtext), com timeline própria —
    independente dos trechos de vídeo. Ver Fase 6."""

    texto: str
    inicio_segundos: float = Field(ge=0)
    fim_segundos: float
    impacto: Literal[IMPACTOS_VALIDOS] = "normal"
    posicao: Literal[POSICOES_VALIDAS] = "centro"
    ativa: bool = True

    @model_validator(mode="after")
    def _validar_palavra(self):
        if self.fim_segundos <= self.inicio_segundos:
            raise ValueError("fim_segundos deve ser maior que inicio_segundos.")
        if not self.texto.strip():
            raise ValueError("texto não pode ficar vazio.")
        if not PADRAO_TEXTO_SEGURO_PALAVRA.match(self.texto):
            raise ValueError(
                "texto contém caracteres não suportados — use apenas letras, "
                "números, espaços e pontuação básica (. , ! ? -)."
            )
        return self


class EncerramentoConfig(BaseModel):
    """Configuração do card de encerramento (logo oficial do ROPE). O
    caminho do arquivo NÃO é um campo aqui de propósito — é sempre resolvido
    e validado pelo backend (`CAMINHO_LOGO_ROPE`), nunca aceito do frontend.
    Ver Fase 7."""

    ativo: bool = True
    duracao_segundos: float = Field(
        default=DURACAO_ENCERRAMENTO_PADRAO_SEGUNDOS,
        ge=DURACAO_ENCERRAMENTO_MINIMA_SEGUNDOS,
        le=DURACAO_ENCERRAMENTO_MAXIMA_SEGUNDOS,
    )
    fade_entrada: float = Field(default=FADE_ENTRADA_ENCERRAMENTO_PADRAO_SEGUNDOS, gt=0)
    fade_saida: float = Field(default=FADE_SAIDA_ENCERRAMENTO_PADRAO_SEGUNDOS, gt=0)

    @model_validator(mode="after")
    def _validar_fades(self):
        if self.fade_entrada + self.fade_saida >= self.duracao_segundos:
            raise ValueError("fade_entrada + fade_saida deve ser menor que duracao_segundos.")
        return self


class DuckingConfig(BaseModel):
    """Configuração de quanto a música abaixa (e com que suavidade) durante
    um trecho com `manter_audio_original = true`. Ver Fase 8."""

    nivel_musica_durante_fala: float = Field(default=NIVEL_DUCKING_PADRAO, ge=0.0, le=1.0)
    ataque_segundos: float = Field(default=ATAQUE_DUCKING_PADRAO_SEGUNDOS, gt=0)
    retorno_segundos: float = Field(default=RETORNO_DUCKING_PADRAO_SEGUNDOS, gt=0)


class MusicaConfig(BaseModel):
    """Configuração da trilha sonora. O campo `arquivo` NÃO é um caminho —
    é uma referência gerada pelo backend no upload (uuid hex + extensão
    suportada, ver `PADRAO_ARQUIVO_MUSICA_SEGURO`) e é a ÚNICA forma de setar
    esse campo: o frontend nunca escolhe nem envia um caminho de arquivo
    livre (item 13 da Fase 8). `curva_emocional` é só o nome do preset usado
    (hoje só existe "padrao"); os pontos da curva em si são calculados no
    motor de renderização a partir da duração real da produção."""

    ativa: bool = False
    arquivo: str | None = Field(default=None, pattern=PADRAO_ARQUIVO_MUSICA_SEGURO.pattern)
    nome_original: str | None = None
    duracao_segundos: float | None = None
    volume_base: float = Field(default=VOLUME_BASE_MUSICA_PADRAO, ge=0.0, le=1.5)
    fade_in: float = Field(default=FADE_IN_MUSICA_PADRAO_SEGUNDOS, gt=0)
    fade_out: float = Field(default=FADE_OUT_MUSICA_PADRAO_SEGUNDOS, gt=0)
    curva_emocional: Literal["padrao"] = "padrao"
    ducking: DuckingConfig = Field(default_factory=DuckingConfig)

    @model_validator(mode="after")
    def _validar_musica(self):
        if self.ativa and not self.arquivo:
            raise ValueError("musica.ativa=true requer um arquivo configurado (envie um upload primeiro).")
        return self


class IdentidadeNarrativa(BaseModel):
    """Bloco de identidade/narrativa do manifesto: palavras (Fase 6),
    encerramento ROPE (Fase 7) e trilha sonora (Fase 8)."""

    palavras: list[PalavraNarrativa] = Field(default_factory=list)
    encerramento: EncerramentoConfig = Field(default_factory=EncerramentoConfig)
    musica: MusicaConfig = Field(default_factory=MusicaConfig)


class ProducaoInstitucionalCriar(BaseModel):
    titulo: str
    selecao_editorial: list[TrechoEditorial] = Field(default_factory=list)
    identidade_narrativa: IdentidadeNarrativa = Field(default_factory=IdentidadeNarrativa)


class ProducaoInstitucionalAtualizar(BaseModel):
    titulo: str | None = None
    selecao_editorial: list[TrechoEditorial] | None = None
    identidade_narrativa: IdentidadeNarrativa | None = None


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
                Json(entrada.identidade_narrativa.model_dump()),
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
# LOGO OFICIAL (somente leitura — Fase 7)
# =========================================================

@router.get("/logo-info")
def obter_logo_institucional():
    """Informa qual arquivo de logo o backend vai usar no encerramento, sem
    expor o caminho absoluto do disco. Não existe endpoint para trocar esse
    caminho — ele é sempre fixo e resolvido no backend."""
    try:
        return obter_info_logo_oficial()
    except RuntimeError as erro:
        raise HTTPException(status_code=500, detail=str(erro)) from erro


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
            valores.append(Json(entrada.identidade_narrativa.model_dump()))

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
# TRILHA SONORA (Fase 8)
# =========================================================

MIME_POR_EXTENSAO_AUDIO = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}


@router.post("/{producao_id}/musica")
async def enviar_musica(producao_id: int, arquivo: UploadFile = File(...)):
    """Upload restrito ao institucional: recebe o arquivo, valida (formato +
    é mesmo um áudio legível), guarda com um nome gerado pelo backend em
    `landing/media/institucional/audio/{producao_id}/` e só então atualiza o
    manifesto. O nome original do upload só é guardado para EXIBIÇÃO — nunca
    usado como caminho."""
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        registro = _buscar_ou_404(cursor, producao_id)

        extensao = Path(arquivo.filename or "").suffix.lower()
        if extensao not in FORMATOS_AUDIO_SUPORTADOS:
            raise HTTPException(
                status_code=400,
                detail="Formato de áudio não suportado. Use MP3, WAV ou M4A/AAC.",
            )

        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(status_code=400, detail="Arquivo de música vazio.")
        if len(conteudo) > TAMANHO_MAXIMO_MUSICA_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Arquivo excede o tamanho máximo permitido ({TAMANHO_MAXIMO_MUSICA_BYTES // (1024*1024)}MB).",
            )

        pasta_producao = PASTA_AUDIO_INSTITUCIONAL / str(producao_id)
        pasta_producao.mkdir(parents=True, exist_ok=True)
        nome_seguro = f"{uuid.uuid4().hex}{extensao}"
        destino = pasta_producao / nome_seguro
        destino.write_bytes(conteudo)

        try:
            metadados = validar_arquivo_audio_upload(destino)
        except RuntimeError as erro:
            destino.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(erro)) from erro

        # Remove o arquivo anterior desta produção, se houver, para não
        # acumular trilhas trocadas sem uso.
        musica_atual = (registro["identidade_narrativa"] or {}).get("musica") or {}
        arquivo_antigo = musica_atual.get("arquivo")
        if arquivo_antigo:
            (pasta_producao / arquivo_antigo).unlink(missing_ok=True)

        nova_musica = {
            "ativa": True,
            "arquivo": nome_seguro,
            "nome_original": Path(arquivo.filename or "trilha").name,
            "duracao_segundos": round(metadados["duracao"], 2),
            "volume_base": musica_atual.get("volume_base", VOLUME_BASE_MUSICA_PADRAO),
            "fade_in": musica_atual.get("fade_in", FADE_IN_MUSICA_PADRAO_SEGUNDOS),
            "fade_out": musica_atual.get("fade_out", FADE_OUT_MUSICA_PADRAO_SEGUNDOS),
            "curva_emocional": "padrao",
            "ducking": musica_atual.get("ducking") or {
                "nivel_musica_durante_fala": NIVEL_DUCKING_PADRAO,
                "ataque_segundos": ATAQUE_DUCKING_PADRAO_SEGUNDOS,
                "retorno_segundos": RETORNO_DUCKING_PADRAO_SEGUNDOS,
            },
        }
        nova_identidade = dict(registro["identidade_narrativa"] or {})
        nova_identidade["musica"] = nova_musica

        cursor.execute(
            """
            UPDATE producoes_institucionais
            SET identidade_narrativa = %s, data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, titulo, status, selecao_editorial, identidade_narrativa,
                      video_vertical_path, video_horizontal_path, erro_automacao,
                      data_criacao, data_atualizacao;
            """,
            (Json(nova_identidade), producao_id),
        )
        linha = cursor.fetchone()
        conexao.commit()
        return _linha_para_dict(cursor, linha)
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@router.delete("/{producao_id}/musica")
def remover_musica(producao_id: int):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        registro = _buscar_ou_404(cursor, producao_id)
        musica_atual = (registro["identidade_narrativa"] or {}).get("musica") or {}
        arquivo_antigo = musica_atual.get("arquivo")
        if arquivo_antigo:
            pasta_producao = PASTA_AUDIO_INSTITUCIONAL / str(producao_id)
            (pasta_producao / arquivo_antigo).unlink(missing_ok=True)

        nova_identidade = dict(registro["identidade_narrativa"] or {})
        nova_identidade["musica"] = {"ativa": False, "arquivo": None}

        cursor.execute(
            """
            UPDATE producoes_institucionais
            SET identidade_narrativa = %s, data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, titulo, status, selecao_editorial, identidade_narrativa,
                      video_vertical_path, video_horizontal_path, erro_automacao,
                      data_criacao, data_atualizacao;
            """,
            (Json(nova_identidade), producao_id),
        )
        linha = cursor.fetchone()
        conexao.commit()
        return _linha_para_dict(cursor, linha)
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@router.get("/{producao_id}/musica/preview")
def obter_preview_musica(producao_id: int):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        registro = _buscar_ou_404(cursor, producao_id)
    finally:
        cursor.close()
        conexao.close()

    musica = (registro["identidade_narrativa"] or {}).get("musica") or {}
    arquivo = musica.get("arquivo")
    if not arquivo:
        raise HTTPException(status_code=404, detail="Esta produção não tem trilha configurada.")

    try:
        caminho, _metadados = resolver_musica_institucional(producao_id, arquivo)
    except RuntimeError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    tipo_mime = MIME_POR_EXTENSAO_AUDIO.get(caminho.suffix.lower(), "application/octet-stream")
    return FileResponse(
        caminho, media_type=tipo_mime, headers={"Cache-Control": "private, max-age=3600"}
    )


# =========================================================
# RENDERIZAÇÃO
# =========================================================

def executar_renderizacao_institucional(producao_id, selecao_editorial, identidade_narrativa):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        resultado = renderizar_producao_institucional(
            producao_id, selecao_editorial, identidade_narrativa
        )
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
            RETURNING selecao_editorial, identidade_narrativa;
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

        tarefas.add_task(
            executar_renderizacao_institucional, producao_id, linha[0], linha[1]
        )
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
