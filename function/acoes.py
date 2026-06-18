"""
ProAutoMax - Catálogo de Ações
================================
Centraliza todos os prompts e configurações de IA em um único lugar.
Ao mudar um prompt, todas as rotinas que o usam são afetadas automaticamente.

USO NAS ROTINAS:
    from function.acoes import AGUARDAR_CSV, CLICAR_CSV
    
    analise = aguardar_estado_ia(**AGUARDAR_CSV, contexto=f"Rotina {CODIGO_ROTINA}")
    clicar_elemento_ia(**CLICAR_CSV)

ESTRUTURA DE CADA AÇÃO:
    - Ações de ESPERA  → usadas com aguardar_estado_ia()
    - Ações de CLIQUE  → usadas com clicar_elemento_ia()
    - Ações de STARTUP → usadas com fechar_popups_inicio()
"""


# ===========================================================================
# AÇÕES DE ESPERA — usadas com aguardar_estado_ia(**ACAO, contexto="...")
# ===========================================================================

# ---------------------------------------------------------------------------
# Download / Exportação
# ---------------------------------------------------------------------------

AGUARDAR_CSV = {
    # Maioria das rotinas: aguarda o botão CSV aparecer no toolbar do relatório
    "estados_esperados": ["csv_disponivel", "sem_dados", "erro"],
    "timeout": 300,
    "intervalo": 4,
    "pergunta": (
        "O relatório já foi gerado no Promax? "
        "Procure um botão pequeno com o texto 'CSV' na barra de ferramentas do relatório. "
        "Se o botão 'CSV' estiver visível e clicável na barra de ferramentas, informe OBRIGATORIAMENTE 'csv_disponivel' — mesmo que o relatório já esteja exibindo dados. "
        "Se não houver dados ou aparecer uma mensagem de 'sem registros', informe 'sem_dados'. "
        "Se houver um popup/dialog aberto, informe 'alerta'."
    ),
}

AGUARDAR_CSV_PESADO = {
    # Relatórios lentos (020304, 03013604_MES, 030237): timeout maior, intervalo maior = menos chamadas = menos custo
    "estados_esperados": ["csv_disponivel", "sem_dados", "erro"],
    "timeout": 600,
    "intervalo": 8,
    "pergunta": (
        "O relatório já foi gerado no Promax? "
        "Procure um botão pequeno com o texto 'CSV' na barra de ferramentas do relatório. "
        "Se o botão 'CSV' estiver visível e clicável na barra de ferramentas, informe OBRIGATORIAMENTE 'csv_disponivel' — mesmo que o relatório já esteja exibindo dados. "
        "Se não houver dados ou aparecer uma mensagem de 'sem registros', informe 'sem_dados'. "
        "Se houver um popup/dialog aberto, informe 'alerta'."
    ),
}

AGUARDAR_DOWNLOAD_SALVAR = {
    # Aguarda a barra de download do Edge aparecer com o botão "Salvar" (dropdown)
    # Aparece após clicar em CSV na maioria das rotinas
    "estados_esperados": ["download_salvar", "erro"],
    "timeout": 60,
    "intervalo": 2,
    "pergunta": (
        "A barra de download do Edge apareceu na parte inferior da tela? "
        "Procure um botão 'Salvar' com uma seta de dropdown ao lado. "
        "Essa barra aparece quando um arquivo está sendo baixado."
    ),
}

AGUARDAR_SALVAR_BOTAO_PAGINA = {
    # Aguarda botão "Salvar" dentro da própria página (rotina 0421 e 01250802)
    # É diferente da barra de download — fica no corpo da tela como botão de formulário
    # "pronto" incluído: a IA retorna esse estado quando vê o relatório carregado com
    # o botão Salvar visível no toolbar, o que é exatamente o sinal que precisamos
    "estados_esperados": ["pronto", "download_salvar", "csv_disponivel", "erro"],
    "timeout": 180,
    "intervalo": 4,
    "pergunta": (
        "O relatório foi gerado e o botão 'Salvar' está visível na barra de ferramentas da página? "
        "Procure um botão 'Salvar' cinza com texto preto no toolbar do relatório Promax "
        "(ao lado do botão 'CSV', que pode estar desabilitado). "
        "Se o relatório estiver carregado e o botão visível, informe 'pronto'. "
        "Se houver um popup/dialog aberto, informe 'alerta'. "
        "Se não houver dados, informe 'sem_dados'."
    ),
}


