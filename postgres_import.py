import pandas as pd
from sqlalchemy import create_engine

# caminho da planilha
arquivo = r"C:\Users\Usuario\OneDrive\Desktop\Projeto Ropeti\sonhos_tratados.xlsx"

# ler excel
df = pd.read_excel(arquivo)

# conexão postgres
usuario = "postgres"
senha = "#Te88510674"
host = "localhost"
porta = "5432"
banco = "projeto_rope"

engine = create_engine(
    f"postgresql+psycopg2://{usuario}:{senha}@{host}:{porta}/{banco}"
)

# enviar para postgres
df.to_sql(
    "sonhos",
    engine,
    if_exists="replace",
    index=False
)

print("Dados enviados com sucesso!")