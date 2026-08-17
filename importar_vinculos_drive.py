import os
import csv
import psycopg2
from dotenv import load_dotenv

load_dotenv()

CAMINHO_CSV = os.path.join(
    "relatorios",
    "vinculos_drive.csv"
)


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
    print("DREAMCARE - IMPORTAÇÃO DE VÍNCULOS DO DRIVE")
    print("=" * 60)

    conexao = None
    cursor = None

    try:

        # =================================================
        # LER CSV
        # =================================================

        print("\n📄 Lendo relatório de vínculos...")

        if not os.path.exists(CAMINHO_CSV):
            raise FileNotFoundError(
                f"Arquivo não encontrado: {CAMINHO_CSV}"
            )

        with open(
            CAMINHO_CSV,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as arquivo:

            amostra = arquivo.read(4096)
            arquivo.seek(0)

            dialect = csv.Sniffer().sniff(
                amostra,
                delimiters=",;\t"
            )

            leitor = csv.DictReader(
                arquivo,
                dialect=dialect
            )

            if not leitor.fieldnames:
                raise ValueError(
                    "O CSV não possui cabeçalho."
                )

            leitor.fieldnames = [
                coluna.strip()
                for coluna in leitor.fieldnames
            ]

            print(
                f"📋 Colunas encontradas: {leitor.fieldnames}"
            )

            vinculos_exatos = []

            for linha in leitor:

                status = (
                    linha.get("status") or ""
                ).strip().upper()

                if status == "EXATO":
                    vinculos_exatos.append(linha)

        print(
            f"✅ {len(vinculos_exatos)} vínculos EXATOS encontrados."
        )

        if len(vinculos_exatos) == 0:
            raise ValueError(
                "Nenhum vínculo EXATO foi encontrado no CSV."
            )

        # =================================================
        # CONECTAR AO BANCO
        # =================================================

        print("\n🔄 Conectando ao PostgreSQL...")

        conexao = conectar_banco()
        cursor = conexao.cursor()

        print("✅ Banco conectado.")

        # =================================================
        # GRAVAR VÍNCULOS
        # =================================================

        print("\n🔗 Gravando vínculos seguros...")

        atualizados = 0
        nao_encontrados = 0
        ignorados = 0

        for vinculo in vinculos_exatos:

            id_texto = (
                vinculo.get("id_sonho") or ""
            ).strip()

            pasta_id = (
                vinculo.get("id_pasta_drive") or ""
            ).strip()

            pasta_nome = (
                vinculo.get("nome_pasta_drive") or ""
            ).strip()

            if not id_texto or not pasta_id:
                ignorados += 1
                continue

            id_sonho = int(id_texto)

            cursor.execute(
                """
                UPDATE sonhos
                SET
                    drive_folder_id = %s,
                    drive_folder_name = %s,
                    drive_match_status = %s
                WHERE id = %s
                """,
                (
                    pasta_id,
                    pasta_nome,
                    "EXATO",
                    id_sonho
                )
            )

            if cursor.rowcount == 1:
                atualizados += 1
            else:
                nao_encontrados += 1

        conexao.commit()

        # =================================================
        # CONFERÊNCIA
        # =================================================

        cursor.execute("""
            SELECT COUNT(*)
            FROM sonhos
            WHERE drive_match_status = 'EXATO'
              AND drive_folder_id IS NOT NULL;
        """)

        total_banco = cursor.fetchone()[0]

        print("\n" + "=" * 60)
        print("📊 RESULTADO")
        print("=" * 60)

        print(
            f"📄 Vínculos EXATOS no CSV: {len(vinculos_exatos)}"
        )

        print(
            f"✅ Sonhos atualizados: {atualizados}"
        )

        print(
            f"⚠️ IDs não encontrados: {nao_encontrados}"
        )

        print(
            f"⚠️ Linhas ignoradas: {ignorados}"
        )

        print(
            f"💾 Vínculos EXATOS confirmados no banco: {total_banco}"
        )

        print("=" * 60)

        if total_banco == len(vinculos_exatos):
            print(
                "\n🎉 Banco e relatório estão consistentes."
            )
        else:
            print(
                "\n⚠️ Existe diferença entre o CSV e o banco."
            )

    except Exception as erro:

        if conexao:
            conexao.rollback()

        print("\n❌ Erro durante a importação:")
        print(erro)

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


if __name__ == "__main__":
    main()