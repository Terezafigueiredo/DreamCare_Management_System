import os
import time
import psycopg2
from dotenv import load_dotenv

from google_drive import conectar_drive
from analisar_sonho_drive import (
    classificar_faixa_etaria,
    ler_pasta_recursivamente,
    salvar_analise
)

load_dotenv()


def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def buscar_sonhos_vinculados():
    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            idade,
            drive_folder_name,
            drive_folder_id
        FROM sonhos
        WHERE drive_match_status = 'EXATO'
          AND drive_folder_id IS NOT NULL
        ORDER BY id;
    """)

    registros = cursor.fetchall()

    cursor.close()
    conexao.close()

    return registros


def main():
    inicio = time.time()

    print("=" * 70)
    print("DREAMCARE - PROCESSAMENTO EM LOTE")
    print("=" * 70)

    print("\n🔄 Buscando sonhos vinculados no PostgreSQL...")

    sonhos = buscar_sonhos_vinculados()

    print(
        f"✅ {len(sonhos)} sonhos com vínculo EXATO encontrados."
    )

    if not sonhos:
        print("❌ Nenhum sonho disponível.")
        return

    print("\n🔄 Conectando ao Google Drive...")

    service = conectar_drive()

    print("✅ Google Drive conectado.")

    processados = 0
    erros = 0

    total_fotos = 0
    total_videos = 0
    total_subpastas = 0
    total_outros = 0

    print("\n🚀 Iniciando análise...\n")

    for indice, sonho in enumerate(sonhos, start=1):

        (
            id_sonho,
            nome,
            idade,
            pasta_nome,
            pasta_id
        ) = sonho

        print("-" * 70)
        print(
            f"[{indice}/{len(sonhos)}] "
            f"ID {id_sonho} | {nome}"
        )

        print(
            f"📁 {pasta_nome}"
        )

        try:
            faixa_etaria = classificar_faixa_etaria(
                idade
            )

            resultado = ler_pasta_recursivamente(
                service,
                pasta_id
            )

            fotos = resultado["fotos"]
            videos = resultado["videos"]
            subpastas = resultado["subpastas"]
            outros = resultado["outros"]

            salvar_analise(
                id_sonho,
                faixa_etaria,
                len(fotos),
                len(videos),
                len(subpastas),
                len(outros)
            )

            total_fotos += len(fotos)
            total_videos += len(videos)
            total_subpastas += len(subpastas)
            total_outros += len(outros)

            processados += 1

            print(
                f"✅ {faixa_etaria} | "
                f"📷 {len(fotos)} | "
                f"🎥 {len(videos)} | "
                f"📂 {len(subpastas)}"
            )

        except Exception as erro:

            erros += 1

            print(
                f"❌ Erro no sonho ID {id_sonho}: "
                f"{erro}"
            )

            # O processamento continua mesmo com erro
            continue

    fim = time.time()

    print("\n" + "=" * 70)
    print("📊 RESUMO DO PROCESSAMENTO")
    print("=" * 70)

    print(
        f"💙 Sonhos encontrados: {len(sonhos)}"
    )

    print(
        f"✅ Processados com sucesso: {processados}"
    )

    print(
        f"❌ Com erro: {erros}"
    )

    print(
        f"📷 Fotos encontradas: {total_fotos}"
    )

    print(
        f"🎥 Vídeos encontrados: {total_videos}"
    )

    print(
        f"📂 Subpastas encontradas: {total_subpastas}"
    )

    print(
        f"📄 Outros arquivos: {total_outros}"
    )

    print(
        f"⏱️ Tempo total: {fim - inicio:.2f} segundos"
    )

    print("=" * 70)

    print(
        "\n✅ Base de conteúdo atualizada."
    )

    print(
        "✅ Sonhos processados ficaram com "
        "status PRONTO_PARA_IA."
    )


if __name__ == "__main__":
    main()