import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2


# conexão com PostgreSQL
def conectar():
    return psycopg2.connect(
        host="localhost",
        database="projeto_rope",
        user="postgres",
        password="#Te88510674",
        port="5432"
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


def cadastrar_sonho():
    nome = entrada_nome.get()
    idade = entrada_idade.get()
    sonho = entrada_sonho.get()
    hospital = entrada_hospital.get()
    status = entrada_status.get()

    if nome == "" or sonho == "":
        messagebox.showwarning("Atenção", "Nome e sonho são obrigatórios")
        return

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO sonhos (nome, idade, sonho, hospital, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (nome, idade, sonho, hospital, status))

    conexao.commit()
    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho cadastrado com sucesso!")
    listar_sonhos()


def pesquisar():
    termo = entrada_pesquisa.get()

    for item in tabela.get_children():
        tabela.delete(item)

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT * FROM sonhos
        WHERE nome ILIKE %s
        OR hospital ILIKE %s
        OR status ILIKE %s
    """, (f"%{termo}%", f"%{termo}%", f"%{termo}%"))

    dados = cursor.fetchall()

    for linha in dados:
        tabela.insert("", tk.END, values=linha)

    cursor.close()
    conexao.close()

def selecionar_sonho(event):
    item = tabela.selection()

    if item:
        valores = tabela.item(item, "values")

        entrada_nome.delete(0, tk.END)
        entrada_idade.delete(0, tk.END)
        entrada_sonho.delete(0, tk.END)
        entrada_hospital.delete(0, tk.END)
        entrada_status.delete(0, tk.END)

        entrada_nome.insert(0, valores[1])
        entrada_idade.insert(0, valores[3])
        entrada_sonho.insert(0, valores[5])
        entrada_hospital.insert(0, valores[7])
        entrada_status.insert(0, valores[8])

def editar_sonho():
    item = tabela.selection()

    if not item:
        messagebox.showwarning("Atenção", "Selecione um sonho para editar")
        return

    valores = tabela.item(item, "values")
    id_sonho = valores[0]

    nome = entrada_nome.get()
    idade = entrada_idade.get()
    sonho = entrada_sonho.get()
    hospital = entrada_hospital.get()
    status = entrada_status.get()

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE sonhos
        SET nome = %s,
            idade = %s,
            sonho = %s,
            hospital = %s,
            status = %s
        WHERE "ID" = %s
    """, (nome, idade, sonho, hospital, status, id_sonho))

    conexao.commit()
    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho editado com sucesso!")
    listar_sonhos()       
    
def excluir_sonho():
    item = tabela.selection()

    if not item:
        messagebox.showwarning("Atenção", "Selecione um sonho")
        return

    confirmar = messagebox.askyesno(
        "Confirmar",
        "Deseja realmente excluir este sonho?"
    )

    if not confirmar:
        return

    valores = tabela.item(item, "values")
    id_sonho = valores[0]

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        'DELETE FROM sonhos WHERE "ID" = %s',
        (id_sonho,)
    )

    conexao.commit()

    cursor.close()
    conexao.close()

    messagebox.showinfo("Sucesso", "Sonho excluído!")

    listar_sonhos()

janela = tk.Tk()
janela.title("Sistema de Sonhos - Instituto Rope")
janela.geometry("1200x700")

# Título
titulo = tk.Label(
    janela,
    text="Sistema de Gestão de Sonhos",
    font=("Arial", 18, "bold")
)
titulo.pack(pady=10)


# Frame do formulário
frame_form = tk.LabelFrame(janela, text="Cadastro / Edição", padx=10, pady=10)
frame_form.pack(fill="x", padx=20, pady=10)

tk.Label(frame_form, text="Nome").grid(row=0, column=0, sticky="w")
entrada_nome = tk.Entry(frame_form, width=40)
entrada_nome.grid(row=0, column=1, padx=10, pady=5)

tk.Label(frame_form, text="Idade").grid(row=0, column=2, sticky="w")
entrada_idade = tk.Entry(frame_form, width=15)
entrada_idade.grid(row=0, column=3, padx=10, pady=5)

tk.Label(frame_form, text="Sonho").grid(row=1, column=0, sticky="w")
entrada_sonho = tk.Entry(frame_form, width=40)
entrada_sonho.grid(row=1, column=1, padx=10, pady=5)

tk.Label(frame_form, text="Hospital").grid(row=1, column=2, sticky="w")
entrada_hospital = tk.Entry(frame_form, width=30)
entrada_hospital.grid(row=1, column=3, padx=10, pady=5)

tk.Label(frame_form, text="Status").grid(row=2, column=0, sticky="w")
entrada_status = tk.Entry(frame_form, width=25)
entrada_status.grid(row=2, column=1, padx=10, pady=5)


# Frame dos botões
frame_botoes = tk.Frame(janela)
frame_botoes.pack(fill="x", padx=20, pady=5)

tk.Button(frame_botoes, text="Cadastrar", width=15, command=cadastrar_sonho).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Editar", width=15, command=editar_sonho).pack(side="left", padx=5)
tk.Button(frame_botoes, text="Listar Todos", width=15, command=listar_sonhos).pack(side="left", padx=5)
tk.Button(
    frame_botoes,
    text="Excluir",
    width=15,
    bg="#d9534f",
    fg="white",
    command=excluir_sonho
).pack(side="left", padx=5)


# Frame de pesquisa
frame_pesquisa = tk.LabelFrame(janela, text="Pesquisa", padx=10, pady=10)
frame_pesquisa.pack(fill="x", padx=20, pady=10)

tk.Label(frame_pesquisa, text="Pesquisar por nome, hospital ou status").pack(side="left")

entrada_pesquisa = tk.Entry(frame_pesquisa, width=40)
entrada_pesquisa.pack(side="left", padx=10)

tk.Button(frame_pesquisa, text="Buscar", width=15, command=pesquisar).pack(side="left")


# Frame da tabela
frame_tabela = tk.Frame(janela)
frame_tabela.pack(fill="both", expand=True, padx=20, pady=10)

colunas = ("ID", "nome", "sexo", "idade", "data", "sonho", "diagnostico", "hospital", "status")

tabela = ttk.Treeview(frame_tabela, columns=colunas, show="headings")

for coluna in colunas:
    tabela.heading(coluna, text=coluna.upper())
    tabela.column(coluna, width=120)

tabela.pack(side="left", fill="both", expand=True)

barra_rolagem = ttk.Scrollbar(frame_tabela, orient="vertical", command=tabela.yview)
barra_rolagem.pack(side="right", fill="y")

tabela.configure(yscrollcommand=barra_rolagem.set)

tabela.bind("<<TreeviewSelect>>", selecionar_sonho)

listar_sonhos()

janela.mainloop()