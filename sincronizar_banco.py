import os
import time
import psycopg2
import pandas as pd

from dotenv import load_dotenv
from etl_sonhos import carregar_sonhos_tratados

load_dotenv()


def conectar_banco():
    conexao = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )
    return conexao


def tratar_valor(valor):
    if pd.isna(valor):
        return None
    return valor


def carregar_ids_existentes(cursor):
    cursor.execute("""
        SELECT id
        FROM sonhos
    """)

    resultado = cursor.fetchall()
    ids_existentes = {linha[0] for linha in resultado}

    return ids_existentes


def inserir_sonho(cursor, linha):
    cursor.execute("""
        INSERT INTO sonhos (
            id, nome, sexo, estado, idade, idealizador,
            data_realizacao, sonho, enfermidade, obito,
            pessoas_impactadas, impacto_total
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        tratar_valor(linha["id"]),
        tratar_valor(linha["nome"]),
        tratar_valor(linha["sexo"]),
        tratar_valor(linha["estado"]),
        tratar_valor(linha["idade"]),
        tratar_valor(linha["idealizador"]),
        tratar_valor(linha["data_realizacao"]),
        tratar_valor(linha["sonho"]),
        tratar_valor(linha["enfermidade"]),
        tratar_valor(linha["obito"]),
        tratar_valor(linha["pessoas_impactadas"]),
        tratar_valor(linha["impacto_total"])
    ))


def atualizar_sonho(cursor, linha):
    cursor.execute("""
        UPDATE sonhos
        SET
            nome = %s,
            sexo = %s,
            estado = %s,
            idade = %s,
            idealizador = %s,
            data_realizacao = %s,
            sonho = %s,
            enfermidade = %s,
            obito = %s,
            pessoas_impactadas = %s,
            impacto_total = %s
        WHERE id = %s
    """, (
        tratar_valor(linha["nome"]),
        tratar_valor(linha["sexo"]),
        tratar_valor(linha["estado"]),
        tratar_valor(linha["idade"]),
        tratar_valor(linha["idealizador"]),
        tratar_valor(linha["data_realizacao"]),
        tratar_valor(linha["sonho"]),
        tratar_valor(linha["enfermidade"]),
        tratar_valor(linha["obito"]),
        tratar_valor(linha["pessoas_impactadas"]),
        tratar_valor(linha["impacto_total"]),
        tratar_valor(linha["id"])
    ))


def sincronizar_sonhos(cursor, df):
    inseridos = 0
    atualizados = 0

    ids_existentes = carregar_ids_existentes(cursor)

    for indice, linha in df.iterrows():
        id_sonho = tratar_valor(linha["id"])

        if id_sonho in ids_existentes:
            atualizar_sonho(cursor, linha)
            atualizados += 1
        else:
            inserir_sonho(cursor, linha)
            inseridos += 1
            ids_existentes.add(id_sonho)

    return inseridos, atualizados


if __name__ == "__main__":
    inicio = time.time()

    print("=" * 45)
    print("              DreamCare Sync")
    print("=" * 45)

    print("\n🔄 Conectando ao PostgreSQL...")
    conexao = conectar_banco()
    print("✅ Banco conectado com sucesso.")

    cursor = conexao.cursor()

    print("\n📄 Lendo planilha tratada...")
    df = carregar_sonhos_tratados()
    print(f"✅ {len(df)} registros encontrados na planilha.")

    print("\n🔄 Sincronizando dados com o banco...")
    inseridos, atualizados = sincronizar_sonhos(cursor, df)

    conexao.commit()

    fim = time.time()

    print("\n📊 Resultado da sincronização")
    print("-" * 45)
    print(f"📥 Inseridos: {inseridos}")
    print(f"🔁 Atualizados: {atualizados}")
    print(f"⏱️ Tempo total: {fim - inicio:.2f} segundos")
    print("-" * 45)

    print("\n✅ Sincronização concluída com sucesso!")
    print("=" * 45)

    cursor.close()
    conexao.close()