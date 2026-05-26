import pandas as pd

arquivo = "sonhos.xlsx"
df = pd.read_excel(arquivo)

# remover espaços nos nomes das colunas
df.columns = df.columns.str.strip()

# padronizar nomes
df["NOME"] = df["NOME"].str.title()

# padronizar sexo
df["SEXO"] = df["SEXO"].str.upper()              # deixa tudo maiúsculo
df["SEXO"] = df["SEXO"].replace("", pd.NA)       # transforma strings vazias em NaN
df["SEXO"] = df["SEXO"].fillna("F")              # preenche NaN com "F"

# converter datas (tratando erros)
df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")

# remover linhas totalmente vazias
df = df.dropna(how="all")

# remover duplicados
df = df.drop_duplicates()

# salvar arquivo limpo
df.to_excel("sonhos_tratados.xlsx", index=False)

print("Dados tratados com sucesso!")
