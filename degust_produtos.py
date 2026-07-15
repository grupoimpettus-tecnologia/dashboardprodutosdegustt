"""
Camada de dados do Painel Produtos Degust.
Consulta produtos por categoria/unidade via API Degust One (PRD).
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

DEGUST_API_BASE = "https://lx-degust-api-integracao-prd.azurewebsites.net"

CREDENCIAIS = {
    "usuario": "06266555794",
    "senha": "250913",
}

MARCAS_CONFIG = {
    "Espetto": {
        "codfranqueador": 3078,
        "cor": "#4ECDC4",
        "nome_exibicao": "Espetto Carioca",
    },
    "Mané": {
        "codfranqueador": 1428,
        "cor": "#95E1D3",
        "nome_exibicao": "Mané",
    },
    "Buteco Seu Rufino": {
        "codfranqueador": 3081,
        "cor": "#FFA500",
        "nome_exibicao": "Buteco Seu Rufino",
    },
    "Bendito": {
        "codfranqueador": 3082,
        "cor": "#FF6B6B",
        "nome_exibicao": "Momento Bendito",
    },
}

_URL_AUTH = "/api/usuario/autenticar"
_URL_LOJAS = "/api/loja/listarLojasFranquia"
_URL_LOJA_DETALHE = "/api/loja/loja"
_URL_CARDAPIO = "/api/produto/relacao-cardapio-produto"
_URL_VO_PRODUTOS = "/api/venda-orientada/consultar-produto-por-grupo-venda-orientada"

_VO_SCAN_MAX = 400
_VO_MIN_PRODUTOS = 80
_VO_OVERLAP_MIN = 0.25
_VO_MIN_INTERSECAO = 120
_JANELA_SECUNDARIOS_CARDAPIO = 20


def _extrair_lista(dados: Any) -> list:
    if dados is None:
        return []
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        for chave in ("data", "produtos", "itens", "items", "resultado", "content"):
            val = dados.get(chave)
            if isinstance(val, list):
                return val
        return [dados]
    return []


def _interpretar_ativo(val) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().upper()
    if not s:
        return None
    if s in ("S", "SIM", "1", "T", "TRUE", "Y", "YES", "ATIVO", "ATIVA"):
        return True
    if s in ("N", "NAO", "NÃO", "0", "F", "FALSE", "INATIVO", "INATIVA"):
        return False
    if "INATIV" in s:
        return False
    if "ATIV" in s:
        return True
    return None


def _loja_ativa_listagem(loja: dict) -> bool:
    for key in ("situacaoLoja", "situacao"):
        val = loja.get(key)
        if val is None:
            continue
        if "INATIV" in str(val).strip().upper():
            return False
    return True


def _normalizar_nome(texto: str) -> str:
    return str(texto or "").strip().upper()


def _config_casa_loja(config_nome: str, nome_loja: str) -> bool:
    cfg = _normalizar_nome(config_nome).replace(" ", "")
    loja = _normalizar_nome(nome_loja).replace(" ", "")
    if not cfg or not loja:
        return False
    return loja in cfg or cfg.endswith(loja)


def autenticar(codfranqueador: int, session: requests.Session | None = None) -> str | None:
    url = f"{DEGUST_API_BASE.rstrip('/')}{_URL_AUTH}"
    body = {
        "usuario": CREDENCIAIS["usuario"],
        "senha": CREDENCIAIS["senha"],
        "codigoFranqueador": int(codfranqueador),
    }
    http = session or requests
    try:
        resp = http.post(url, json=body, timeout=15)
        if resp.status_code == 200:
            return resp.json()["acesso"]["token"]
    except Exception:
        pass
    return None


def _consultar_cadastro_loja(
    session: requests.Session, token: str, codfranqueador: int, codigo_loja: int
) -> dict | None:
    url = f"{DEGUST_API_BASE.rstrip('/')}{_URL_LOJA_DETALHE}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = session.get(
            url,
            params={"CodigoFranqueador": int(codfranqueador), "CodigoLoja": int(codigo_loja)},
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        dg = data.get("dadosGerais") or {}
        cfg = data.get("configuracaoVenda") or {}
        return {
            "ativo": _interpretar_ativo(dg.get("ativo") if isinstance(dg, dict) else None),
            "config_vo": str(cfg.get("configuracaoVendaOrientada") or "").strip(),
        }
    except Exception:
        return None


def listar_lojas(
    token: str, codfranqueador: int, session: requests.Session | None = None
) -> list[dict]:
    url = f"{DEGUST_API_BASE.rstrip('/')}{_URL_LOJAS}"
    params = {"codigoFranquia": int(codfranqueador)}
    headers = {"Authorization": f"Bearer {token}"}
    http = session or requests
    try:
        resp = http.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        lojas = resp.json()
        if not isinstance(lojas, list):
            return []
    except Exception:
        return []

    ativas: list[dict] = []
    for loja in lojas:
        try:
            cod = int(loja.get("codigoLoja"))
        except (TypeError, ValueError):
            continue
        if cod == 999:
            continue
        cad = _consultar_cadastro_loja(http, token, codfranqueador, cod)
        if cad and cad.get("ativo") is False:
            continue
        if cad and cad.get("ativo") is True:
            if cad.get("config_vo"):
                loja["configuracaoVendaOrientada"] = cad["config_vo"]
            ativas.append(loja)
            continue
        if _loja_ativa_listagem(loja):
            if cad and cad.get("config_vo"):
                loja["configuracaoVendaOrientada"] = cad["config_vo"]
            ativas.append(loja)
    return ativas


def obter_cardapio_detalhado_loja(
    session: requests.Session, token: str, codfranqueador: int, codigo_loja: int
) -> list[dict]:
    url = f"{DEGUST_API_BASE.rstrip('/')}{_URL_CARDAPIO}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = session.get(
            url,
            params={"CodigoFranqueador": int(codfranqueador), "CodigoLoja": int(codigo_loja)},
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        return [
            item
            for item in _extrair_lista(resp.json())
            if isinstance(item, dict) and item.get("codigoProduto") is not None
        ]
    except Exception:
        return []


def obter_cardapio_loja(
    session: requests.Session, token: str, codfranqueador: int, codigo_loja: int
) -> dict[int, float]:
    precos: dict[int, float] = {}
    for item in obter_cardapio_detalhado_loja(session, token, codfranqueador, codigo_loja):
        cod = item.get("codigoProduto")
        if cod is None:
            continue
        try:
            cod_int = int(cod)
            precos[cod_int] = float(item.get("valorVenda") or 0)
        except (TypeError, ValueError):
            continue
    return precos


def _exibir_degust_ativo(val) -> bool:
    """Campo 'exibir' da venda orientada — Sim = visível no Degust."""
    s = str(val or "").strip().upper()
    if not s:
        return True
    if s in ("N", "NAO", "NÃO", "0", "F", "FALSE", "NAO EXIBIR", "NÃO EXIBIR"):
        return False
    return s in ("S", "SIM", "1", "T", "TRUE", "Y", "YES")


def _produto_visivel_vo(item: dict) -> bool:
    return _exibir_degust_ativo(item.get("exibir"))


def _categoria_vo(item: dict) -> str:
    return str(item.get("grupoDescricao") or item.get("descricaoGrupo") or "Sem categoria").strip()


def _descricao_vo(item: dict) -> str:
    return str(item.get("produtoDescricao") or item.get("descricaoProduto") or "N/A").strip()


def _categorias_visiveis_vo(produtos_vo: list[dict]) -> set[str]:
    """Categorias com ao menos um produto com exibir = Sim no Degust."""
    por_categoria: dict[str, list[bool]] = {}
    for item in produtos_vo:
        cat = _categoria_vo(item)
        por_categoria.setdefault(cat, []).append(_produto_visivel_vo(item))
    return {cat for cat, flags in por_categoria.items() if any(flags)}


def _detectar_secundarios_cardapio(cardapio_itens: list[dict]) -> tuple[dict[int, list[int]], set[int]]:
    """
    Identifica produtos referência (preço zero) com SKUs secundários consecutivos no cardápio.
    Retorna (mapa_pai -> [filhos], conjunto_de_codigos_secundarios).
    """
    pais: dict[int, list[int]] = {}
    secundarios: set[int] = set()

    for idx, item in enumerate(cardapio_itens):
        try:
            cod_pai = int(item["codigoProduto"])
            preco_pai = float(item.get("valorVenda") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        if preco_pai > 0:
            continue

        filhos: list[int] = []
        for j in range(idx + 1, min(idx + 1 + _JANELA_SECUNDARIOS_CARDAPIO, len(cardapio_itens))):
            filho_item = cardapio_itens[j]
            try:
                cod_filho = int(filho_item["codigoProduto"])
                preco_filho = float(filho_item.get("valorVenda") or 0)
            except (TypeError, ValueError, KeyError):
                break
            if preco_filho <= 0:
                break
            filhos.append(cod_filho)
            secundarios.add(cod_filho)

        if filhos:
            pais[cod_pai] = filhos

    return pais, secundarios


def _mapa_vo_por_codigo(produtos_vo: list[dict]) -> dict[int, dict]:
    mapa: dict[int, dict] = {}
    for item in produtos_vo:
        cod = item.get("produto")
        if cod is None:
            continue
        try:
            cod_int = int(cod)
        except (TypeError, ValueError):
            continue
        if cod_int not in mapa:
            mapa[cod_int] = item
    return mapa


def _consultar_vo_produtos(
    session: requests.Session, token: str, codfranqueador: int, codigo_vo: int
) -> list[dict]:
    url = f"{DEGUST_API_BASE.rstrip('/')}{_URL_VO_PRODUTOS}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = session.post(
            url,
            json={"codigoFranquia": int(codfranqueador), "vendaOrientada": int(codigo_vo)},
            headers=headers,
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        return [item for item in _extrair_lista(resp.json()) if isinstance(item, dict)]
    except Exception:
        return []


def construir_indice_vo_franquia(
    session: requests.Session, token: str, codfranqueador: int, max_vo: int = _VO_SCAN_MAX
) -> dict[int, dict]:
    """
    Varre códigos de venda orientada e indexa produtos por VO.
    Retorno: {codigo_vo: {"produtos": [...], "ids": frozenset[int]}}
    """
    indice: dict[int, dict] = {}

    def _probe(codigo_vo: int):
        itens = _consultar_vo_produtos(session, token, codfranqueador, codigo_vo)
        if len(itens) < _VO_MIN_PRODUTOS:
            return codigo_vo, None
        try:
            ids = frozenset(int(it["produto"]) for it in itens if it.get("produto") is not None)
        except (TypeError, ValueError):
            ids = frozenset()
        if not ids:
            return codigo_vo, None
        return codigo_vo, {"produtos": itens, "ids": ids}

    workers = min(8, max(1, max_vo))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for codigo_vo, payload in executor.map(_probe, range(1, max_vo + 1)):
            if payload:
                indice[int(codigo_vo)] = payload
    return indice


def resolver_vo_loja(
    cardapio_ids: set[int],
    indice_vo: dict[int, dict],
    config_nome: str = "",
    nome_loja: str = "",
) -> int | None:
    if not cardapio_ids or not indice_vo:
        return None

    melhor_vo = None
    melhor_score = -1.0
    card = set(cardapio_ids)

    for codigo_vo, payload in indice_vo.items():
        ids = payload["ids"]
        if not ids:
            continue
        inter = len(card & ids)
        if inter < _VO_MIN_INTERSECAO:
            continue
        overlap = inter / len(card)
        if overlap < _VO_OVERLAP_MIN:
            continue
        bonus = 0.05 if config_nome and _config_casa_loja(config_nome, nome_loja) else 0.0
        score = overlap + bonus + (inter / 10000.0)
        if score > melhor_score:
            melhor_score = score
            melhor_vo = codigo_vo

    return melhor_vo


def mapear_vo_por_configuracao(
    lojas: list[dict],
    indice_vo: dict[int, dict],
    mapa_cardapio: dict[int, set[int]],
) -> dict[str, int]:
    """
    Associa configuracaoVendaOrientada -> codigo VO (1 VO por config, como no dashboard de promoções).
    """
    config_lojas: dict[str, list[dict]] = {}
    for loja in lojas:
        config = str(loja.get("configuracaoVendaOrientada") or "").strip()
        if not config:
            continue
        try:
            cod_loja = int(loja["codigoLoja"])
        except (TypeError, ValueError):
            continue
        card = mapa_cardapio.get(cod_loja)
        if not card:
            continue
        config_lojas.setdefault(config, []).append(
            {
                "codigo_loja": cod_loja,
                "nome_loja": loja.get("nomeLoja") or "",
                "cardapio": card,
            }
        )

    if not config_lojas or not indice_vo:
        return {}

    edges: list[tuple] = []
    for config_nome, entries in config_lojas.items():
        for codigo_vo, payload in indice_vo.items():
            ids = payload["ids"]
            if len(ids) < _VO_MIN_PRODUTOS:
                continue
            overlaps = []
            bonus_nome = 0.0
            for entry in entries:
                card = entry["cardapio"]
                if not card:
                    continue
                overlaps.append(len(ids & card) / len(card))
                if _config_casa_loja(config_nome, entry["nome_loja"]):
                    bonus_nome = 0.05
            if not overlaps:
                continue
            overlap = max(overlaps)
            if overlap < _VO_OVERLAP_MIN:
                continue
            miss = min(len(ids - entry["cardapio"]) for entry in entries)
            score = overlap + bonus_nome + (0.06 * miss)
            edges.append((score, overlap, len(ids), codigo_vo, config_nome))

    edges.sort(reverse=True)
    mapa_config: dict[str, int] = {}
    used_vo: set[int] = set()
    for score, overlap, _n, codigo_vo, config_nome in edges:
        if config_nome in mapa_config or codigo_vo in used_vo:
            continue
        mapa_config[config_nome] = int(codigo_vo)
        used_vo.add(int(codigo_vo))

    return mapa_config


def _formatar_preco(valor: float | None) -> str:
    if valor is None:
        return "N/A"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "N/A"


def _ordenar_linhas_hierarquicas(
    linhas: list[dict], pais_secundarios: dict[int, list[int]]
) -> list[dict]:
    """Agrupa cada produto principal imediatamente seguido dos seus secundários."""
    if not linhas:
        return []

    filhos_map: dict[int, list[dict]] = {}
    for row in linhas:
        if row.get("tipo") != "Secundário":
            continue
        try:
            pai = int(row.get("codigoPrincipal") or 0)
        except (TypeError, ValueError):
            continue
        if pai:
            filhos_map.setdefault(pai, []).append(row)

    for pai, filhos in filhos_map.items():
        ordem = pais_secundarios.get(pai) or []
        filhos_map[pai] = sorted(
            filhos,
            key=lambda r: (
                ordem.index(r["codigoProduto"]) if r["codigoProduto"] in ordem else 99999,
                r["codigoProduto"],
            ),
        )

    def _chave_grupo(row: dict) -> tuple:
        return (
            str(row.get("marca") or ""),
            int(row.get("codigoLoja") or 0),
            str(row.get("unidade") or ""),
            str(row.get("categoria") or ""),
        )

    grupos: dict[tuple, list[dict]] = {}
    for row in linhas:
        grupos.setdefault(_chave_grupo(row), []).append(row)

    ordem_pais = list(pais_secundarios.keys())
    resultado: list[dict] = []

    for chave in sorted(grupos.keys()):
        grupo = grupos[chave]
        vistos: set[int] = set()

        principais = [r for r in grupo if r.get("tipo") == "Principal"]
        principais.sort(
            key=lambda r: (
                ordem_pais.index(r["codigoProduto"]) if r["codigoProduto"] in ordem_pais else 99999,
                r["codigoProduto"],
            )
        )

        for principal in principais:
            cod = principal["codigoProduto"]
            if cod in vistos:
                continue
            resultado.append(principal)
            vistos.add(cod)
            for filho in filhos_map.get(cod, []):
                fc = filho["codigoProduto"]
                if fc not in vistos:
                    resultado.append(filho)
                    vistos.add(fc)

        soltos = [r for r in grupo if r.get("tipo") == "Produto"]
        soltos.sort(key=lambda r: (str(r.get("produto") or ""), r["codigoProduto"]))
        for row in soltos:
            cod = row["codigoProduto"]
            if cod not in vistos:
                resultado.append(row)
                vistos.add(cod)

        for row in grupo:
            if row.get("tipo") == "Secundário" and row["codigoProduto"] not in vistos:
                resultado.append(row)
                vistos.add(row["codigoProduto"])

    return resultado


def _aplicar_formato_hierarquico(linhas: list[dict]) -> list[dict]:
    """Formata nomes para exibição em árvore (principal → secundários)."""
    formatadas: list[dict] = []
    for row in linhas:
        item = dict(row)
        tipo = str(item.get("tipo") or "Produto")
        nome = str(item.get("produto") or "")
        if tipo == "Principal":
            item["produtoExibicao"] = f"- {nome}"
            item["nivel"] = 0
        elif tipo == "Secundário":
            item["produtoExibicao"] = f"      ──────► {nome}"
            item["nivel"] = 1
        else:
            item["produtoExibicao"] = nome
            item["nivel"] = 0
        formatadas.append(item)
    return formatadas


def _criar_linha(
    marca: str,
    codigo_loja: int,
    nome_loja: str,
    categoria: str,
    cod_int: int,
    produto: str,
    preco: float | None,
    tipo: str,
    codigo_principal: int | None = None,
) -> dict:
    return {
        "marca": marca,
        "codigoLoja": codigo_loja,
        "unidade": nome_loja,
        "categoria": categoria,
        "codigoProduto": cod_int,
        "produto": produto,
        "preco": preco if preco is not None else 0.0,
        "precoFormatado": _formatar_preco(preco),
        "tipo": tipo,
        "codigoPrincipal": codigo_principal if codigo_principal is not None else "",
    }


def montar_linhas_loja(
    loja: dict,
    indice_vo: dict[int, dict],
    precos: dict[int, float],
    marca: str,
    codigo_vo: int | None,
    cardapio_itens: list[dict] | None = None,
) -> list[dict]:
    if codigo_vo is None:
        return []

    payload = indice_vo.get(codigo_vo)
    if not payload:
        return []

    codigo_loja = int(loja["codigoLoja"])
    nome_loja = loja.get("nomeLoja") or "N/A"
    produtos_vo = payload["produtos"]

    # Fonte da verdade = grupo de venda orientada do Degust.
    # O cardápio da loja entra APENAS como preço; produto do grupo sem preço
    # aparece com R$ 0,00. Não inferimos hierarquia (o VO não expõe pai/filho).
    linhas: list[dict] = []
    vistos: set[int] = set()

    for item in produtos_vo:
        cod = item.get("produto")
        try:
            cod_int = int(cod)
        except (TypeError, ValueError):
            continue
        if cod_int in vistos:
            continue
        if not _produto_visivel_vo(item):  # respeita "exibir = Sim" no Degust
            continue
        vistos.add(cod_int)

        preco = precos.get(cod_int, 0.0)  # sem preço no cardápio -> R$ 0,00
        linha = _criar_linha(
            marca,
            codigo_loja,
            nome_loja,
            _categoria_vo(item),
            cod_int,
            _descricao_vo(item),
            preco,
            "Produto",
        )
        linha["produtoExibicao"] = linha["produto"]
        linha["nivel"] = 0
        linhas.append(linha)

    # Ordena por categoria e descrição, espelhando a tela do Degust.
    linhas.sort(
        key=lambda r: (
            str(r.get("categoria") or ""),
            str(r.get("produto") or ""),
            r["codigoProduto"],
        )
    )
    return linhas


def _processar_loja(
    loja: dict,
    token: str,
    codfranqueador: int,
    indice_vo: dict[int, dict],
    marca: str,
    precos: dict[int, float] | None = None,
    cardapio_itens: list[dict] | None = None,
) -> list[dict]:
    thread_local = threading.local()

    def _session() -> requests.Session:
        if not hasattr(thread_local, "session"):
            thread_local.session = requests.Session()
        return thread_local.session

    session = _session()
    codigo_loja = int(loja["codigoLoja"])

    if precos is None or cardapio_itens is None:
        cardapio_itens = obter_cardapio_detalhado_loja(session, token, codfranqueador, codigo_loja)
        precos = {
            int(item["codigoProduto"]): float(item.get("valorVenda") or 0)
            for item in cardapio_itens
            if item.get("codigoProduto") is not None
        }
    if not precos:
        return []

    config_nome = loja.get("configuracaoVendaOrientada") or ""
    if not config_nome:
        cad = _consultar_cadastro_loja(session, token, codfranqueador, codigo_loja)
        config_nome = (cad or {}).get("config_vo") or ""

    codigo_vo = resolver_vo_loja(
        set(precos.keys()),
        indice_vo,
        config_nome=config_nome,
        nome_loja=loja.get("nomeLoja") or "",
    )

    return montar_linhas_loja(
        loja, indice_vo, precos, marca, codigo_vo, cardapio_itens=cardapio_itens
    )


def carregar_produtos_marca(marca: str) -> list[dict]:
    config = MARCAS_CONFIG.get(marca)
    if not config:
        return []

    codfranqueador = int(config["codfranqueador"])
    with requests.Session() as session:
        token = autenticar(codfranqueador, session)
        if not token:
            return []

        lojas = listar_lojas(token, codfranqueador, session)
        if not lojas:
            return []

        mapa_cardapio: dict[int, set[int]] = {}
        mapa_precos: dict[int, dict[int, float]] = {}
        mapa_cardapio_itens: dict[int, list[dict]] = {}
        for loja in lojas:
            codigo_loja = int(loja["codigoLoja"])
            itens = obter_cardapio_detalhado_loja(session, token, codfranqueador, codigo_loja)
            if not itens:
                continue
            precos = {
                int(item["codigoProduto"]): float(item.get("valorVenda") or 0)
                for item in itens
                if item.get("codigoProduto") is not None
            }
            if precos:
                mapa_cardapio[codigo_loja] = set(precos.keys())
                mapa_precos[codigo_loja] = precos
                mapa_cardapio_itens[codigo_loja] = itens

        indice_vo = construir_indice_vo_franquia(session, token, codfranqueador)
        if not indice_vo:
            return []

        todas_linhas: list[dict] = []
        workers = min(8, max(1, len(lojas)))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futuros = {
                executor.submit(
                    _processar_loja,
                    loja,
                    token,
                    codfranqueador,
                    indice_vo,
                    marca,
                    mapa_precos.get(int(loja["codigoLoja"])),
                    mapa_cardapio_itens.get(int(loja["codigoLoja"])),
                ): loja
                for loja in lojas
                if int(loja["codigoLoja"]) in mapa_precos
            }
            for futuro in as_completed(futuros):
                try:
                    linhas = futuro.result()
                    if linhas:
                        todas_linhas.extend(linhas)
                except Exception:
                    continue

    return todas_linhas
