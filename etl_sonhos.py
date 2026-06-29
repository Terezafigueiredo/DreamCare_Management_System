import pandas as pd


def carregar_sonhos_tratados():
    """
    Lê a planilha de sonhos, realiza todo o tratamento dos dados
    e retorna um DataFrame limpo.
    """

    # ==========================
    # Leitura da planilha
    # ==========================
    df = pd.read_excel("dados/sonhos.xlsx", header=None)

    # Localiza a linha do cabeçalho
    linha_cabecalho = None

    for i, linha in df.iterrows():
        if "SONHADOR" in linha.astype(str).tolist():
            linha_cabecalho = i
            break

    if linha_cabecalho is None:
        raise ValueError("Cabeçalho da planilha não encontrado.")

    # Define o cabeçalho correto
    df.columns = df.iloc[linha_cabecalho]
    df = df.iloc[linha_cabecalho + 1:]

    # ==========================
    # Limpeza inicial
    # ==========================
    df = df.dropna(axis=1, how="all")
    df = df.dropna(how="all")
    df = df.reset_index(drop=True)

    # ==========================
    # Padronização dos nomes das colunas
    # ==========================
    df.columns = [
        "id",
        "nome",
        "sexo",
        "estado",
        "idade",
        "idealizador",
        "data_realizacao",
        "sonho",
        "enfermidade",
        "obito",
        "pessoas_impactadas",
        "impacto_total",
        "valor_aproximado",
        "gasto"
    ]

    # Remove colunas que não serão utilizadas
    df = df.drop(columns=["valor_aproximado", "gasto"])

    # ==========================
    # Remove espaços em branco
    # ==========================
    df = df.apply(
        lambda coluna: coluna.map(
            lambda valor: valor.strip() if isinstance(valor, str) else valor
        )
    )

    # ==========================
    # Padronização dos textos
    # ==========================
    df["nome"] = df["nome"].str.title()
    df["sexo"] = df["sexo"].str.upper()
    df["estado"] = df["estado"].str.upper()
    df["idealizador"] = df["idealizador"].str.title()
    df["enfermidade"] = df["enfermidade"].str.lower()

    # ==========================
    # Conversão dos tipos
    # ==========================
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["idade"] = pd.to_numeric(df["idade"], errors="coerce")
    df["impacto_total"] = pd.to_numeric(df["impacto_total"], errors="coerce")

    df["data_realizacao"] = pd.to_datetime(
        df["data_realizacao"],
        errors="coerce",
        dayfirst=True
    )

    # ==========================
    # Remoção de registros inválidos
    # ==========================
    df = df.dropna(subset=["id", "nome"])
    df = df[df["nome"] != ""]
    df = df.drop_duplicates()

    # ==========================
    # Ajuste dos tipos finais
    # ==========================
    df["id"] = df["id"].astype(int)

    # Reorganiza o índice
    df = df.reset_index(drop=True)

    return df