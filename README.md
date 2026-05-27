# DreamCare Management System

Sistema completo de gestão e análise de sonhos de pacientes desenvolvido com Python, Tkinter, PostgreSQL e Streamlit, criado com foco em organização, automação, análise de dados e impacto social.

O projeto permite cadastrar, visualizar, editar, pesquisar e excluir registros de sonhos de pacientes em tratamento de saúde, oferecendo uma interface gráfica integrada a banco de dados e módulos analíticos.

Além do CRUD completo, o sistema também realiza integração com planilhas Excel, tratamento de dados, geração de métricas e dashboards interativos para análise estratégica das informações.



# Funcionalidades

## Gestão de Dados

* Cadastro de pacientes e sonhos
* Edição e exclusão de registros
* Pesquisa dinâmica por nome, hospital e status
* Listagem de registros em tabela
* Integração com PostgreSQL
* Importação de dados via Excel
* Tratamento e padronização de dados



# Módulo Analítico

O sistema possui um módulo de análise de dados desenvolvido para transformar informações em métricas e insights visuais.

## Métricas disponíveis

* Total de sonhos cadastrados
* Ano com maior número de sonhos realizados
* Distribuição por sexo
* Média de idade dos pacientes
* Faixa etária mais atendida
* Sonhos mais frequentes
* Enfermidades mais recorrentes
* Contatos que mais idealizaram sonhos



# Dashboard Interativo

Foi desenvolvido um dashboard analítico utilizando Streamlit e Plotly, permitindo:

* Navegação através de menu lateral
* Visualização de gráficos dinâmicos
* Exploração da base de dados em tempo real
* Análise estatística dos registros
* Organização visual das métricas

O dashboard possibilita uma análise mais estratégica e intuitiva dos dados do projeto.



# Tecnologias Utilizadas

* Python
* Tkinter
* PostgreSQL
* Pandas
* Streamlit
* Plotly
* Matplotlib
* SQLAlchemy
* Psycopg2
* OpenPyXL



# Estrutura do Projeto

```bash
DreamCare_Management_System/
│
├── app_sonhos.py
├── dashboard.py
├── metricas.py
├── limpeza.py
├── importar_bd.py
├── postgres_import.py
├── teste_sql.py
│
├── README.md
├── .gitignore
│
└── arquivos auxiliares
```


# Objetivo

Criar uma plataforma de gestão de dados com propósito social, unindo:

* desenvolvimento de software,
* banco de dados,
* análise de dados,
* visualização de métricas,
* automação de processos.

O projeto nasceu da necessidade de automatizar cadastros que anteriormente eram feitos em planilhas Excel, tornando o processo mais organizado, seguro, escalável e preparado para futuras análises e dashboards.



# Diferenciais do Projeto

* CRUD completo integrado ao PostgreSQL
* Pipeline de limpeza e tratamento de dados
* Dashboard analítico interativo
* Visualização de métricas em tempo real
* Estrutura preparada para BI e automações
* Projeto aplicado a um caso real com impacto social
* Integração entre sistema desktop, banco de dados e analytics



# Possíveis Evoluções

* Sistema de login e permissões
* Hospedagem em nuvem
* Dashboard online
* Geração automática de relatórios PDF
* Integração com APIs
* Inteligência Artificial para categorização de sonhos
* Automação de cadastros e notificações

## Como executar o dashboard


```bash
streamlit run dashboard.py
```

## Dashboard 1

![Dashboard](imagens/dashboards%20(1).png)

---

## Dashboard 2

![Dashboard](imagens/dashboards%20(2).png)

---

## Dashboard 3

![Dashboard](imagens/dashboards%20(3).png)

---

## Dashboard 4

![Dashboard](imagens/dashboards%20(4).png)

---

## Dashboard 5

![Dashboard](imagens/dashboards%20(5).png)

---

## Dashboard 6

![Dashboard](imagens/dashboards%20(6).png)
