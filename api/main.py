from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
import os


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
                p.data_publicacao

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