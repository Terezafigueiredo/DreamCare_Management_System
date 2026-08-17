from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()


def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


try:
    conexao = conectar_banco()
    cursor = conexao.cursor()

    print("\n" + "=" * 70)
    print("        DREAMCARE - DIAGNÓSTICO DO BANCO DE DADOS")
    print("=" * 70)

    # ------------------------------------------------
    # DESCOBRIR AS COLUNAS REAIS DA TABELA
    # ------------------------------------------------

    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'sonhos'
        ORDER BY ordinal_position;
    """)

    colunas = [
        linha[0]
        for linha in cursor.fetchall()
    ]

    print("\n📋 COLUNAS DA TABELA SONHOS:\n")

    for coluna in colunas:
        print(f"   • {coluna}")

    # ------------------------------------------------
    # TOTAL DE SONHOS
    # ------------------------------------------------

    cursor.execute(
        "SELECT COUNT(*) FROM sonhos"
    )

    total = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print(f"💙 TOTAL DE SONHOS NO BANCO: {total}")
    print("-" * 70)

    # ------------------------------------------------
    # MOSTRAR ALGUNS REGISTROS
    # ------------------------------------------------

    cursor.execute("""
        SELECT *
        FROM sonhos
        ORDER BY id
        LIMIT 10;
    """)

    registros = cursor.fetchall()

    print("\n🔎 PRIMEIROS 10 REGISTROS:\n")

    for registro in registros:

        dados = dict(
            zip(
                colunas,
                registro
            )
        )

        print("=" * 50)

        # Mostra os campos mais importantes
        for campo in [
            "id",
            "nome",
            "idade",
            "data_realizacao",
            "sonho"
        ]:

            if campo in dados:
                print(
                    f"{campo.upper()}: "
                    f"{dados[campo]}"
                )

    print("\n" + "=" * 70)
    print("✅ Consulta concluída com sucesso.")
    print("=" * 70)

    cursor.close()
    conexao.close()

except Exception as erro:

    print("\n❌ Erro encontrado:")
    print(erro)