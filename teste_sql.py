import sqlite3
import pandas as pd

conexao = sqlite3.connect("banco.db")

query = "SELECT * FROM sonhos"

df = pd.read_sql(query, conexao)

print(df)

conexao.close()


um pipeline ETL+ simples integração Excel → +Banco persistência de dados+início de um sistema real