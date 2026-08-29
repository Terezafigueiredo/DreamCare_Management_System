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
            CREATE TABLE IF NOT EXISTS producoes_institucionais (
                id SERIAL PRIMARY KEY,

                titulo TEXT NOT NULL,

                status VARCHAR(30)
                    DEFAULT 'RASCUNHO',

                selecao_editorial JSONB
                    NOT NULL DEFAULT '[]'::jsonb,

                identidade_narrativa JSONB
                    NOT NULL DEFAULT '{}'::jsonb,

                video_vertical_path TEXT,
                video_horizontal_path TEXT,
                erro_automacao TEXT,

                data_criacao TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                data_atualizacao TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conexao.commit()

        print("=" * 60)
        print("DREAMCARE - VÍDEO INSTITUCIONAL ROPE")
        print("=" * 60)

        print(
            "✅ Tabela producoes_institucionais criada/verificada."
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
