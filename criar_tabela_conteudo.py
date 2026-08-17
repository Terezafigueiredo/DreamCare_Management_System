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
            CREATE TABLE IF NOT EXISTS conteudo_sonhos (
                id SERIAL PRIMARY KEY,
                sonho_id INTEGER UNIQUE NOT NULL,
                faixa_etaria VARCHAR(30),
                quantidade_fotos INTEGER DEFAULT 0,
                quantidade_videos INTEGER DEFAULT 0,
                quantidade_subpastas INTEGER DEFAULT 0,
                quantidade_outros INTEGER DEFAULT 0,
                conteudo_analisado BOOLEAN DEFAULT FALSE,
                status_post VARCHAR(30) DEFAULT 'NAO_ANALISADO',
                data_ultima_analise TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_sonho
                    FOREIGN KEY (sonho_id)
                    REFERENCES sonhos(id)
                    ON DELETE CASCADE
            );
        """)

        conexao.commit()

        print("=" * 60)
        print("DREAMCARE - CENTRAL DE CONTEÚDO")
        print("=" * 60)
        print("✅ Tabela conteudo_sonhos criada/verificada.")
        print("✅ Nenhum sonho foi alterado.")

    except Exception as erro:
        if conexao:
            conexao.rollback()

        print("❌ Erro:")
        print(erro)

    finally:
        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


if __name__ == "__main__":
    main()