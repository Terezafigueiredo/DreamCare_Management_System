import pandas as pd
import sqlite3

# caminho da planilha
arquivo = r"C:\Users\Usuario\OneDrive\Desktop\Projeto Ropeti\sonhos_tratados.xlsx"

df = pd.read_excel(arquivo) #ler arquivo

conexao = sqlite3.connect('banco.db') #conectar banco

df.to_sql('sonhos', conexao, if_exists='replace', index=False) #envia dados

conexao.close()#fecha conexão
print("Banco criado com sucesso!")


#abriu o Excel +leu os dados+criou o banco banco.db+criou a tabela sonhos+inseriu todos os registros