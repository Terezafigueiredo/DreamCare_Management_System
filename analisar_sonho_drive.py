import os
import psycopg2
from dotenv import load_dotenv

from google_drive import conectar_drive

load_dotenv()


# =========================================================
# BANCO
# =========================================================

def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def buscar_sonho_vinculado():
    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            idade,
            data_realizacao,
            sonho,
            enfermidade,
            idealizador,
            drive_folder_name,
            drive_folder_id,
            drive_match_status
        FROM sonhos
        WHERE drive_match_status = 'EXATO'
          AND drive_folder_id IS NOT NULL
        ORDER BY id
        LIMIT 1;
    """)

    registro = cursor.fetchone()

    cursor.close()
    conexao.close()

    return registro


# =========================================================
# FAIXA ETÁRIA
# =========================================================

def classificar_faixa_etaria(idade):

    if idade is None:
        return "IDADE_NAO_INFORMADA"

    try:
        idade = int(idade)
    except (TypeError, ValueError):
        return "IDADE_NAO_INFORMADA"

    if idade <= 12:
        return "CRIANCA"

    elif idade <= 17:
        return "ADOLESCENTE"

    else:
        return "ADULTO"


# =========================================================
# GOOGLE DRIVE
# =========================================================

def listar_itens_pasta(service, pasta_id):

    itens = []
    page_token = None

    while True:

        resposta = service.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            spaces="drive",
            fields=(
                "nextPageToken,"
                "files("
                "id,"
                "name,"
                "mimeType,"
                "webViewLink,"
                "size"
                ")"
            ),
            pageToken=page_token,
            pageSize=1000
        ).execute()

        itens.extend(
            resposta.get("files", [])
        )

        page_token = resposta.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return itens


def ler_pasta_recursivamente(
    service,
    pasta_id,
    caminho=""
):

    fotos = []
    videos = []
    outros = []
    subpastas = []

    itens = listar_itens_pasta(
        service,
        pasta_id
    )

    for item in itens:

        nome = item.get(
            "name",
            "Sem nome"
        )

        mime_type = item.get(
            "mimeType",
            ""
        )

        caminho_item = (
            f"{caminho}/{nome}"
            if caminho
            else nome
        )

        if mime_type == "application/vnd.google-apps.folder":

            subpastas.append({
                "id": item["id"],
                "nome": nome,
                "caminho": caminho_item
            })

            resultado_subpasta = ler_pasta_recursivamente(
                service,
                item["id"],
                caminho_item
            )

            fotos.extend(
                resultado_subpasta["fotos"]
            )

            videos.extend(
                resultado_subpasta["videos"]
            )

            outros.extend(
                resultado_subpasta["outros"]
            )

            subpastas.extend(
                resultado_subpasta["subpastas"]
            )

        elif mime_type.startswith("image/"):

            fotos.append({
                "id": item["id"],
                "nome": nome,
                "caminho": caminho_item,
                "mimeType": mime_type
            })

        elif mime_type.startswith("video/"):

            videos.append({
                "id": item["id"],
                "nome": nome,
                "caminho": caminho_item,
                "mimeType": mime_type
            })

        else:

            outros.append({
                "id": item["id"],
                "nome": nome,
                "caminho": caminho_item,
                "mimeType": mime_type
            })

    return {
        "fotos": fotos,
        "videos": videos,
        "outros": outros,
        "subpastas": subpastas
    }


# =========================================================
# SALVAR ANÁLISE
# =========================================================

def salvar_analise(
    sonho_id,
    faixa_etaria,
    quantidade_fotos,
    quantidade_videos,
    quantidade_subpastas,
    quantidade_outros
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            INSERT INTO conteudo_sonhos (
                sonho_id,
                faixa_etaria,
                quantidade_fotos,
                quantidade_videos,
                quantidade_subpastas,
                quantidade_outros,
                conteudo_analisado,
                status_post,
                data_ultima_analise
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE,
                'PRONTO_PARA_IA',
                CURRENT_TIMESTAMP
            )

            ON CONFLICT (sonho_id)
            DO UPDATE SET

                faixa_etaria =
                    EXCLUDED.faixa_etaria,

                quantidade_fotos =
                    EXCLUDED.quantidade_fotos,

                quantidade_videos =
                    EXCLUDED.quantidade_videos,

                quantidade_subpastas =
                    EXCLUDED.quantidade_subpastas,

                quantidade_outros =
                    EXCLUDED.quantidade_outros,

                conteudo_analisado = TRUE,

                status_post =
                    'PRONTO_PARA_IA',

                data_ultima_analise =
                    CURRENT_TIMESTAMP;
        """, (
            sonho_id,
            faixa_etaria,
            quantidade_fotos,
            quantidade_videos,
            quantidade_subpastas,
            quantidade_outros
        ))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        cursor.close()
        conexao.close()


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("🚀 DREAMCARE - ANÁLISE DE CONTEÚDO")
    print("=" * 70)

    print(
        "\n🔄 Buscando sonho vinculado..."
    )

    sonho = buscar_sonho_vinculado()

    if not sonho:

        print(
            "❌ Nenhum sonho vinculado encontrado."
        )

        return

    (
        id_sonho,
        nome,
        idade,
        data_realizacao,
        descricao_sonho,
        enfermidade,
        idealizador,
        pasta_nome,
        pasta_id,
        status
    ) = sonho

    faixa_etaria = classificar_faixa_etaria(
        idade
    )

    print(
        f"\n💙 Sonho #{id_sonho}"
    )

    print(
        f"👤 Nome: {nome}"
    )

    print(
        f"🎂 Idade: {idade}"
    )

    print(
        f"👥 Faixa etária: {faixa_etaria}"
    )

    print(
        f"💭 Sonho: {descricao_sonho}"
    )

    print(
        f"📁 Pasta: {pasta_nome}"
    )

    print(
        "\n🔄 Conectando ao Google Drive..."
    )

    service = conectar_drive()

    print(
        "\n🔎 Analisando pasta e subpastas..."
    )

    resultado = ler_pasta_recursivamente(
        service,
        pasta_id
    )

    fotos = resultado["fotos"]
    videos = resultado["videos"]
    subpastas = resultado["subpastas"]
    outros = resultado["outros"]

    print("\n" + "=" * 70)
    print("📊 RESULTADO")
    print("=" * 70)

    print(
        f"📷 Fotos: {len(fotos)}"
    )

    print(
        f"🎥 Vídeos: {len(videos)}"
    )

    print(
        f"📂 Subpastas: {len(subpastas)}"
    )

    print(
        f"📄 Outros: {len(outros)}"
    )

    print(
        "\n💾 Salvando análise no PostgreSQL..."
    )

    salvar_analise(
        id_sonho,
        faixa_etaria,
        len(fotos),
        len(videos),
        len(subpastas),
        len(outros)
    )

    print(
        "✅ Análise salva em conteudo_sonhos."
    )

    print(
        "✅ Status: PRONTO_PARA_IA"
    )

    print("\n" + "=" * 70)
    print("✅ Processo concluído.")
    print("=" * 70)


if __name__ == "__main__":
    main()