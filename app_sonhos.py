import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import os

# Carrega variáveis do .env
load_dotenv()

def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def listar_sonhos():
    for item in tabela.get_children():
        tabela.delete(item)

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute('SELECT * FROM sonhos ORDER BY "ID" ASC')
    dados = cursor.fetchall()

    for linha in dados:
        tabela.insert("", tk.END, values=linha)

    cursor.close()
    conexao.close()


def limpar_campos():
    entrada_nome.delete(0, tk.END)
    entrada_sexo.delete(0, tk.END)
    entrada_idade.delete(0, tk.END)
    entrada_data.delete(0, tk.END)
    entrada_sonho.delete(0, tk.END)
    entrada_enfermidade.delete(0, tk.END)
    entrada_contato.delete(0, tk.END)

def formatar_nome(texto):
    return texto.title()

def cadastrar_sonho():
    nome = formatar_nome(entrada_nome.get())
    sexo = entrada_sexo.get().upper()
    idade = entrada_idade.get()
    data = entrada_data.get()
    sonho = formatar_nome(entrada_sonho.get())
    enfermidade = formatar_nome(entrada_enfermidade.get())
    contato = formatar_nome(entrada_contato.get())
    

    if nome == "" or sonho == "":
        messagebox.showwarning("Atenção", "Nome e sonho são obrigatórios")
        return
    
    if not idade.isdigit():
        messagebox.showwarning("Atenção", "Idade deve conter apenas números")
        return
    try:
        data = datetime.strptime(data, "%Y-%m-%d").date()
    except ValueError:
        messagebox.showwarning(
            "Atenção",
            "Digite a data no formato AAAA-MM-DD. Exemplo: 2026-05-20"
        )
        return

    confirmar = messagebox.askyesno(
        "Confirmar cadastro",
        "Deseja realmente cadastrar este sonho?"
    )

    if not confirmar:
        return
    

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO sonhos ("NOME", "SEXO", "IDADE", "DATA", "SONHO", "ENFERMIDADE", "CONTATO")
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (nome, sexo, idade, data, sonho, enfermidade, contato))

    conexao.commit()
    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho cadastrado com sucesso!")
    limpar_campos()
    listar_sonhos()


def pesquisar():
    termo = entrada_pesquisa.get()

    for item in tabela.get_children():
        tabela.delete(item)

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT * FROM sonhos
        WHERE "NOME" ILIKE %s
        OR "SONHO" ILIKE %s
        OR "ENFERMIDADE" ILIKE %s
        OR "CONTATO" ILIKE %s
        ORDER BY "ID" ASC
    """, (f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%"))

    dados = cursor.fetchall()

    for linha in dados:
        tabela.insert("", tk.END, values=linha)

    cursor.close()
    conexao.close()


def selecionar_sonho(event):
    item = tabela.selection()

    if item:
        valores = tabela.item(item, "values")

        limpar_campos()

        entrada_nome.insert(0, valores[1])
        entrada_sexo.insert(0, valores[2])
        entrada_idade.insert(0, valores[3])
        entrada_data.insert(0, valores[4])
        entrada_sonho.insert(0, valores[5])
        entrada_enfermidade.insert(0, valores[6])
        entrada_contato.insert(0, valores[7])


def editar_sonho():
    item = tabela.selection()

    if not item:
        messagebox.showwarning("Atenção", "Selecione um sonho para editar")
        return

    valores = tabela.item(item, "values")
    id_sonho = valores[0]

    nome = entrada_nome.get()
    sexo = entrada_sexo.get()
    idade = entrada_idade.get()
    data = entrada_data.get()
    sonho = entrada_sonho.get()
    enfermidade = entrada_enfermidade.get()
    contato = entrada_contato.get()

    confirmar = messagebox.askyesno(
        "Confirmar edição",
        "Deseja realmente editar este sonho?"
    )

    if not confirmar:
        return

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE sonhos
        SET "NOME" = %s,
            "SEXO" = %s,
            "IDADE" = %s,
            "DATA" = %s,
            "SONHO" = %s,
            "ENFERMIDADE" = %s,
            "CONTATO" = %s
        WHERE "ID" = %s
    """, (nome, sexo, idade, data, sonho, enfermidade, contato, id_sonho))

    conexao.commit()
    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho editado com sucesso!")
    limpar_campos()
    listar_sonhos()