# ---------------------------------------------------------------------------
# Rotina 0105070402 — Cliente Plus (fluxo próprio com imagens específicas)
# ---------------------------------------------------------------------------

AGUARDAR_TODOS_0105070402 = {
    # Aguarda o checkbox "Todos" aparecer no formulário de filtro
    "estados_esperados": ["pronto", "erro"],
    "timeout": 30,
    "intervalo": 2,
    "pergunta": (
        "Na tela do Promax, está visível um checkbox ou opção chamada 'Todos' "
        "em um formulário de seleção de clientes? "
        "O formulário deve conter opções como 'Todos', 'Duplicados', 'AS'."
    ),
}

AGUARDAR_CSV_GERADO_0105070402 = {
    # Aguarda o popup "CSV gerado com Sucesso!" aparecer
    "estados_esperados": ["alerta", "erro"],
    "timeout": 300,
    "intervalo": 10,
    "pergunta": (
        "Apareceu um popup/dialog com a mensagem 'CSV gerado com Sucesso!' ou similar? "
        "É uma janela pequena do sistema com um botão 'OK'."
    ),
}


# ===========================================================================
# AÇÕES DE CLIQUE — usadas com clicar_elemento_ia(**ACAO)
# ===========================================================================

CLICAR_CSV = {
    # Clica no botão CSV pequeno na barra de ferramentas do relatório
    # Presente na maioria das rotinas após o relatório carregar
    "descricao": (
        "botão com o texto 'CSV' (pode aparecer como 'CSV', 'Csv' ou 'csv') "
        "na barra de ferramentas horizontal do relatório Promax. "
        "Essa barra fica logo abaixo do cabeçalho azul da página e contém os botões: "
        "Pode também aparecer na parte inferior da tela"
        "O botão CSV é pequeno, branco com borda cinza, e fica entre o 'Salvar' e o 'PDF'. "
        "NÃO é o botão 'Salvar', NÃO é a barra de download do Edge na parte inferior da tela."
    ),
    "timeout": 30,
}

CLICAR_DOWNLOAD_SALVAR = {
    # Clica no botão "Salvar" da barra de download do Edge
    # Aparece na parte inferior da janela quando um arquivo está sendo baixado
    "descricao": (
        "botão 'Salvar' na barra de download do Microsoft Edge. "
        "Fica na parte inferior da tela, tem uma seta de dropdown ao lado. "
        "Clique na parte esquerda do botão (não na seta)."
    ),
    "timeout": 30,
}

FECHAR_ALERTA = {
    # Fecha um alerta ou popup genérico que pode aparecer durante a execução (usado em várias rotinas)
    "descricao": (
        "botão de fechar ou confirmar em um popup ou alerta que apareceu na tela. "
        "Pode ser um 'X' no canto da janela, ou um botão com texto como 'OK', 'Fechar', 'Confirmar'. "
        "O popup pode estar no centro da tela e conter uma mensagem de aviso ou erro."
        "NÃO é um botão do formulário, NÃO é o botão 'Salvar' ou 'CSV'."
        "NÃO é a janela de processamento do relatório (que pode ter um texto 'Processando...' e não deve ser fechado)."
        ),
    "timeout": 30,
}

CLICAR_SALVAR_BOTAO_PAGINA = {
    # Clica no botão "Salvar" que fica dentro do corpo da página (rotina 0421)
    # Diferente da barra de download — é um botão de formulário
    "descricao": (
        "botão 'Salvar' dentro da página do relatório Promax. "
        "Não é a barra de download do Edge — é um botão que aparece no corpo da tela "
        "após o relatório ser processado."
    ),
    "timeout": 30,
}

CLICAR_BOTAO_VISUALIZAR = {
    # Clica no botão "Visualizar" que gera o relatório (usado em várias rotinas)
    "descricao": (
        "botão 'Visualizar' no formulário do Promax. "
        "É um botão cinza com o texto preto 'Visualizar', fica na parte inferior do formulário, no lado direito. "
        "NÃO é o botão 'Gerar CSV', NÃO é o botão 'Salvar', NÃO é o botão 'CSV' do toolbar."
    ),
    "timeout": 30,
}


