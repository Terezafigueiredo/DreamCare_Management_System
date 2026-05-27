import pandas as pd
import matplotlib.pyplot as plt

# carregar planilha
df = pd.read_excel("sonhos_tratados.xlsx")

# limpar nomes das colunas
df.columns = df.columns.str.strip()

# converter data
df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")

# criar coluna ano
df["ANO"] = df["DATA"].dt.year

print("=" * 50)
print("MÉTRICAS DREAMCARE")
print("=" * 50)

# total de sonhos
print("\nTOTAL DE SONHOS:")
print(len(df))

# ano com mais sonhos
print("\nSONHOS POR ANO:")
sonhos_ano = df["ANO"].value_counts().sort_index()

print(sonhos_ano)

print("\nANO COM MAIS SONHOS:")
print(sonhos_ano.idxmax())

# sexo mais atendido
print("\nSEXO MAIS ATENDIDO:")
sexo = df["SEXO"].value_counts()

print(sexo)

print("\nSEXO COM MAIS SONHOS:")
print(sexo.idxmax())

# média de idade
print("\nMÉDIA DE IDADE:")
print(round(df["IDADE"].mean(), 1))

# menor idade
print("\nMENOR IDADE:")
print(df["IDADE"].min())

# maior idade
print("\nMAIOR IDADE:")
print(df["IDADE"].max())

# sonho mais frequente
print("\nTOP 10 SONHOS:")
print(df["SONHO"].value_counts().head(10))

# enfermidades mais frequentes
print("\nENFERMIDADES MAIS ATENDIDAS:")
print(df["ENFERMIDADE"].value_counts().head(10))

# contato que mais idealizou sonhos
print("\nCONTATOS QUE MAIS IDEALIZARAM SONHOS:")
contatos = df["CONTATO"].value_counts()

print(contatos)

print("\nCONTATO QUE MAIS IDEALIZOU SONHOS:")
print(contatos.idxmax())

# criar faixa etária
df["FAIXA_ETARIA"] = pd.cut(
    df["IDADE"],
    bins=[0, 18, 30, 50, 80, 120],
    labels=["0-18", "19-30", "31-50", "51-80", "80+"]
)

faixa_etaria = df["FAIXA_ETARIA"].value_counts().sort_index()

print("\nFAIXA ETÁRIA:")
print(faixa_etaria)

# salvar relatório em Excel
with pd.ExcelWriter("relatorio_metricas.xlsx") as writer:
    sonhos_ano.to_excel(writer, sheet_name="Sonhos por ano")
    sexo.to_excel(writer, sheet_name="Sexo")
    df["SONHO"].value_counts().head(10).to_excel(writer, sheet_name="Top sonhos")
    df["ENFERMIDADE"].value_counts().head(10).to_excel(writer, sheet_name="Enfermidades")
    contatos.to_excel(writer, sheet_name="Contatos")
    faixa_etaria.to_excel(writer, sheet_name="Faixa etaria")

print("\nRelatório Excel gerado com sucesso!")

# gráfico sonhos por ano
sonhos_ano.plot(kind="bar", title="Sonhos por Ano")
plt.xlabel("Ano")
plt.ylabel("Quantidade")
plt.tight_layout()
plt.savefig("sonhos_por_ano.png")
plt.show()

# gráfico sexo
sexo.plot(kind="bar", title="Sonhos por Sexo")
plt.xlabel("Sexo")
plt.ylabel("Quantidade")
plt.tight_layout()
plt.savefig("sonhos_por_sexo.png")
plt.show()

# gráfico top contatos
contatos.head(10).plot(kind="bar", title="Top 10 Contatos")
plt.xlabel("Contato")
plt.ylabel("Quantidade")
plt.tight_layout()
plt.savefig("top_contatos.png")
plt.show()