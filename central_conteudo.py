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


def buscar_criancas_com_midias(idade_maxima=9):
    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            s.id,
            s.nome,
            s.idade,
            s.sonho,
            s.data_realizacao,
            s.drive_folder_id,
            s.drive_folder_name,
            c.quantidade_fotos,
            c.quantidade_videos,
            c.faixa_etaria,
            c.status_post
        FROM sonhos s

        INNER JOIN conteudo_sonhos c
            ON c.sonho_id = s.id

        WHERE s.idade <= %s
          AND c.quantidade_fotos > 0
          AND c.quantidade_videos > 0
          AND s.drive_folder_id IS NOT NULL

        ORDER BY s.idade, s.nome;
    """, (
        idade_maxima,
    ))

    registros = cursor.fetchall()

    cursor.close()
    conexao.close()

    return registros


def criar_link_drive(folder_id):
    return (
        "https://drive.google.com/drive/folders/"
        + folder_id
    )


def main():

    print("=" * 75)
    print("DREAMCARE - CENTRAL DE CONTEÚDO")
    print("=" * 75)

    print(
        "\n🔎 Buscando crianças abaixo de 10 anos "
        "com fotos e vídeos...\n"
    )

    resultados = buscar_criancas_com_midias(
        idade_maxima=9
    )

    print(
        f"💙 {len(resultados)} sonhos encontrados."
    )

    for registro in resultados:

        (
            id_sonho,
            nome,
            idade,
            sonho,
            data_realizacao,
            folder_id,
            folder_name,
            fotos,
            videos,
            faixa_etaria,
            status_post
        ) = registro

        link_drive = criar_link_drive(
            folder_id
        )

        print("\n" + "-" * 75)

        print(
            f"💙 ID {id_sonho} | {nome}"
        )

        print(
            f"🎂 Idade: {idade} anos"
        )

        print(
            f"👥 Categoria: {faixa_etaria}"
        )

        print(
            f"💭 Sonho: {sonho}"
        )

        print(
            f"📅 Realização: {data_realizacao}"
        )

        print(
            f"📷 Fotos: {fotos}"
        )

        print(
            f"🎥 Vídeos: {videos}"
        )

        print(
            f"📁 Pasta: {folder_name}"
        )

        print(
            f"🔗 Drive: {link_drive}"
        )

        print(
            f"📌 Status conteúdo: {status_post}"
        )

    print("\n" + "=" * 75)

    print(
        f"✅ Total disponível para conteúdo: "
        f"{len(resultados)}"
    )

    print("=" * 75)


if __name__ == "__main__":
    main()
    