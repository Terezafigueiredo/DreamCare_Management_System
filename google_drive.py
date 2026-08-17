from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import io
import os
import pickle
from dotenv import load_dotenv


load_dotenv()


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

ID_PLANILHA_PRINCIPAL = os.getenv(
    "ID_PLANILHA_PRINCIPAL"
)

CAMINHO_DESTINO = os.getenv(
    "CAMINHO_DESTINO"
)

ID_PASTA_SONHOS = os.getenv(
    "ID_PASTA_SONHOS"
)


MIME_GOOGLE_SHEETS = (
    "application/vnd.google-apps.spreadsheet"
)

MIME_XLSX = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


# =========================================================
# CONEXÃO COM GOOGLE DRIVE
# =========================================================

def conectar_drive():

    print("🔄 Conectando ao Google Drive...")

    creds = None

    if os.path.exists("token.pickle"):

        print("✅ Token encontrado.")

        with open(
            "token.pickle",
            "rb"
        ) as token:

            creds = pickle.load(token)

    if not creds:

        print("🔐 Fazendo login no Google...")

        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials/credentials.json",
            SCOPES
        )

        creds = flow.run_local_server(
            port=0,
            open_browser=True
        )

        with open(
            "token.pickle",
            "wb"
        ) as token:

            pickle.dump(
                creds,
                token
            )

        print("✅ Login realizado.")

    service = build(
        "drive",
        "v3",
        credentials=creds
    )

    print(
        "✅ Serviço do Drive conectado."
    )

    return service


# =========================================================
# LISTAR PASTAS
# =========================================================

def listar_pastas_drive(
    service,
    parent_id
):

    query = (
        "mimeType='application/vnd.google-apps.folder' "
        "and trashed=false "
        f"and '{parent_id}' in parents"
    )

    pastas = []

    page_token = None

    while True:

        resposta = service.files().list(
            q=query,
            spaces="drive",
            fields=(
                "nextPageToken, "
                "files(id, name, parents)"
            ),
            pageToken=page_token,
            pageSize=1000
        ).execute()

        pastas.extend(
            resposta.get(
                "files",
                []
            )
        )

        page_token = resposta.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return pastas


# =========================================================
# LISTAR ANOS E SONHOS
# =========================================================

def listar_anos_e_sonhos(
    service
):

    print(
        "\n📁 Lendo estrutura "
        "de sonhos do Drive...\n"
    )

    if not ID_PASTA_SONHOS:

        print(
            "❌ ID_PASTA_SONHOS "
            "não configurado."
        )

        return []

    pastas_principais = listar_pastas_drive(
        service,
        ID_PASTA_SONHOS
    )

    estrutura = []

    for pasta in pastas_principais:

        nome_pasta = pasta["name"]
        id_pasta = pasta["id"]

        if (
            nome_pasta.isdigit()
            and len(nome_pasta) == 4
        ):

            print("=" * 60)

            print(
                f"📅 ANO: {nome_pasta}"
            )

            sonhos = listar_pastas_drive(
                service,
                id_pasta
            )

            print(
                f"📂 {len(sonhos)} "
                "pastas de sonhos encontradas."
            )

            for sonho in sonhos:

                print(
                    f"   💙 {sonho['name']} "
                    f"| ID: {sonho['id']}"
                )

            estrutura.append(
                {
                    "ano": nome_pasta,
                    "id_pasta_ano": id_pasta,
                    "sonhos": sonhos
                }
            )

            print()

    return estrutura


# =========================================================
# EXPORTAR GOOGLE SHEETS PARA XLSX
# =========================================================

def exportar_planilha_google(
    service,
    file_id,
    caminho_destino
):

    print(
        "\n⬇️ Exportando planilha "
        "atual do Google Sheets..."
    )

    # Confere qual é o tipo real do arquivo
    metadata = service.files().get(
        fileId=file_id,
        fields="id,name,mimeType"
    ).execute()

    nome = metadata.get(
        "name",
        "Sem nome"
    )

    mime_type = metadata.get(
        "mimeType"
    )

    print(
        f"📄 Planilha encontrada: {nome}"
    )

    print(
        f"📦 Tipo do arquivo: {mime_type}"
    )

    # Se for uma Google Sheet nativa
    if mime_type == MIME_GOOGLE_SHEETS:

        print(
            "✅ Google Sheets detectado."
        )

        request = service.files().export_media(
            fileId=file_id,
            mimeType=MIME_XLSX
        )

    else:

        # Mantém compatibilidade caso no futuro
        # seja um XLSX comum armazenado no Drive
        print(
            "ℹ️ Arquivo comum detectado."
        )

        request = service.files().get_media(
            fileId=file_id
        )

    arquivo = io.BytesIO()

    downloader = MediaIoBaseDownload(
        arquivo,
        request
    )

    concluido = False

    while not concluido:

        status, concluido = (
            downloader.next_chunk()
        )

        if status:

            porcentagem = int(
                status.progress() * 100
            )

            print(
                f"Download: {porcentagem}%"
            )

    arquivo.seek(0)

    pasta_destino = os.path.dirname(
        caminho_destino
    )

    if pasta_destino:

        os.makedirs(
            pasta_destino,
            exist_ok=True
        )

    with open(
        caminho_destino,
        "wb"
    ) as arquivo_saida:

        arquivo_saida.write(
            arquivo.read()
        )

    print(
        f"✅ Planilha atual salva em: "
        f"{caminho_destino}"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)

    print(
        "🚀 DREAMCARE GOOGLE DRIVE SYNC"
    )

    print("=" * 60)

    service = conectar_drive()

    # -----------------------------------------------------
    # LEITURA DAS PASTAS DOS SONHOS
    # -----------------------------------------------------

    estrutura = listar_anos_e_sonhos(
        service
    )

    total_sonhos_drive = sum(
        len(item["sonhos"])
        for item in estrutura
    )

    print(
        "\n" + "=" * 60
    )

    print(
        "📊 RESUMO DO GOOGLE DRIVE"
    )

    print("=" * 60)

    print(
        f"📅 Anos encontrados: "
        f"{len(estrutura)}"
    )

    print(
        f"💙 Pastas de sonhos encontradas: "
        f"{total_sonhos_drive}"
    )

    # -----------------------------------------------------
    # EXPORTAÇÃO DA PLANILHA ATUAL
    # -----------------------------------------------------

    if (
        ID_PLANILHA_PRINCIPAL
        and CAMINHO_DESTINO
    ):

        exportar_planilha_google(
            service,
            ID_PLANILHA_PRINCIPAL,
            CAMINHO_DESTINO
        )

    else:

        print(
            "\n❌ ID_PLANILHA_PRINCIPAL "
            "ou CAMINHO_DESTINO "
            "não configurado no .env."
        )

    print(
        "\n✅ Sincronização do Drive "
        "finalizada com sucesso."
    )

    print("=" * 60)


if __name__ == "__main__":
    main()