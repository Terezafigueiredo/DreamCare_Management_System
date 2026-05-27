import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="DreamCare Analytics", layout="wide")

df = pd.read_excel("sonhos_tratados.xlsx")
df.columns = df.columns.str.strip()
df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")
df["ANO"] = df["DATA"].dt.year

st.title("DreamCare Analytics")
st.write("Sistema de análise dos sonhos realizados")

opcao = st.sidebar.selectbox(
    "Escolha o que deseja visualizar:",
    [
        "Visão geral",
        "Sonhos por ano",
        "Distribuição por sexo",
        "Faixa etária",
        "Top sonhos",
        "Enfermidades",
        "Contatos",
        "Tabela completa"
    ]
)

if opcao == "Visão geral":
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total de sonhos", len(df))
    col2.metric("Média de idade", round(df["IDADE"].mean(), 1))
    col3.metric("Ano com mais sonhos", int(df["ANO"].value_counts().idxmax()))
    col4.metric("Sexo mais atendido", df["SEXO"].value_counts().idxmax())

elif opcao == "Sonhos por ano":
    dados = df["ANO"].value_counts().sort_index().reset_index()
    dados.columns = ["ANO", "QUANTIDADE"]

    fig = px.bar(dados, x="ANO", y="QUANTIDADE", title="Sonhos por Ano")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Distribuição por sexo":
    dados = df["SEXO"].value_counts().reset_index()
    dados.columns = ["SEXO", "QUANTIDADE"]

    fig = px.pie(dados, names="SEXO", values="QUANTIDADE", title="Distribuição por Sexo")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Faixa etária":
    df["FAIXA_ETARIA"] = pd.cut(
        df["IDADE"],
        bins=[0, 18, 30, 50, 80, 120],
        labels=["0-18", "19-30", "31-50", "51-80", "80+"]
    )

    dados = df["FAIXA_ETARIA"].value_counts().sort_index().reset_index()
    dados.columns = ["FAIXA ETÁRIA", "QUANTIDADE"]

    fig = px.bar(dados, x="FAIXA ETÁRIA", y="QUANTIDADE", title="Sonhos por Faixa Etária")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Top sonhos":
    dados = df["SONHO"].value_counts().head(10).reset_index()
    dados.columns = ["SONHO", "QUANTIDADE"]

    fig = px.bar(dados, x="QUANTIDADE", y="SONHO", orientation="h", title="Top 10 Sonhos")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Enfermidades":
    dados = df["ENFERMIDADE"].value_counts().head(10).reset_index()
    dados.columns = ["ENFERMIDADE", "QUANTIDADE"]

    fig = px.bar(dados, x="QUANTIDADE", y="ENFERMIDADE", orientation="h", title="Top 10 Enfermidades")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Contatos":
    dados = df["CONTATO"].value_counts().head(10).reset_index()
    dados.columns = ["CONTATO", "QUANTIDADE"]

    fig = px.bar(dados, x="QUANTIDADE", y="CONTATO", orientation="h", title="Top 10 Contatos")
    st.plotly_chart(fig, use_container_width=True)

elif opcao == "Tabela completa":
    st.dataframe(df)