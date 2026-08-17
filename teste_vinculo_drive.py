import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def main():
    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                id,
                nome,
                idade,
                data_realizacao,
                sonho,
                drive_folder_name,
                drive_folder_id,
                drive_match_status
            FROM sonhos
            WHERE drive_match_status = 'EXATO'
              AND drive_folder_id IS NOT NULL
            ORDER BY id
            LIMIT 10;
        """)

        registros = cursor.fetchall()

        print("=" * 70)
        print("DREAMCARE - TESTE DE VÍNCULOS COM O DRIVE")
        print("=" * 70)

        for registro in registros:
            (
                id_sonho,
                nome,
                idade,
                data_realizacao,
                sonho,
                pasta_nome,
                pasta_id,
                status
            ) = registro

            print("\n" + "-" * 70)
            print(f"ID: {id_sonho}")
            print(f"NOME: {nome}")
            print(f"IDADE: {idade}")
            print(f"DATA: {data_realizacao}")
            print(f"SONHO: {sonho}")
            print(f"PASTA DRIVE: {pasta_nome}")
            print(f"ID PASTA: {pasta_id}")
            print(f"STATUS: {status}")

        print("\n" + "=" * 70)
        print(f"✅ {len(registros)} vínculos consultados com sucesso.")
        print("=" * 70)

    except Exception as erro:
        print("\n❌ Erro:")
        print(erro)

    finally:
        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


if __name__ == "__main__":
    main()