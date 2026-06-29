from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import io
import os
import pickle


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

ID_PLANILHA_PRINCIPAL = "1MnU15iZqCmChA-FgwAww-UhxjR-MY1i1"
CAMINHO_DESTINO = "dados/sonhos.xlsx"


def conectar_drive():
    print("🔄 Conectando ao Google Drive...")

    creds = None

    if os.path.exists("token.pickle"):
        print("✅ Token encontrado.")
        with open("token.pickle", "rb") as token:
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

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

        print("✅ Login realizado.")

    service = build("drive", "v3", credentials=creds)

    print("✅ Serviço do Drive conectado.")
    return service


def baixar_planilha_google(service, file_id, caminho_destino):
    print("⬇️ Baixando planilha principal do Google Drive...")

    request = service.files().get_media(fileId=file_id)

    arquivo = io.BytesIO()
    downloader = MediaIoBaseDownload(arquivo, request)

    concluido = False

    while not concluido:
        status, concluido = downloader.next_chunk()

        if status:
            print(f"Download: {int(status.progress() * 100)}%")

    arquivo.seek(0)

    os.makedirs(os.path.dirname(caminho_destino), exist_ok=True)

    with open(caminho_destino, "wb") as f:
        f.write(arquivo.read())

    print(f"✅ Planilha salva em: {caminho_destino}")


print("🚀 Iniciando DreamCare Google Drive Sync...")

service = conectar_drive()

baixar_planilha_google(
    service,
    ID_PLANILHA_PRINCIPAL,
    CAMINHO_DESTINO
)

print("✅ Sincronização finalizada com sucesso.")