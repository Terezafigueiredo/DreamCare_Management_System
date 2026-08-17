import os
import re
import csv
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

import psycopg2
from dotenv import load_dotenv

from google_drive import conectar_drive, listar_pastas_drive


load_dotenv()

ID_PASTA_SONHOS = os.getenv("ID_PASTA_SONHOS")

MESES_PT = {
    "jan": 1,
    "janeiro": 1,
    "fev": 2,
    "fevereiro": 2,
    "mar": 3,
    "marco": 3,
    "março": 3,
    "abr": 4,
    "abril": 4,
    "mai": 5,
    "maio": 5,
    "jun": 6,
    "junho": 6,
    "jul": 7,
    "julho": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "setembro": 9,
    "out": 10,
    "outubro": 10,
    "nov": 11,
    "novembro": 11,
    "dez": 12,
    "dezembro": 12
}


# =========================================================
# BANCO
# =========================================================

def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def carregar_sonhos_banco():
    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            idade,
            data_realizacao,
            sonho,
            enfermidade,
            idealizador
        FROM sonhos
        ORDER BY id;
    """)

    registros = cursor.fetchall()

    cursor.close()
    conexao.close()

    sonhos = []

    for registro in registros:
        sonhos.append({
            "id": registro[0],
            "nome": registro[1],
            "idade": registro[2],
            "data_realizacao": registro[3],
            "sonho": registro[4],
            "enfermidade": registro[5],
            "idealizador": registro[6]
        })

    return sonhos


# =========================================================
# NORMALIZAÇÃO
# =========================================================

def remover_acentos(texto):
    if texto is None:
        return ""

    texto = str(texto)

    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


def normalizar_texto(texto):
    texto = remover_acentos(texto)
    texto = texto.lower().strip()

    texto = re.sub(
        r"[^a-z0-9\s]",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def palavras_nome(nome):
    ignorar = {
        "da", "de", "do", "das", "dos",
        "e"
    }

    palavras = normalizar_texto(nome).split()

    return [
        palavra
        for palavra in palavras
        if palavra not in ignorar
        and len(palavra) >= 2
    ]


def primeiro_nome(nome):
    palavras = palavras_nome(nome)

    if not palavras:
        return ""

    return palavras[0]


# =========================================================
# DATAS DAS PASTAS
# =========================================================

def extrair_data_numerica(nome_pasta):
    texto = normalizar_texto(nome_pasta)

    # DDMMYYYY
    encontrados = re.findall(
        r"(?<!\d)(\d{8})(?!\d)",
        texto
    )

    for valor in encontrados:
        try:
            return datetime.strptime(
                valor,
                "%d%m%Y"
            ).date()
        except ValueError:
            pass

    # DDMMYY
    encontrados = re.findall(
        r"(?<!\d)(\d{6})(?!\d)",
        texto
    )

    for valor in encontrados:
        try:
            return datetime.strptime(
                valor,
                "%d%m%y"
            ).date()
        except ValueError:
            pass

    return None


def extrair_data_escrita(nome_pasta):
    texto = normalizar_texto(nome_pasta)

    padrao = (
        r"\b(\d{1,2})\s+"
        r"([a-z]+)\s+"
        r"(\d{2,4})\b"
    )

    correspondencia = re.search(
        padrao,
        texto
    )

    if not correspondencia:
        return None

    dia = int(correspondencia.group(1))
    mes_texto = correspondencia.group(2)
    ano = int(correspondencia.group(3))

    mes = MESES_PT.get(mes_texto)

    if not mes:
        return None

    if ano < 100:
        ano += 2000

    try:
        return datetime(
            ano,
            mes,
            dia
        ).date()

    except ValueError:
        return None


def extrair_data_nome_pasta(nome_pasta):
    data = extrair_data_numerica(
        nome_pasta
    )

    if data:
        return data

    return extrair_data_escrita(
        nome_pasta
    )


def remover_datas_nome_pasta(nome_pasta):
    texto = normalizar_texto(
        nome_pasta
    )

    texto = re.sub(
        r"(?<!\d)\d{8}(?!\d)",
        " ",
        texto
    )

    texto = re.sub(
        r"(?<!\d)\d{6}(?!\d)",
        " ",
        texto
    )

    texto = re.sub(
        r"\b\d{1,2}\s+[a-z]+\s+\d{2,4}\b",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# =========================================================
# DRIVE
# =========================================================

def carregar_pastas_sonhos(service):
    pastas_anos = listar_pastas_drive(
        service,
        ID_PASTA_SONHOS
    )

    resultado = []

    for pasta_ano in pastas_anos:
        nome_ano = pasta_ano["name"]

        if not (
            nome_ano.isdigit()
            and len(nome_ano) == 4
        ):
            continue

        sonhos = listar_pastas_drive(
            service,
            pasta_ano["id"]
        )

        for pasta in sonhos:
            resultado.append({
                "ano": int(nome_ano),
                "id_drive": pasta["id"],
                "nome_pasta": pasta["name"],
                "data_pasta": extrair_data_nome_pasta(
                    pasta["name"]
                ),
                "nome_limpo": remover_datas_nome_pasta(
                    pasta["name"]
                )
            })

    return resultado


# =========================================================
# SEMELHANÇA DE NOMES
# =========================================================

def contar_palavras_comuns(nome_banco, nome_pasta):
    palavras_banco = set(
        palavras_nome(nome_banco)
    )

    palavras_pasta = set(
        palavras_nome(nome_pasta)
    )

    comuns = palavras_banco.intersection(
        palavras_pasta
    )

    return len(comuns)


def proporcao_palavras(nome_banco, nome_pasta):
    palavras_banco = set(
        palavras_nome(nome_banco)
    )

    if not palavras_banco:
        return 0

    comuns = contar_palavras_comuns(
        nome_banco,
        nome_pasta
    )

    return comuns / len(palavras_banco)
def similaridade_texto(texto1, texto2):
    """
    Compara dois textos e retorna uma similaridade entre 0 e 1.
    """
    texto1 = normalizar_texto(texto1)
    texto2 = normalizar_texto(texto2)

    if not texto1 or not texto2:
        return 0

    return SequenceMatcher(
        None,
        texto1,
        texto2
    ).ratio()


def similaridade_primeiro_nome(nome1, nome2):
    """
    Compara o primeiro nome, permitindo pequenas diferenças
    de grafia, como Victoria/Vitoria e Ary/Ari.
    """
    primeiro1 = primeiro_nome(nome1)
    primeiro2 = primeiro_nome(nome2)

    if not primeiro1 or not primeiro2:
        return 0

    return SequenceMatcher(
        None,
        primeiro1,
        primeiro2
    ).ratio()

# =========================================================
# PONTUAÇÃO
# =========================================================

def calcular_pontuacao(sonho, pasta):
    score = 0
    motivos = []

    nome_banco = normalizar_texto(
        sonho["nome"]
    )

    nome_pasta = normalizar_texto(
        pasta["nome_limpo"]
    )

    primeiro_banco = primeiro_nome(
        sonho["nome"]
    )

    primeiro_pasta = primeiro_nome(
        pasta["nome_limpo"]
    )

    data_banco = sonho["data_realizacao"]
    data_pasta = pasta["data_pasta"]

    # -----------------------------------------
    # NOME EXATO
    # -----------------------------------------

    if (
        nome_banco
        and nome_pasta
        and nome_banco == nome_pasta
    ):
        score += 70
        motivos.append("nome exato")

    # -----------------------------------------
    # NOME CONTIDO
    # -----------------------------------------

    elif (
        nome_banco
        and nome_pasta
        and (
            nome_banco in nome_pasta
            or nome_pasta in nome_banco
        )
    ):
        score += 50
        motivos.append("nome contido")

    # -----------------------------------------
    # PALAVRAS EM COMUM
    # -----------------------------------------

    comuns = contar_palavras_comuns(
        sonho["nome"],
        pasta["nome_limpo"]
    )

    proporcao = proporcao_palavras(
        sonho["nome"],
        pasta["nome_limpo"]
    )

    if comuns >= 3:
        score += 40
        motivos.append(
            f"{comuns} palavras do nome iguais"
        )

    elif comuns == 2:
        score += 30
        motivos.append(
            "2 palavras do nome iguais"
        )

    elif comuns == 1:
        score += 15
        motivos.append(
            "1 palavra do nome igual"
        )

    if proporcao >= 0.75:
        score += 20
        motivos.append(
            "maior parte do nome compatível"
        )

    # -----------------------------------------
    # PRIMEIRO NOME
    # -----------------------------------------

    if (
        primeiro_banco
        and primeiro_pasta
        and primeiro_banco == primeiro_pasta
    ):
        score += 15
        motivos.append(
            "primeiro nome igual"
        )
            # -----------------------------------------
    # SIMILARIDADE DE GRAFIA
    # -----------------------------------------

    similaridade_nome = similaridade_texto(
        sonho["nome"],
        pasta["nome_limpo"]
    )

    similaridade_primeiro = similaridade_primeiro_nome(
        sonho["nome"],
        pasta["nome_limpo"]
    )

    if (
        similaridade_nome >= 0.88
        and nome_banco != nome_pasta
    ):
        score += 35
        motivos.append(
            f"nome muito semelhante "
            f"({similaridade_nome:.0%})"
        )

    elif (
        similaridade_nome >= 0.75
        and nome_banco != nome_pasta
    ):
        score += 20
        motivos.append(
            f"nome semelhante "
            f"({similaridade_nome:.0%})"
        )

    if (
        similaridade_primeiro >= 0.80
        and primeiro_banco != primeiro_pasta
    ):
        score += 25
        motivos.append(
            f"primeiro nome semelhante "
            f"({similaridade_primeiro:.0%})"
        )

    # -----------------------------------------
    # ANO
    # -----------------------------------------

    if data_banco:
        if data_banco.year == pasta["ano"]:
            score += 20
            motivos.append(
                "ano igual"
            )
        else:
            score -= 35
            motivos.append(
                "ano diferente"
            )

    # -----------------------------------------
    # DATA COMPLETA
    # -----------------------------------------

    if data_banco and data_pasta:
        if data_banco == data_pasta:
            score += 55
            motivos.append(
                "data exata"
            )
        else:
            score -= 20
            motivos.append(
                "data diferente"
            )

    return score, motivos


# =========================================================
# CRUZAMENTO ÚNICO
# =========================================================

def gerar_candidatos(sonhos, pastas):
    candidatos = []

    for sonho in sonhos:
        for pasta in pastas:
            score, motivos = calcular_pontuacao(
                sonho,
                pasta
            )

            if score >= 35:
                candidatos.append({
                    "sonho": sonho,
                    "pasta": pasta,
                    "score": score,
                    "motivos": motivos
                })

    candidatos.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return candidatos


def cruzar_dados(sonhos, pastas):
    candidatos = gerar_candidatos(
        sonhos,
        pastas
    )

    sonhos_usados = set()
    pastas_usadas = set()

    resultados = []

    for candidato in candidatos:
        id_sonho = candidato["sonho"]["id"]
        id_pasta = candidato["pasta"]["id_drive"]

        if id_sonho in sonhos_usados:
            continue

        if id_pasta in pastas_usadas:
            continue

        score = candidato["score"]

        if score >= 110:
         status = "EXATO"

        elif score >= 80:
         status = "PROVAVEL"

        elif score >= 60:
         status = "REVISAR"

        else:
            continue

        resultados.append({
            "sonho": candidato["sonho"],
            "pasta": candidato["pasta"],
            "score": score,
            "motivos": candidato["motivos"],
            "status": status
        })

        sonhos_usados.add(
            id_sonho
        )

        pastas_usadas.add(
            id_pasta
        )

    sem_pasta = [
        sonho
        for sonho in sonhos
        if sonho["id"] not in sonhos_usados
    ]

    pastas_sem_banco = [
        pasta
        for pasta in pastas
        if pasta["id_drive"] not in pastas_usadas
    ]

    return (
        resultados,
        sem_pasta,
        pastas_sem_banco
    )


# =========================================================
# CSV
# =========================================================

def gerar_csv(
    resultados,
    sem_pasta,
    pastas_sem_banco
):
    os.makedirs(
        "relatorios",
        exist_ok=True
    )

    caminho = os.path.join(
        "relatorios",
        "vinculos_drive.csv"
    )

    with open(
        caminho,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as arquivo:

        campos = [
            "status",
            "id_sonho",
            "nome_banco",
            "idade",
            "data_realizacao",
            "sonho",
            "ano_drive",
            "nome_pasta_drive",
            "id_pasta_drive",
            "score",
            "motivos"
        ]

        writer = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=";"
        )

        writer.writeheader()

        for item in resultados:
            writer.writerow({
                "status": item["status"],
                "id_sonho": item["sonho"]["id"],
                "nome_banco": item["sonho"]["nome"],
                "idade": item["sonho"]["idade"],
                "data_realizacao":
                    item["sonho"]["data_realizacao"],
                "sonho": item["sonho"]["sonho"],
                "ano_drive": item["pasta"]["ano"],
                "nome_pasta_drive":
                    item["pasta"]["nome_pasta"],
                "id_pasta_drive":
                    item["pasta"]["id_drive"],
                "score": item["score"],
                "motivos": ", ".join(
                    item["motivos"]
                )
            })

        for sonho in sem_pasta:
            writer.writerow({
                "status": "SEM_PASTA",
                "id_sonho": sonho["id"],
                "nome_banco": sonho["nome"],
                "idade": sonho["idade"],
                "data_realizacao":
                    sonho["data_realizacao"],
                "sonho": sonho["sonho"],
                "ano_drive": "",
                "nome_pasta_drive": "",
                "id_pasta_drive": "",
                "score": "",
                "motivos": ""
            })

        for pasta in pastas_sem_banco:
            writer.writerow({
                "status": "PASTA_SEM_BANCO",
                "id_sonho": "",
                "nome_banco": "",
                "idade": "",
                "data_realizacao": "",
                "sonho": "",
                "ano_drive": pasta["ano"],
                "nome_pasta_drive":
                    pasta["nome_pasta"],
                "id_pasta_drive":
                    pasta["id_drive"],
                "score": "",
                "motivos": ""
            })

    return caminho


# =========================================================
# RELATÓRIO TERMINAL
# =========================================================

def imprimir_relatorio(
    resultados,
    sem_pasta,
    pastas_sem_banco,
    total_banco,
    total_drive
):
    exatos = [
        item
        for item in resultados
        if item["status"] == "EXATO"
    ]

    provaveis = [
        item
        for item in resultados
        if item["status"] == "PROVAVEL"
    ]
    revisar = [
    item
    for item in resultados
    if item["status"] == "REVISAR"
]

    print("\n" + "=" * 70)
    print("DREAMCARE - VÍNCULO BANCO x GOOGLE DRIVE V2")
    print("=" * 70)

    print(
        f"\n💙 Sonhos no PostgreSQL: {total_banco}"
    )

    print(
        f"📁 Pastas no Google Drive: {total_drive}"
    )

    print("\n" + "-" * 70)

    print(
        f"✅ Vínculos exatos: {len(exatos)}"
    )

    print(
        f"🟡 Vínculos prováveis: {len(provaveis)}"
    )
    print(
    f"🟠 Revisar manualmente: {len(revisar)}"
    )

    print(
        f"❌ Sem pasta encontrada: {len(sem_pasta)}"
    )

    print(
        f"❓ Pastas sem vínculo: {len(pastas_sem_banco)}"
    )

    print("-" * 70)

    print(
        "\n✅ Cada pasta foi usada no máximo uma vez."
    )

    print(
        "✅ Cada sonho foi usado no máximo uma vez."
    )


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 70)
    print("🚀 DREAMCARE - VÍNCULO DRIVE V2")
    print("=" * 70)

    print(
        "\n🔄 Lendo PostgreSQL..."
    )

    sonhos = carregar_sonhos_banco()

    print(
        f"✅ {len(sonhos)} sonhos carregados."
    )

    print(
        "\n🔄 Conectando ao Google Drive..."
    )

    service = conectar_drive()

    print(
        "\n🔄 Lendo pastas..."
    )

    pastas = carregar_pastas_sonhos(
        service
    )

    print(
        f"✅ {len(pastas)} pastas carregadas."
    )

    print(
        "\n🔍 Fazendo cruzamento inteligente..."
    )

    (
        resultados,
        sem_pasta,
        pastas_sem_banco
    ) = cruzar_dados(
        sonhos,
        pastas
    )

    imprimir_relatorio(
        resultados,
        sem_pasta,
        pastas_sem_banco,
        len(sonhos),
        len(pastas)
    )

    caminho_csv = gerar_csv(
        resultados,
        sem_pasta,
        pastas_sem_banco
    )

    print(
        f"\n📄 Relatório criado em: {caminho_csv}"
    )

    print(
        "\n✅ Análise concluída."
    )

    print(
        "Nenhum dado do banco ou Drive foi alterado."
    )


if __name__ == "__main__":
    main()