import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# ======================================
# CARREGA AS VARIÁVEIS DO ARQUIVO .env
# ======================================
load_dotenv()

# ======================================
# DADOS DO BANCO
# ======================================
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

# ======================================
# CAMINHO DA PLANILHA
# ======================================
arquivo = r"C:\Users\Usuario\OneDrive\Desktop\Projeto Ropeti\sonhos_tratados.xlsx"

# ======================================
# LÊ O EXCEL
# ======================================
df = pd.read_excel(arquivo)

# ======================================
# CRIA A CONEXÃO COM O POSTGRESQL
# ======================================
DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{DB_USER}:{DB_PASSWORD}@"
    f"{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)

# ======================================
# IMPORTA PARA O POSTGRESQL
# ======================================
df.to_sql(
    "sonhos",
    engine,
    if_exists="replace",
    index=False
)

print("✅ Dados enviados com sucesso para o PostgreSQL!")