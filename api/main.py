from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import json
import psycopg2
import os

from api.automacao_social import (
    obter_video_original_em_cache,
    preparar_reel,
    publicar_reel,
    renderizar_reel_revisado,
)
from api.video_institucional import router as router_video_institucional


# =========================================================
# CONFIGURAÇÃO
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(
    BASE_DIR / ".env"
)

app = FastAPI(
    title="DreamCare API"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PASTA_MEDIA = BASE_DIR / "landing" / "media"
PASTA_MEDIA.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=PASTA_MEDIA), name="media")

app.include_router(router_video_institucional)


# =========================================================
# MODELOS
# =========================================================

class ProducaoEntrada(BaseModel):
    sonho_id: int
    tipo_conteudo: str = "NAO_DEFINIDO"
    observacoes: str | None = None
class ProducaoAtualizacao(BaseModel):
    status: str | None = None
    tipo_conteudo: str | None = None
    observacoes: str | None = None


class PrepararVideoEntrada(BaseModel):
    legenda: str = ""
    duracao_maxima: int = 60


class TrechoRevisadoEntrada(BaseModel):
    drive_file_id: str
    inicio_segundos: float
    fim_segundos: float


class RenderizarRevisaoEntrada(BaseModel):
    trechos: list[TrechoRevisadoEntrada]
    duracao_maxima: int = 60


class PublicarInstagramEntrada(BaseModel):
    confirmar_publicacao: bool = False
    video_publico_url: str | None = None

# =========================================================
# BANCO
# =========================================================

def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return {
        "mensagem": "API DreamCare funcionando"
    }


# =========================================================
# LISTAR TODOS OS SONHOS
# =========================================================

