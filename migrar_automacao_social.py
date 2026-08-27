from criar_tabela_producao import conectar_banco


def main():
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            ALTER TABLE producao_conteudo
                ADD COLUMN IF NOT EXISTS edicao_status VARCHAR(30) DEFAULT 'NAO_INICIADA',
                ADD COLUMN IF NOT EXISTS video_editado_path TEXT,
                ADD COLUMN IF NOT EXISTS video_publico_url TEXT,
                ADD COLUMN IF NOT EXISTS legenda_instagram TEXT,
                ADD COLUMN IF NOT EXISTS erro_automacao TEXT,
                ADD COLUMN IF NOT EXISTS instagram_media_id TEXT,
                ADD COLUMN IF NOT EXISTS data_autorizacao TIMESTAMP;
        """)
        conexao.commit()
        print("Automação de edição e Instagram preparada no banco.")
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


if __name__ == "__main__":
    main()
