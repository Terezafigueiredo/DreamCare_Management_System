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
            CREATE TABLE IF NOT EXISTS producao_conteudo (
                id SERIAL PRIMARY KEY,

                sonho_id INTEGER NOT NULL,

                tipo_conteudo VARCHAR(30)
                    DEFAULT 'NAO_DEFINIDO',

                status VARCHAR(30)
                    DEFAULT 'A_FAZER',

                observacoes TEXT,

                data_criacao TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                data_atualizacao TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                data_publicacao DATE,

                CONSTRAINT fk_producao_sonho
                    FOREIGN KEY (sonho_id)
                    REFERENCES sonhos(id)
                    ON DELETE CASCADE,

                CONSTRAINT uq_producao_sonho
                    UNIQUE (sonho_id)
            );
        """)

        conexao.commit()

        print("=" * 60)
        print("DREAMCARE - PRODUÇÃO DE CONTEÚDO")
        print("=" * 60)

        print(
            "✅ Tabela producao_conteudo criada/verificada."
        )

        print(
            "✅ Nenhum sonho foi adicionado à produção ainda."
        )

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