@app.get("/sonhos")
def listar_sonhos():

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            SELECT *
            FROM sonhos
            ORDER BY id ASC
        """)

        dados = cursor.fetchall()

        colunas = [
            desc[0]
            for desc in cursor.description
        ]

        sonhos = []

        for linha in dados:

            sonho = dict(
                zip(
                    colunas,
                    linha
                )
            )

            for chave, valor in sonho.items():

                if hasattr(
                    valor,
                    "isoformat"
                ):

                    sonho[chave] = (
                        valor.isoformat()
                    )

            sonhos.append(
                sonho
            )

        return {
            "total": len(sonhos),
            "sonhos": sonhos
        }

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# CENTRAL DE CONTEÚDO
# =========================================================

@app.get("/central-conteudo")
def central_conteudo(
    idade_minima: int | None = None,
    idade_maxima: int | None = None,
    faixa_etaria: str | None = None,
    tem_fotos: bool | None = None,
    tem_videos: bool | None = None,
    busca: str | None = None
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        query = """
            SELECT
                s.id,
                s.nome,
                s.idade,
                s.sonho,
                s.data_realizacao,
                s.enfermidade,
                s.idealizador,
                s.drive_folder_id,
                s.drive_folder_name,

                c.faixa_etaria,
                c.quantidade_fotos,
                c.quantidade_videos,
                c.quantidade_subpastas,
                c.quantidade_outros,
                c.status_post,

                p.id AS producao_id,
                p.status AS producao_status,
                p.tipo_conteudo

            FROM sonhos s

            INNER JOIN conteudo_sonhos c
                ON c.sonho_id = s.id

            LEFT JOIN producao_conteudo p
                ON p.sonho_id = s.id

            WHERE s.drive_folder_id IS NOT NULL

            AND (
                p.status IS NULL
                OR p.status <> 'PUBLICADO'
            )
        """

        parametros = []

        # =========================================
        # IDADE MÍNIMA
        # =========================================

        if idade_minima is not None:

            query += """
                AND s.idade >= %s
            """

            parametros.append(
                idade_minima
            )

        # =========================================
        # IDADE MÁXIMA
        # =========================================

        if idade_maxima is not None:

            query += """
                AND s.idade <= %s
            """

            parametros.append(
                idade_maxima
            )

        # =========================================
        # FAIXA ETÁRIA
        # =========================================

        if faixa_etaria:

            query += """
                AND c.faixa_etaria = %s
            """

            parametros.append(
                faixa_etaria.upper()
            )

        # =========================================
        # FOTOS
        # =========================================

        if tem_fotos is True:

            query += """
                AND c.quantidade_fotos > 0
            """

        elif tem_fotos is False:

            query += """
                AND c.quantidade_fotos = 0
            """

        # =========================================
        # VÍDEOS
        # =========================================

        if tem_videos is True:

            query += """
                AND c.quantidade_videos > 0
            """

        elif tem_videos is False:

            query += """
                AND c.quantidade_videos = 0
            """

        # =========================================
        # PESQUISA
        # =========================================

        if busca:

            query += """
                AND (
                    LOWER(s.nome) LIKE LOWER(%s)

                    OR LOWER(s.sonho) LIKE LOWER(%s)

                    OR LOWER(
                        COALESCE(
                            s.enfermidade,
                            ''
                        )
                    ) LIKE LOWER(%s)

                    OR LOWER(
                        COALESCE(
                            s.idealizador,
                            ''
                        )
                    ) LIKE LOWER(%s)
                )
            """

            termo = f"%{busca}%"

            parametros.extend([
                termo,
                termo,
                termo,
                termo
            ])

        # =========================================
        # ORDENAÇÃO
        # =========================================

        query += """
            ORDER BY
                CASE
                    WHEN p.status IS NULL THEN 0
                    ELSE 1
                END,
                s.idade ASC NULLS LAST,
                s.nome ASC
        """

        cursor.execute(
            query,
            parametros
        )

        dados = cursor.fetchall()

        colunas = [
            desc[0]
            for desc in cursor.description
        ]

        resultados = []

        for linha in dados:

            item = dict(
                zip(
                    colunas,
                    linha
                )
            )

            for chave, valor in item.items():

                if hasattr(
                    valor,
                    "isoformat"
                ):

                    item[chave] = (
                        valor.isoformat()
                    )

            if item["drive_folder_id"]:

                item["drive_url"] = (
                    "https://drive.google.com/"
                    "drive/folders/"
                    + item["drive_folder_id"]
                )

            else:

                item["drive_url"] = None

            item["ja_na_semana"] = (
                item["producao_status"]
                is not None
            )

            resultados.append(
                item
            )

        return {
            "total": len(resultados),
            "resultados": resultados
        }

    finally:

        cursor.close()
        conexao.close()
# =========================================================
# ADICIONAR À PRODUÇÃO
# =========================================================

@app.post("/producao")
def adicionar_producao(
    entrada: ProducaoEntrada
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        # -----------------------------------------
        # CONFIRMAR QUE O SONHO EXISTE
        # -----------------------------------------

        cursor.execute("""
            SELECT id, nome
            FROM sonhos
            WHERE id = %s
        """, (
            entrada.sonho_id,
        ))

        sonho = cursor.fetchone()

        if not sonho:

            raise HTTPException(
                status_code=404,
                detail="Sonho não encontrado."
            )

        # -----------------------------------------
        # VERIFICAR SE JÁ ESTÁ NA PRODUÇÃO
        # -----------------------------------------

        cursor.execute("""
            SELECT id, status
            FROM producao_conteudo
            WHERE sonho_id = %s
        """, (
            entrada.sonho_id,
        ))

        existente = cursor.fetchone()

        if existente:

            raise HTTPException(
                status_code=409,
                detail="Este sonho já está na fila de produção."
            )

        # -----------------------------------------
        # INSERIR
        # -----------------------------------------

        cursor.execute("""
            INSERT INTO producao_conteudo (
                sonho_id,
                tipo_conteudo,
                status,
                observacoes
            )
            VALUES (
                %s,
                %s,
                'A_FAZER',
                %s
            )
            RETURNING id;
        """, (
            entrada.sonho_id,
            entrada.tipo_conteudo.upper(),
            entrada.observacoes
        ))

        producao_id = cursor.fetchone()[0]

        conexao.commit()

        return {
            "mensagem": "Sonho adicionado à produção.",
            "producao_id": producao_id,
            "sonho_id": entrada.sonho_id,
            "nome": sonho[1],
            "status": "A_FAZER"
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# LISTAR PRODUÇÃO
# =========================================================

@app.get("/producao")
def listar_producao(
    status: str | None = None
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        query = """
            SELECT
                p.id AS producao_id,
                p.sonho_id,
                s.nome,
                s.idade,
                s.sonho,
                s.drive_folder_id,
                s.drive_folder_name,

                c.quantidade_fotos,
                c.quantidade_videos,
                c.faixa_etaria,

                p.tipo_conteudo,
                p.status,
                p.observacoes,
                p.data_criacao,
                p.data_atualizacao,
                p.data_publicacao,
                p.edicao_status,
                p.video_editado_path,
                p.video_publico_url,
                p.legenda_instagram,
                p.erro_automacao,
                p.instagram_media_id

            FROM producao_conteudo p

            INNER JOIN sonhos s
                ON s.id = p.sonho_id

            LEFT JOIN conteudo_sonhos c
                ON c.sonho_id = s.id

            WHERE 1 = 1
        """

        parametros = []

        if status:

            query += """
                AND p.status = %s
            """

            parametros.append(
                status.upper()
            )

        query += """
            ORDER BY
                p.data_criacao DESC
        """

        cursor.execute(
            query,
            parametros
        )

        dados = cursor.fetchall()

        colunas = [
            desc[0]
            for desc in cursor.description
        ]

        resultados = []

        for linha in dados:

            item = dict(
                zip(
                    colunas,
                    linha
                )
            )

            for chave, valor in item.items():

                if hasattr(
                    valor,
                    "isoformat"
                ):

                    item[chave] = (
                        valor.isoformat()
                    )

            if item["drive_folder_id"]:

                item["drive_url"] = (
                    "https://drive.google.com/"
                    "drive/folders/"
                    + item["drive_folder_id"]
                )

            else:

                item["drive_url"] = None

            if item.get("video_editado_path"):
                caminho_video = Path(item["video_editado_path"])
                item["video_preview_url"] = (
                    "/media/editados/"
                    + caminho_video.name
                )
                caminho_relatorio = caminho_video.with_suffix(".json")
                item["relatorio_edicao_url"] = (
                    "/media/editados/" + caminho_relatorio.name
                    if caminho_relatorio.exists()
                    else None
                )
                if caminho_relatorio.exists():
                    try:
                        relatorio = json.loads(
                            caminho_relatorio.read_text(encoding="utf-8")
                        )
                        item["resumo_edicao"] = {
                            "duracao_segundos": relatorio.get("duracao_segundos"),
                            "videos_utilizados": relatorio.get("videos_utilizados"),
                            "trechos_utilizados": relatorio.get("trechos_utilizados"),
                        }
                    except (OSError, ValueError):
                        item["resumo_edicao"] = None
            else:
                item["video_preview_url"] = None
                item["relatorio_edicao_url"] = None
                item["resumo_edicao"] = None

            resultados.append(
                item
            )

        return {
            "total": len(resultados),
            "resultados": resultados
        }

    finally:

        cursor.close()
        conexao.close()
@app.patch("/producao/{producao_id}")
def atualizar_producao(
    producao_id: int,
    entrada: ProducaoAtualizacao
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            SELECT id
            FROM producao_conteudo
            WHERE id = %s
        """, (
            producao_id,
        ))

        existe = cursor.fetchone()

        if not existe:
            raise HTTPException(
                status_code=404,
                detail="Produção não encontrada."
            )

        campos = []
        valores = []

        if entrada.status is not None:

            status_permitidos = {
                "A_FAZER",
                "EM_PRODUCAO",
                "PRONTO_PARA_POSTAR",
                "PUBLICADO"
            }

            status = entrada.status.upper()

            if status not in status_permitidos:
                raise HTTPException(
                    status_code=400,
                    detail="Status inválido."
                )

            campos.append(
                "status = %s"
            )

            valores.append(
                status
            )

            if status == "PUBLICADO":

                campos.append(
        "data_publicacao = CURRENT_DATE"
    )

            else:

                campos.append(
        "data_publicacao = NULL"
    )

        if entrada.tipo_conteudo is not None:

            tipos_permitidos = {
                "NAO_DEFINIDO",
                "REEL",
                "CARROSSEL",
                "STORY",
                "POST"
            }

            tipo = entrada.tipo_conteudo.upper()

            if tipo not in tipos_permitidos:

                raise HTTPException(
                    status_code=400,
                    detail="Tipo de conteúdo inválido."
                )

            campos.append(
                "tipo_conteudo = %s"
            )

            valores.append(
                tipo
            )

        if entrada.observacoes is not None:

            campos.append(
                "observacoes = %s"
            )

            valores.append(
                entrada.observacoes
            )

        if not campos:

            raise HTTPException(
                status_code=400,
                detail="Nenhuma alteração enviada."
            )

        campos.append(
            "data_atualizacao = CURRENT_TIMESTAMP"
        )

        query = f"""
            UPDATE producao_conteudo
            SET {", ".join(campos)}
            WHERE id = %s
        """

        valores.append(
            producao_id
        )

        cursor.execute(
            query,
            valores
        )

        conexao.commit()

        return {
            "mensagem": "Produção atualizada com sucesso.",
            "producao_id": producao_id
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()
def executar_edicao_video(producao_id, drive_folder_id, duracao_maxima):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        resultado = preparar_reel(drive_folder_id, producao_id, duracao_maxima)
        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'AGUARDANDO_APROVACAO',
                video_editado_path = %s,
                video_publico_url = %s,
                erro_automacao = NULL,
                status = 'PRONTO_PARA_POSTAR',
                tipo_conteudo = 'REEL',
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (str(resultado.caminho), None, producao_id))
        conexao.commit()
    except Exception as erro:
        conexao.rollback()
        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'ERRO',
                erro_automacao = %s,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (str(erro)[:3000], producao_id))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()


