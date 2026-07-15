# Painel Produtos Degust

Painel Streamlit para listar produtos por **categoria** e **unidade** das marcas do Grupo Impettus Degust:

- Espetto Carioca
- Mané
- Buteco Seu Rufino
- Bendito (Momento Bendito)

## Informações exibidas

| Campo | Descrição |
|-------|-----------|
| Marca | Filtro por marca |
| Unidade | Loja/franquia |
| Categoria | Grupo do cardápio (venda orientada) |
| Cód. Produto | Código Degust |
| Produto | Descrição |
| Preço | Valor de venda no cardápio da unidade |

## Como executar

1. Instale as dependências: `INSTALAR_DEPENDENCIAS.bat`
2. Inicie o painel: `EXECUTAR_PAINEL_PRODUTOS.bat`
3. Acesse: http://localhost:8503

## Estrutura do projeto

- `app_painel_produtos.py` — aplicação Streamlit deste painel
- `degust_produtos.py` — integração com API Degust One
- `Estrutura Base/` — Dashboard de Promoções (referência)

## API utilizada

Autenticação e endpoints da retaguarda Degust One (PRD), conforme `Estrutura Base/app_promocoes_hierarquico.py`.
