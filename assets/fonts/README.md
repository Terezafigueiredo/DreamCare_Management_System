# Fontes do Vídeo Institucional ROPE

## Montserrat-SemiBold.ttf

- **Fonte:** Montserrat, peso SemiBold.
- **Origem:** repositório oficial do designer, https://github.com/JulietaUla/Montserrat
  (o mesmo arquivo fonte distribuído pelo Google Fonts em
  https://fonts.google.com/specimen/Montserrat).
- **Licença:** SIL Open Font License, Version 1.1 (texto completo em `OFL.txt`
  nesta mesma pasta). A OFL permite usar, estudar, modificar e **redistribuir**
  a fonte livremente — inclusive embutida em projetos de software — desde que
  não seja vendida isoladamente e que o aviso de licença acompanhe o arquivo.
- **Uso no projeto:** referenciada por caminho absoluto em
  `api/video_institucional_render.py` (opção `fontfile` do filtro `drawtext`
  do FFmpeg) para desenhar as palavras da narrativa do vídeo institucional.
  Não depende de nenhuma fonte instalada no sistema operacional.
