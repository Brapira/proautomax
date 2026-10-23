# Promax via HTTP

Gera e baixa os relatórios do Promax **sem navegador**: sem Edge, sem tela, sem IA, sem pywinauto.
O código repete os mesmos pedidos que o navegador faz (descobertos por captura de tráfego).

```
python main_http.py                    # roda as rotinas validadas do rotinas.json
python main_http.py rotinas_tarde.json
```

Ele usa o mesmo JSON do `main.py` (`ativo`, `destino`, `nome`, `params`) e grava no mesmo lugar.
Rotinas ainda não migradas aparecem no log e continuam no `main.py`.

> ⚠️ **O Promax aceita uma sessão por usuário.** Um novo login derruba o anterior.
> Por isso o modo HTTP usa contas próprias, diferentes da conta do robô Selenium (`PROMAX_USER`):
>
> ```
> PROMAX_HTTP_CONTAS=Robo,Isac
> PROMAX_HTTP_SENHA_Robo=...
> PROMAX_HTTP_SENHA_Isac=...
> ```
>
> Cada conta vira um trabalhador em paralelo, e as rotinas pesadas (`pesada=True`) começam primeiro.
> Não use em paralelo uma conta que alguém esteja usando no Promax: o login do robô derruba a pessoa.
> Os testes (`testar`, `inspecionar`) usam a primeira conta da lista.

**Novas tentativas:** uma rotina que falha volta para o **fim da fila** e tenta de novo depois das outras,
até `HTTP_RETENTATIVAS` vezes (padrão 2, ou seja, até 3 tentativas). "Sem dados" não tenta de novo,
porque o Promax responderia igual.

**Agendador (agente/dash):** no `agente/.env`, `SCRIPT_MANHA=main_http.py` e `SCRIPT_TARDE=main_http_tarde.py`.
O resumo no fim do log segue o mesmo formato do `main.py`, que é o que o dash lê.

## Como funciona

1. **Login:** dois envios de formulário. Na 2ª etapa, a senha já vem codificada pelo servidor.
2. **Abrir rotina:** o código do menu vira o `MenuID` com 12 dígitos (`120601` → `120601000000`).
   A tela de parâmetros (`form1`) é lida com os **valores padrão** do HTML e do JavaScript da página.
3. **Gerar:** cada rotina informa só o que muda na tela (`promax_http/rotinas.py`).
   - **Visualizar** (`opcao=1`): página do relatório, e daí o botão CSV/Salvar (`opcao=88`).
   - **Botões de download direto** (`GerarCsv`, `GerarExcel`…): `opcao` 9 ou 12.
   - Telas de cadastro enviam pelo quadro de baixo (`via_quadro=True`).
4. **Baixar:** `GET /pw/tmp/rels/<arquivo>`.

## Migrar ou ajustar uma rotina

1. Veja o que a versão Selenium (`rotinas/...`) preenche e adicione em `ROTINAS` (`promax_http/rotinas.py`):
   ```python
   "020229": RotinaHTTP("020229", lambda p: {"opcaoRel": "1"}),
   ```
   `"valor"` = campo, select ou radio · `True`/`False` = marcar/desmarcar checkbox · `None` = não enviar.
2. Teste e compare com o arquivo de produção (grava em `promax_http/saida/`, nunca no destino real):
   ```
   python -m promax_http.testar 020229
   ```
3. Se bater, deixe `validada=True` (o padrão). Só as validadas rodam no `main_http.py`.

### Quando o Promax responde "sem dados"

Algum campo que o JavaScript da tela ajusta ficou diferente. Para não ficar adivinhando:

1. Na VM, coloque `CAPTURAR_FORM=1` no `.env` e rode o `main.py` com a rotina ativa.
   O robô salva o que o navegador enviou em `promax_http/capturas/<codigo>.json`.
2. Compare, sem gerar relatório:
   ```
   python -m promax_http.testar --captura 030111
   ```
3. Passe as diferenças para os campos da rotina.

Para ver a tela crua de uma rotina: `python -m promax_http.inspecionar 030111` (salva em `promax_http/inspecao/`).
