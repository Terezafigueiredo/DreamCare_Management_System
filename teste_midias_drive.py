import os
import psycopg2
from dotenv import load_dotenv

from google_drive import conectar_drive

load_dotenv()


def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def buscar_sonho():
    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            idade,
            sonho,
            drive_folder_name,
            drive_folder_id
        FROM sonhos
        WHERE drive_match_status = 'EXATO'
          AND drive_folder_id IS NOT NULL
        ORDER BY id
        LIMIT 1;
    """)

    sonho = cursor.fetchone()

    cursor.close()
    conexao.close()

    return sonho


def listar_arquivos_pasta(service, pasta_id):

    arquivos = []
    page_token = None

    while True:

        resultado = service.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            spaces="drive",
            fields=(
                "nextPageToken,"
                "files(id,name,mimeType,webViewLink)"
            ),
            pageToken=page_token,
            pageSize=1000
        ).execute()

        arquivos.extend(
            resultado.get("files", [])
        )

        page_token = resultado.get("nextPageToken")

        if not page_token:
            break

    return arquivos


def classificar_arquivos(arquivos):

    fotos = []
    videos = []
    outros = []
    subpastas = []

    for arquivo in arquivos:

        tipo = arquivo.get("mimeType", "")

        if tipo == "application/vnd.google-apps.folder":
            subpastas.append(arquivo)

        elif tipo.startswith("image/"):
            fotos.append(arquivo)

        elif tipo.startswith("video/"):
            videos.append(arquivo)

        else:
            outros.append(arquivo)

    return fotos, videos, outros, subpastas


def main():

    print("=" * 65)
    print("DREAMCARE - LEITURA DE MÍDIAS DO GOOGLE DRIVE")
    print("=" * 65)

    sonho = buscar_sonho()

    if not sonho:
        print("❌ Nenhum sonho vinculado encontrado.")
        return

    (
        id_sonho,
        nome,
        idade,
        descricao_sonho,
        pasta_nome,
        pasta_id
    ) = sonho

    print(f"\n💙 Sonho #{id_sonho}")
    print(f"👤 Nome: {nome}")
    print(f"🎂 Idade: {idade}")
    print(f"💭 Sonho: {descricao_sonho}")
    print(f"📁 Pasta: {pasta_nome}")

    print("\n🔄 Conectando ao Google Drive...")

    service = conectar_drive()

    print("\n🔎 Lendo arquivos da pasta...")

    arquivos = listar_arquivos_pasta(
        service,
        pasta_id
    )

    fotos, videos, outros, subpastas = classificar_arquivos(
        arquivos
    )

    print("\n" + "=" * 65)
    print("📊 MÍDIAS ENCONTRADAS")
    print("=" * 65)

    print(f"📷 Fotos: {len(fotos)}")
    print(f"🎥 Vídeos: {len(videos)}")
    print(f"📂 Subpastas: {len(subpastas)}")
    print(f"📄 Outros arquivos: {len(outros)}")

    if fotos:
        print("\n📷 Algumas fotos:")

        for foto in fotos[:5]:
            print(f"   • {foto['name']}")

    if videos:
        print("\n🎥 Alguns vídeos:")

        for video in videos[:5]:
            print(f"   • {video['name']}")

    if subpastas:
        print("\n📂 Subpastas:")

        for pasta in subpastas[:10]:
            print(f"   • {pasta['name']}")

    print("\n✅ Leitura concluída.")


if __name__ == "__main__":
    main()
    