def excluir_sonho():
    item = tabela.selection()

    if not item:
        messagebox.showwarning("Atenção", "Selecione um sonho para excluir")
        return

    confirmar = messagebox.askyesno(
        "Confirmar exclusão",
        "Deseja realmente excluir este sonho?"
    )

    if not confirmar:
        return

    valores = tabela.item(item, "values")
    id_sonho = valores[0]

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute('DELETE FROM sonhos WHERE "ID" = %s', (id_sonho,))

    conexao.commit()
    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho excluído com sucesso!")
    limpar_campos()
    listar_sonhos()


janela = tk.Tk()
janela.title("Sistema de Sonhos - Instituto Rope")
janela.geometry("1200x700")

titulo = tk.Label(
    janela,
    text="Sistema de Gestão de Sonhos",
    font=("Arial", 18, "bold")
)
titulo.pack(pady=10)


frame_form = tk.LabelFrame(janela, text="Cadastro / Edição", padx=10, pady=10)
frame_form.pack(fill="x", padx=20, pady=10)

tk.Label(frame_form, text="Nome").grid(row=0, column=0, sticky="w")
entrada_nome = tk.Entry(frame_form, width=35)
entrada_nome.grid(row=0, column=1, padx=10, pady=5)

tk.Label(frame_form, text="Sexo F/M").grid(row=0, column=2, sticky="w")
entrada_sexo = tk.Entry(frame_form, width=10)
entrada_sexo.grid(row=0, column=3, padx=10, pady=5)

tk.Label(frame_form, text="Idade").grid(row=0, column=4, sticky="w")
entrada_idade = tk.Entry(frame_form, width=10)
entrada_idade.grid(row=0, column=5, padx=10, pady=5)

tk.Label(frame_form, text="Data").grid(row=1, column=0, sticky="w")
entrada_data = tk.Entry(frame_form, width=20)
entrada_data.grid(row=1, column=1, padx=10, pady=5)

tk.Label(frame_form, text="Sonho").grid(row=1, column=2, sticky="w")
entrada_sonho = tk.Entry(frame_form, width=35)
entrada_sonho.grid(row=1, column=3, padx=10, pady=5)

tk.Label(frame_form, text="Enfermidade").grid(row=2, column=0, sticky="w")
entrada_enfermidade = tk.Entry(frame_form, width=35)
entrada_enfermidade.grid(row=2, column=1, padx=10, pady=5)

tk.Label(frame_form, text="Contato").grid(row=2, column=2, sticky="w")
entrada_contato = tk.Entry(frame_form, width=25)
entrada_contato.grid(row=2, column=3, padx=10, pady=5)


frame_botoes = tk.Frame(janela)
frame_botoes.pack(fill="x", padx=20, pady=5)

tk.Button(frame_botoes, text="Cadastrar", width=15, command=cadastrar_sonho).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Editar", width=15, command=editar_sonho).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Excluir", width=15, bg="#d9534f", fg="white", command=excluir_sonho).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Limpar", width=15, command=limpar_campos).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Listar Todos", width=15, command=listar_sonhos).pack(side="left", padx=5)


frame_pesquisa = tk.LabelFrame(janela, text="Pesquisa", padx=10, pady=10)
frame_pesquisa.pack(fill="x", padx=20, pady=10)

tk.Label(frame_pesquisa, text="Pesquisar por nome, sonho, enfermidade ou contato").pack(side="left")

entrada_pesquisa = tk.Entry(frame_pesquisa, width=40)
entrada_pesquisa.pack(side="left", padx=10)

tk.Button(frame_pesquisa, text="Buscar", width=15, command=pesquisar).pack(side="left")


frame_tabela = tk.Frame(janela)
frame_tabela.pack(fill="both", expand=True, padx=20, pady=10)

colunas = ("ID", "NOME", "SEXO", "IDADE", "DATA", "SONHO", "ENFERMIDADE", "CONTATO")

tabela = ttk.Treeview(frame_tabela, columns=colunas, show="headings")

for coluna in colunas:
    tabela.heading(coluna, text=coluna)
    tabela.column(coluna, width=140)

tabela.pack(side="left", fill="both", expand=True)

barra_rolagem = ttk.Scrollbar(frame_tabela, orient="vertical", command=tabela.yview)
barra_rolagem.pack(side="right", fill="y")

tabela.configure(yscrollcommand=barra_rolagem.set)
tabela.bind("<<TreeviewSelect>>", selecionar_sonho)

listar_sonhos()

janela.mainloop()