# ---------------------------------------------------------------------------
# Rotina 0105070402 — ações específicas em sequência
# ---------------------------------------------------------------------------

CLICAR_TODOS_0105070402 = {
    "descricao": (
        "Fica em uma seção chamada 'Preferências' ao lado esquerdo da tela."
        "checkbox com o label 'Todos' no formulário de filtro do Promax. "
        "É o PRIMEIRO checkbox da lista, fica no TOPO do formulário. "
        "Tem um quadrado verde e esta escrito 'Todos' ao lado direito. "
        "NÃO é o botão 'Gerar CSV', NÃO é o checkbox 'Duplicados', NÃO é o checkbox 'AS'."
    ),
    "timeout": 20,
}

CLICAR_DUPLICADOS_0105070402 = {
    "descricao": (
        "Fica em uma seção chamada 'Preferências' ao lado esquerdo da tela."
        "checkbox com o label 'Duplicados' no formulário de filtro do Promax. "
        "É o SÉTIMO checkbox da lista. "
        "Tem um quadrado cinza vazio e esta escrito 'Duplicados' ao lado direito. "
        "NÃO é o botão 'Gerar CSV', NÃO é o checkbox 'Todos', NÃO é o checkbox 'AS'."
    ),
    "timeout": 20,
}

CLICAR_AS_0105070402 = {
    "descricao": (
        "checkbox com o label 'AS' no formulário de 'Cliente' do Promax. "
        "Fica dentro de uma seção chamada 'Cliente', no lado direito da tela. "
        "É o SEGUNDO checkbox da lista, fica ABAIXO do checkbox 'Rota'. "
        "NÃO é o botão 'Gerar CSV', NÃO é o checkbox 'Todos', NÃO é o checkbox 'Duplicados'."
    ),
    "timeout": 20,
}

CLICAR_GERAR_CSV_0105070402 = {
    "descricao": (
        "botão 'Gerar CSV' no formulário do Promax. "
        "É um botão escuro/azul com o texto branco 'Gerar CSV', fica na parte inferior do formulário, no lado direito. "
        "NÃO é um checkbox, NÃO é o botão 'Salvar', NÃO é o botão 'CSV' do toolbar."
    ),
    "timeout": 20,
}

CLICAR_OK_CSV_GERADO_0105070402 = {
    "descricao": (
        "botão 'OK' no popup 'CSV gerado com Sucesso!' do Promax. "
        "É uma janela de confirmação pequena com uma mensagem de sucesso e um botão OK."
    ),
    "timeout": 20,
}


# ===========================================================================
# STARTUP — popups imprevisíveis pós-login
# ===========================================================================

# Contexto descritivo para a IA entender o que pode aparecer na tela ao iniciar o Promax.
# Usado pela função fechar_popups_inicio() no aceitar_alertas.py
CONTEXTO_POPUPS_INICIO = (
    "O sistema Promax acabou de fazer login. "
    "Às vezes aparecem popups ou dialogs de configuração inicial que precisam ser fechados. "
    "Geralmente são janelas que aparecem no meio da tela, com um botão de fechar ou confirmar. "
    "Podem ser: \n"
    "  - Popups com filtros/dropdowns (Conta, Depto, NBZ, VBZ, Pacote) com opção 'Todos'\n"
    "  - Alertas JS do sistema (mensagens de aviso)\n"
    "  - Janelas de boas-vindas ou notificações\n"
    "  - Qualquer dialog com botão OK, Fechar, Confirmar\n"
    "Se a tela principal do Promax estiver limpa (tela toda branca, sem pop-ups visíveis ou menu lateral de navegação e menu lateral direito com campo de busca), "
    "a inicialização está concluída."
)

AGUARDAR_PROMAX_PRONTO = {
    # Usado após fechar todos os popups — confirma que o Promax está pronto para uso
    "estados_esperados": ["pronto"],
    "timeout": 30,
    "intervalo": 2,
    "pergunta": (
        "O Promax está com a tela principal carregada e sem nenhum popup aberto? "
        "A tela principal deve mostrar o menu lateral com as opções do sistema "
        "e um campo de atalho/busca de rotinas."
    ),
}