def executar_revisao_video(
    producao_id, drive_folder_id, relatorio_atual, trechos, duracao_maxima
):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        resultado = renderizar_reel_revisado(
            drive_folder_id,
            producao_id,
            relatorio_atual,
            trechos,
            duracao_maxima,
        )
        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'AGUARDANDO_APROVACAO',
                video_editado_path = %s,
                video_publico_url = NULL,
                erro_automacao = NULL,
                status = 'PRONTO_PARA_POSTAR',
                tipo_conteudo = 'REEL',
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (str(resultado.caminho), producao_id))
        conexao.commit()
    except Exception as erro:
        conexao.rollback()
        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'ERRO',
                erro_automacao = %s,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (str(erro)[:3000], producao_id))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()


def _carregar_relatorio_edicao(caminho_video):
    caminho = Path(caminho_video).resolve()
    pasta_permitida = (PASTA_MEDIA / "editados").resolve()
    if caminho.parent != pasta_permitida:
        raise HTTPException(status_code=400, detail="Caminho de edição inválido.")
    relatorio = caminho.with_suffix(".json")
    if not relatorio.exists():
        raise HTTPException(status_code=404, detail="Relatório da edição não encontrado.")
    try:
        return relatorio, json.loads(relatorio.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise HTTPException(status_code=500, detail="Relatório da edição inválido.") from erro


@app.post("/producao/{producao_id}/preparar-video")
def solicitar_edicao_video(
    producao_id: int,
    entrada: PrepararVideoEntrada,
    tarefas: BackgroundTasks,
):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT s.drive_folder_id
            FROM producao_conteudo p
            INNER JOIN sonhos s ON s.id = p.sonho_id
            WHERE p.id = %s
        """, (producao_id,))
        registro = cursor.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Produção não encontrada.")
        if not registro[0]:
            raise HTTPException(status_code=400, detail="Esta produção não possui pasta no Drive.")

        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'PROCESSANDO',
                legenda_instagram = %s,
                erro_automacao = NULL,
                status = 'EM_PRODUCAO',
                tipo_conteudo = 'REEL',
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (entrada.legenda.strip(), producao_id))
        conexao.commit()
        tarefas.add_task(
            executar_edicao_video,
            producao_id,
            registro[0],
            entrada.duracao_maxima,
        )
        return {"mensagem": "Edição iniciada.", "producao_id": producao_id}
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.get("/producao/{producao_id}/revisar-trechos")
def obter_revisao_trechos(producao_id: int):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT p.video_editado_path, p.edicao_status, s.drive_folder_id
            FROM producao_conteudo p
            INNER JOIN sonhos s ON s.id = p.sonho_id
            WHERE p.id = %s
        """, (producao_id,))
        registro = cursor.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Produção não encontrada.")
        caminho_video, edicao_status, drive_folder_id = registro
        if edicao_status != "AGUARDANDO_APROVACAO" or not caminho_video:
            raise HTTPException(status_code=409, detail="Não há uma prévia pronta para revisão.")
        _, relatorio = _carregar_relatorio_edicao(caminho_video)
        if relatorio.get("drive_folder_id") != drive_folder_id:
            raise HTTPException(status_code=409, detail="A prévia não corresponde à pasta atual.")
        deslocamento = 0.0
        trechos = []
        for trecho in relatorio.get("trechos", []):
            item = dict(trecho)
            item["inicio_na_previa"] = round(deslocamento, 3)
            deslocamento += float(trecho.get("duracao_segundos") or 0)
            trechos.append(item)
        return {
            "producao_id": producao_id,
            "video_preview_url": "/media/editados/" + Path(caminho_video).name,
            "trechos": trechos,
        }
    finally:
        cursor.close()
        conexao.close()


