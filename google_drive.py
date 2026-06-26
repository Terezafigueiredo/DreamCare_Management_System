from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import io
import os
import pickle


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]


def conectar_drive():
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials/credentials.json",
            SCOPES
        )

        creds = flow.run_local_server(
            port=8080,
            open_browser=True
        )

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("drive", "v3", credentials=creds)
    return service


def procurar_pasta(service, nome_pasta):
    resultado = service.files().list(
        q=f"name='{nome_pasta}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)"
    ).execute()

    pastas = resultado.get("files", [])

    if not pastas:
        return None

    return pastas[0]["id"]


def percorrer_pastas(service, id_pasta, planilhas=None):
    if planilhas is None:
        planilhas = []

    resultado = service.files().list(
        q=f"'{id_pasta}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()

    arquivos = resultado.get("files", [])

    for arquivo in arquivos:
        nome = arquivo["name"]
        tipo = arquivo["mimeType"]

        if tipo == "application/vnd.google-apps.folder":
            percorrer_pastas(service, arquivo["id"], planilhas)

        elif (
            nome.endswith(".xlsx")
            or tipo == "application/vnd.google-apps.spreadsheet"
        ):
            planilhas.append({
                "nome": nome,
                "id": arquivo["id"],
                "tipo": tipo
            })

    return planilhas


def baixar_planilha(service, file_id, nome_arquivo):
    print("1 - Preparando download...")

    request = service.files().get_media(fileId=file_id)

    print("2 - Requisição criada.")

    arquivo = io.BytesIO()
    downloader = MediaIoBaseDownload(arquivo, request)

    concluido = False

    while not concluido:
        print("3 - Baixando...")
        status, concluido = downloader.next_chunk()

        if status:
            print(f"Download: {int(status.progress() * 100)}%")

    arquivo.seek(0)

    os.makedirs(os.path.dirname(nome_arquivo), exist_ok=True)

    with open(nome_arquivo, "wb") as f:
        f.write(arquivo.read())

    print(f"✅ Arquivo salvo em {nome_arquivo}")
    
    
    
# PROGRAMA PRINCIPAL
service = conectar_drive()

id_sonhos = procurar_pasta(service, "Sonhos")

if id_sonhos:
    planilhas = percorrer_pastas(service, id_sonhos)

    print(f"\nTotal de planilhas encontradas: {len(planilhas)}\n")

    for planilha in planilhas:
        print(f"{planilha['nome']} --> {planilha['id']}")

    planilha_principal = None

    for planilha in planilhas:
        if planilha["nome"].startswith("Sonhos Realizados"):
            planilha_principal = planilha
            break

    if planilha_principal:
        print("\n===== PLANILHA PRINCIPAL =====")
        print(f"Nome: {planilha_principal['nome']}")
        print(f"ID: {planilha_principal['id']}")

        baixar_planilha(
            service,
            planilha_principal["id"],
            "dados/sonhos.xlsx"
        )

    else:
        print("Planilha principal não encontrada.")

else:
    print("Pasta Sonhos não encontrada.")