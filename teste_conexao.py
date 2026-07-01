from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()

try:
    conexao = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )

    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM sonhos LIMIT 5")
    dados = cursor.fetchall()

    print("Conexão funcionando!")
    print(dados)

    cursor.close()
    conexao.close()

except Exception as erro:
    print("Erro encontrado:")
    print(erro)