@app.get("/producao/{producao_id}/video-original/{drive_file_id}")
def obter_video_original(producao_id: int, drive_file_id: str):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT p.video_editado_path, p.edicao_status, s.drive_folder_id
            FROM producao_conteudo p
            INNER JOIN sonhos s ON s.id = p.sonho_id
            WHERE p.id = %s
        """, (producao_id,))
        registro = cursor.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Produção não encontrada.")
        caminho_video, edicao_status, drive_folder_id = registro
        if edicao_status != "AGUARDANDO_APROVACAO" or not caminho_video:
            raise HTTPException(status_code=409, detail="Esta produção não está disponível para revisão.")
        _, relatorio = _carregar_relatorio_edicao(caminho_video)
        autorizado = next(
            (
                trecho for trecho in relatorio.get("trechos", [])
                if trecho.get("drive_file_id") == drive_file_id
                and trecho.get("pasta_origem_id") == drive_folder_id
            ),
            None,
        )
        if not autorizado or relatorio.get("drive_folder_id") != drive_folder_id:
            raise HTTPException(status_code=403, detail="Vídeo não autorizado para esta revisão.")
        try:
            caminho_cache, arquivo = obter_video_original_em_cache(
                drive_folder_id, drive_file_id
            )
        except RuntimeError as erro:
            raise HTTPException(status_code=400, detail=str(erro)) from erro
        return FileResponse(
            caminho_cache,
            media_type=arquivo.get("mimeType") or "video/mp4",
            headers={
                "Cache-Control": "private, max-age=3600",
            },
        )
    finally:
        cursor.close()
        conexao.close()


@app.post("/producao/{producao_id}/renderizar-revisao")
def solicitar_renderizacao_revisada(
    producao_id: int,
    entrada: RenderizarRevisaoEntrada,
    tarefas: BackgroundTasks,
):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT p.video_editado_path, p.edicao_status, s.drive_folder_id
            FROM producao_conteudo p
            INNER JOIN sonhos s ON s.id = p.sonho_id
            WHERE p.id = %s
            FOR UPDATE
        """, (producao_id,))
        registro = cursor.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Produção não encontrada.")
        caminho_video, edicao_status, drive_folder_id = registro
        if edicao_status != "AGUARDANDO_APROVACAO" or not caminho_video:
            raise HTTPException(status_code=409, detail="A prévia não está disponível para revisão.")
        caminho_relatorio, _ = _carregar_relatorio_edicao(caminho_video)
        trechos = [item.dict() for item in entrada.trechos]
        cursor.execute("""
            UPDATE producao_conteudo
            SET edicao_status = 'PROCESSANDO',
                erro_automacao = NULL,
                status = 'EM_PRODUCAO',
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (producao_id,))
        conexao.commit()
        tarefas.add_task(
            executar_revisao_video,
            producao_id,
            drive_folder_id,
            str(caminho_relatorio),
            trechos,
            entrada.duracao_maxima,
        )
        return {"mensagem": "Nova versão em processamento.", "producao_id": producao_id}
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.post("/producao/{producao_id}/publicar-instagram")
def autorizar_publicacao_instagram(
    producao_id: int,
    entrada: PublicarInstagramEntrada,
):
    if not entrada.confirmar_publicacao:
        raise HTTPException(
            status_code=400,
            detail="A publicação exige autorização explícita.",
        )

    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT edicao_status, video_publico_url, legenda_instagram, status
            FROM producao_conteudo
            WHERE id = %s
            FOR UPDATE
        """, (producao_id,))
        registro = cursor.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Produção não encontrada.")
        edicao_status, url_salva, legenda, status = registro
        if edicao_status != "AGUARDANDO_APROVACAO" or status != "PRONTO_PARA_POSTAR":
            raise HTTPException(status_code=409, detail="O vídeo ainda não está pronto para publicar.")

        video_url = entrada.video_publico_url or url_salva
        if not video_url or not video_url.startswith("https://"):
            raise HTTPException(
                status_code=400,
                detail="Informe uma URL pública HTTPS do vídeo ou configure PUBLIC_MEDIA_BASE_URL.",
            )

        media_id = publicar_reel(video_url, legenda or "")
        cursor.execute("""
            UPDATE producao_conteudo
            SET status = 'PUBLICADO',
                instagram_media_id = %s,
                video_publico_url = %s,
                data_autorizacao = CURRENT_TIMESTAMP,
                data_publicacao = CURRENT_DATE,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (media_id, video_url, producao_id))
        conexao.commit()
        return {
            "mensagem": "Reel publicado no Instagram.",
            "instagram_media_id": media_id,
        }
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=502, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.get("/sugestoes-semana")
def sugestoes_semana(
    limite: int = 3,
    idade_maxima: int | None = None,
    faixa_etaria: str | None = None
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        query = """
            SELECT
                s.id,
                s.nome,
                s.idade,
                s.sonho,
                s.data_realizacao,
                s.enfermidade,
                s.idealizador,
                s.drive_folder_id,
                s.drive_folder_name,

                c.faixa_etaria,
                c.quantidade_fotos,
                c.quantidade_videos,
                c.quantidade_subpastas,

                (
                    -- Fotos ajudam, mas com limite
                    LEAST(c.quantidade_fotos, 50)

                    +

                    -- Vídeos têm mais peso, também com limite
                    LEAST(c.quantidade_videos * 5, 100)

                    +

                    -- Bônus por ter pelo menos 5 fotos
                    CASE
                        WHEN c.quantidade_fotos >= 5
                        THEN 20
                        ELSE 0
                    END

                    +

                    -- Bônus por ter pelo menos 2 vídeos
                    CASE
                        WHEN c.quantidade_videos >= 2
                        THEN 30
                        ELSE 0
                    END

                    +

                    -- Bônus para sonhos mais recentes
                    CASE
                        WHEN s.data_realizacao >= CURRENT_DATE - INTERVAL '2 years'
                        THEN 40

                        WHEN s.data_realizacao >= CURRENT_DATE - INTERVAL '5 years'
                        THEN 20

                        ELSE 0
                    END

                ) AS score_editorial

            FROM sonhos s

            INNER JOIN conteudo_sonhos c
                ON c.sonho_id = s.id

            LEFT JOIN producao_conteudo p
                ON p.sonho_id = s.id

            WHERE s.drive_folder_id IS NOT NULL

              AND c.quantidade_fotos >= 3
              AND c.quantidade_videos >= 1

              AND p.id IS NULL
        """

        parametros = []

        if idade_maxima is not None:
            query += """
                AND s.idade <= %s
            """

            parametros.append(
                idade_maxima
            )

        if faixa_etaria:
            query += """
                AND c.faixa_etaria = %s
            """

            parametros.append(
                faixa_etaria.upper()
            )

        query += """
            ORDER BY
                score_editorial DESC,
                s.data_realizacao DESC NULLS LAST,
                c.quantidade_videos DESC
            LIMIT %s
        """

        parametros.append(
            limite
        )

        cursor.execute(
            query,
            parametros
        )

        dados = cursor.fetchall()

        colunas = [
            desc[0]
            for desc in cursor.description
        ]

        resultados = []

        for linha in dados:

            item = dict(
                zip(
                    colunas,
                    linha
                )
            )

            for chave, valor in item.items():

                if hasattr(
                    valor,
                    "isoformat"
                ):
                    item[chave] = (
                        valor.isoformat()
                    )

            item["drive_url"] = (
                "https://drive.google.com/"
                "drive/folders/"
                + item["drive_folder_id"]
            )

            resultados.append(
                item
            )

        return {
            "total": len(resultados),
            "sugestoes": resultados
        }

    finally:

        cursor.close()
        conexao.close()
@app.get("/historico-publicados")
def historico_publicados(
    ano: int | None = None,
    tipo_conteudo: str | None = None
):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        query = """
            SELECT
                p.id AS producao_id,
                p.sonho_id,

                s.nome,
                s.idade,
                s.sonho,
                s.data_realizacao,
                s.drive_folder_id,
                s.drive_folder_name,

                c.faixa_etaria,
                c.quantidade_fotos,
                c.quantidade_videos,

                p.tipo_conteudo,
                p.status,
                p.data_publicacao,
                p.data_atualizacao

            FROM producao_conteudo p

            INNER JOIN sonhos s
                ON s.id = p.sonho_id

            LEFT JOIN conteudo_sonhos c
                ON c.sonho_id = s.id

            WHERE p.status = 'PUBLICADO'
        """

        parametros = []

        if ano is not None:

            query += """
                AND EXTRACT(
                    YEAR FROM p.data_publicacao
                ) = %s
            """

            parametros.append(
                ano
            )

        if tipo_conteudo:

            query += """
                AND p.tipo_conteudo = %s
            """

            parametros.append(
                tipo_conteudo.upper()
            )

        query += """
            ORDER BY
                p.data_publicacao DESC NULLS LAST,
                p.data_atualizacao DESC
        """

        cursor.execute(
            query,
            parametros
        )

        dados = cursor.fetchall()

        colunas = [
            desc[0]
            for desc in cursor.description
        ]

        resultados = []

        for linha in dados:

            item = dict(
                zip(
                    colunas,
                    linha
                )
            )

            for chave, valor in item.items():

                if hasattr(
                    valor,
                    "isoformat"
                ):

                    item[chave] = (
                        valor.isoformat()
                    )

            if item["drive_folder_id"]:

                item["drive_url"] = (
                    "https://drive.google.com/"
                    "drive/folders/"
                    + item["drive_folder_id"]
                )

            else:

                item["drive_url"] = None

            resultados.append(
                item
            )

        return {
            "total": len(resultados),
            "resultados": resultados
        }

    finally:

        cursor.close()
        conexao.close()
