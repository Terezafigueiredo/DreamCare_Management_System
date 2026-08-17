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
    print("=" * 60)
    print("DREAMCARE - ALTERAÇÃO DA TABELA SONHOS")
    print("=" * 60)

    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()

        print("\n🔄 Conectado ao PostgreSQL.")

        cursor.execute("""
            ALTER TABLE sonhos
            ADD COLUMN IF NOT EXISTS drive_folder_id TEXT;
        """)

        cursor.execute("""
            ALTER TABLE sonhos
            ADD COLUMN IF NOT EXISTS drive_folder_name TEXT;
        """)

        cursor.execute("""
            ALTER TABLE sonhos
            ADD COLUMN IF NOT EXISTS drive_match_status VARCHAR(30);
        """)

        conexao.commit()

        print("✅ Colunas criadas/verificadas com sucesso.")

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'sonhos'
            AND column_name IN (
                'drive_folder_id',
                'drive_folder_name',
                'drive_match_status'
            )
            ORDER BY column_name;
        """)

        colunas = cursor.fetchall()

        print("\n📋 COLUNAS DE INTEGRAÇÃO:\n")

        for nome, tipo in colunas:
            print(f"   {nome} | {tipo}")

        print("\n✅ Nenhum vínculo foi gravado ainda.")

    except Exception as erro:
        if conexao:
            conexao.rollback()

        print("\n❌ Erro:")
        print(erro)

    finally:
        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


if __name__ == "__main__":
    main()