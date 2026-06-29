import pandas as pd


# LEITURA DA PLANILHA


df = pd.read_excel("dados/sonhos.xlsx", header=None)

# Procura automaticamente a linha do cabeçalho
linha_cabecalho = None

for i, linha in df.iterrows():
    if "SONHADOR" in linha.astype(str).tolist():
        linha_cabecalho = i
        break

# Define o cabeçalho
df.columns = df.iloc[linha_cabecalho]

# Remove as linhas acima
df = df.iloc[linha_cabecalho + 1:]

# Remove linhas e colunas vazias
df = df.dropna(axis=1, how="all")
df = df.dropna(how="all")

# Reinicia o índice
df = df.reset_index(drop=True)


# PADRONIZAÇÃO DOS NOMES


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


# REMOVE COLUNAS DESNECESSÁRIAS


df = df.drop(columns=[
    "valor_aproximado",
    "gasto"
])


# LIMPEZA DOS DADOS


# Remove espaços extras
df = df.apply(lambda coluna: coluna.map(
    lambda valor: valor.strip() if isinstance(valor, str) else valor
))

# Padroniza textos
df["nome"] = df["nome"].str.title()

df["sexo"] = df["sexo"].str.upper()

df["estado"] = df["estado"].str.upper()

df["idealizador"] = df["idealizador"].str.title()

df["enfermidade"] = df["enfermidade"].str.lower()


# CONVERSÕES


df["idade"] = pd.to_numeric(df["idade"], errors="coerce")

df["impacto_total"] = pd.to_numeric(
    df["impacto_total"],
    errors="coerce"
)

df["data_realizacao"] = pd.to_datetime(
    df["data_realizacao"],
    errors="coerce",
    dayfirst=True
)


# VISUALIZAÇÃO


print("\n==============================")
print("DADOS TRATADOS")
print("==============================\n")

print(df.head())

print("\n==============================")
print("COLUNAS")
print("==============================\n")

print(df.columns.tolist())

print("\n==============================")
print("TOTAL DE SONHOS")
print("==============================\n")

print(len(df))