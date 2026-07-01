from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="DreamCare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )

@app.get("/")
def home():
    return {"mensagem": "API DreamCare funcionando"}

@app.get("/sonhos")
def listar_sonhos():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT *
        FROM sonhos
        ORDER BY id ASC
    """)

    dados = cursor.fetchall()
    colunas = [desc[0] for desc in cursor.description]

    sonhos = []

    for linha in dados:
        sonho = dict(zip(colunas, linha))

        for chave, valor in sonho.items():
            if hasattr(valor, "isoformat"):
                sonho[chave] = valor.isoformat()

        sonhos.append(sonho)

    cursor.close()
    conexao.close()

    return {
        "total": len(sonhos),
        "sonhos": sonhos
    }