#!/usr/bin/env python3
"""
enem_erros.py - % de erro por questão do ENEM (prova AZUL, aplicação regular).

Rode um ano por vez:
  python enem_erros.py --ano 2024 --itens ITENS_PROVA_2024.csv --resultados RESULTADOS_2024.csv

Depois de rodar todos os anos, junte tudo numa tabela só:
  python enem_erros.py --juntar

Opcional: --limiar 75  (% mínimo de erro para a questão entrar na lista de "mais erradas")

Requisitos: pip install pandas numpy
"""
import argparse
import glob
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

AREAS = ("LC", "CH", "CN", "MT")   # Linguagens, Humanas, Natureza e Matemática
ENC = "latin-1"        # os arquivos do INEP vêm em latin-1
CHUNK = 200_000        # blocos de linhas lidas por vez (baixe se faltar memória)
N_ITENS = 45           # questões que cada participante responde por área
N_LANG = 5             # questões de língua estrangeira (inglês OU espanhol) dentro de LC
LEN_LC_ANTIGO = N_ITENS + N_LANG   # em vários anos a resposta de LC vem com 50 caracteres
MIN_PARTICIPANTES = 1000           # abaixo disso a área do ano não é incluída (evita lixo)
LIMIAR_PADRAO = 75.0
BRANCO, DUPLA = ord("."), ord("*")


# Dia da prova de cada área. Até 2016: 1º dia = Humanas + Natureza, 2º dia = Linguagens + Matemática.
# De 2017 em diante: 1º dia = Linguagens + Humanas, 2º dia = Natureza + Matemática.
def dia_da_area(area, ano):
    if ano <= 2016:
        return 1 if area in ("CH", "CN") else 2
    return 1 if area in ("LC", "CH") else 2


# Carrega e limpa o arquivo de metadados das questões (ITENS_PROVA)
# Filtra as colunas obrigatórias, remove espaços em branco dos textos,
# converte a posição da questão para inteiro e trata os parâmetros
# do TRI trocando a vírgula por ponto
def ler_itens(caminho):
    df = pd.read_csv(caminho, sep=";", encoding=ENC, dtype=str)
    df.columns = df.columns.str.strip()
    obrig = ["CO_POSICAO", "SG_AREA", "CO_ITEM", "TX_GABARITO",
             "CO_HABILIDADE", "TX_COR", "CO_PROVA"]
    faltam = [c for c in obrig if c not in df.columns]
    if faltam:
        sys.exit(f"ITENS_PROVA sem as colunas: {faltam}\nColunas encontradas: {list(df.columns)}")
    if "TP_LINGUA" not in df.columns:
        df["TP_LINGUA"] = np.nan
    df["TX_COR"] = df["TX_COR"].str.strip().str.upper()
    df["CO_PROVA"] = df["CO_PROVA"].str.strip()
    df["CO_POSICAO"] = df["CO_POSICAO"].astype(int)
    for c in ("NU_PARAM_A", "NU_PARAM_B", "IN_ITEM_ABAN"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce")
    return df


# Identifica o idioma da questão na prova de Linguagens e Códigos
# Retorna None para questões comuns, 0 para Inglês e 1 para Espanhol
def lingua_do_item(valor):
    """None = item comum às duas línguas; 0 = inglês; 1 = espanhol."""
    if pd.isna(valor) or str(valor).strip() == "":
        return None
    return int(float(valor))


# Filtra as questões da prova de cor AZUL e monta os gabaritos de referência.
# Para cada questão calcula um índice lógico (0 a 44) que independe de como o INEP numerou
# as posições naquele ano:
#   - CN, CH, MT: índice = posição - menor posição da área;
#   - LC: as 5 questões de língua (inglês e espanhol) ocupam os índices 0 a 4 de cada idioma
#         e as 40 comuns ocupam 5 a 44 (funciona mesmo que a numeração das posições mude de ano).
def montar_chaves(itens):
    """(área, prova) -> gabarito por língua [2, 45] e índice lógico de cada linha do ITENS."""
    chaves = {}
    azul = itens[itens["TX_COR"] == "AZUL"]
    for (area, prova), g in azul.groupby(["SG_AREA", "CO_PROVA"]):
        if area not in AREAS:
            continue
        g = g.sort_values("CO_POSICAO")
        lg = g["TP_LINGUA"].map(lingua_do_item)
        idx = {}
        if area == "LC":
            n_ing, n_esp, n_com = int((lg == 0).sum()), int((lg == 1).sum()), int(lg.isna().sum())
            if (n_ing, n_esp, n_com) != (N_LANG, N_LANG, N_ITENS - N_LANG):
                print(f"  aviso: LC/{prova} com estrutura inesperada (inglês={n_ing}, espanhol={n_esp}, "
                      f"comuns={n_com}; esperado 5/5/40); ignorada")
                continue
            cont = {0: 0, 1: 0, None: 0}
            for ind, l in zip(g.index, lg):
                if pd.isna(l):
                    idx[ind] = N_LANG + cont[None]
                    cont[None] += 1
                else:
                    idx[ind] = cont[int(l)]
                    cont[int(l)] += 1
        else:
            pos = g["CO_POSICAO"]
            pos0 = pos.min()
            if pos.nunique() != N_ITENS or (pos - pos0).max() != N_ITENS - 1:
                print(f"  aviso: {area}/{prova} não tem {N_ITENS} posições distintas; ignorada")
                continue
            idx = {ind: int(p - pos0) for ind, p in zip(g.index, pos)}
        chave = np.zeros((2, N_ITENS), dtype=np.uint8)   # [língua, índice]; 0 = item inválido
        for ind, gab, l in zip(g.index, g["TX_GABARITO"], lg):
            gab = str(gab).strip().upper()
            cod = ord(gab) if gab in ("A", "B", "C", "D", "E") else 0
            for x in ((0, 1) if pd.isna(l) else (int(l),)):
                chave[x, idx[ind]] = cod
        chaves[(area, prova)] = {"chave": chave, "idx": idx}
    return chaves


# Faz um teste de integridade comparando o gabarito oficial
# com o gabarito registrado para um participante real, emitindo um alerta
# caso haja divergência nos dados
def conferir(area, prova, chave0, gab_participante):
    """Compara o gabarito do ITENS_PROVA com o que vem na linha de um participante."""
    if len(gab_participante) == 0:
        return
    gab = gab_participante.iloc[0]
    ref = [chr(c) if c else "?" for c in chave0]
    bate = len(gab) == N_ITENS and all(
        r == g or r == "?" or g not in "ABCDE" for r, g in zip(ref, gab))
    print(f"  conferência {area}/{prova}:",
          "OK, gabarito bate com o do participante" if bate
          else "ATENÇÃO: gabarito NÃO bate, não confie neste resultado")


def acumular(a, chave, x, g):
    """Soma participantes, acertos e brancos/duplas de uma matriz x (n, 45) do grupo de língua g."""
    a["n"][g] += len(x)
    a["acerto"][g] += (x == chave[g]).sum(axis=0)
    a["branco"][g] += ((x == BRANCO) | (x == DUPLA)).sum(axis=0)


# Processa os microdados de resultados em blocos -> economizar memória
# Para cada participante, extrai a string de respostas e valida o tamanho.
# Em LC, quando a string tem 50 caracteres (inglês 0-4, espanhol 5-9, comuns 10-49),
# fica só com o bloco da língua que o participante escolheu (TP_LINGUA) + as 40 comuns.
# Usa operações vetorizadas do NumPy para contar: o total de respondentes (n), a soma de acertos
# e a soma de respostas em branco/duplas
def processar(itens, caminho_resultados):
    chaves = montar_chaves(itens)
    if not chaves:
        sys.exit("Nenhuma prova AZUL utilizável encontrada no ITENS_PROVA.")
    acc = {k: {"n": np.zeros((2, N_ITENS)), "acerto": np.zeros((2, N_ITENS)),
               "branco": np.zeros((2, N_ITENS)), "conferido": False,
               "lang_check": np.zeros((2, 3))} for k in chaves}

    usecols = ["TP_LINGUA"]
    for a in AREAS:
        usecols += [f"TP_PRESENCA_{a}", f"CO_PROVA_{a}", f"TX_RESPOSTAS_{a}"]
    usecols += [f"TX_GABARITO_{a}" for a in ("CN", "CH", "MT")]
    cab = pd.read_csv(caminho_resultados, sep=";", encoding=ENC, nrows=0).columns.str.strip()
    faltam = [c for c in usecols if c not in cab]
    if faltam:
        sys.exit(f"RESULTADOS sem as colunas: {faltam}")

    lidas = descartadas = 0
    tam_descartados = {a: Counter() for a in AREAS}
    leitor = pd.read_csv(caminho_resultados, sep=";", encoding=ENC,
                         usecols=usecols, dtype=str, chunksize=CHUNK)
    for ch in leitor:
        lidas += len(ch)
        for area in AREAS:
            d = ch[(ch[f"TP_PRESENCA_{area}"] == "1") & ch[f"TX_RESPOSTAS_{area}"].notna()]
            for prova, sub in d.groupby(f"CO_PROVA_{area}"):
                k = (area, str(prova).strip())
                if k not in acc:
                    continue                       # não é prova azul
                resp = sub[f"TX_RESPOSTAS_{area}"].str.strip()
                tam = resp.str.len()
                validos = (N_ITENS, LEN_LC_ANTIGO) if area == "LC" else (N_ITENS,)
                ok = tam.isin(validos)
                if (~ok).any():
                    descartadas += int((~ok).sum())
                    tam_descartados[area].update(tam[~ok].value_counts().to_dict())
                if not ok.any():
                    continue
                resp, tam = resp[ok], tam[ok].to_numpy()
                lingua = sub.loc[ok, "TP_LINGUA"].to_numpy()
                a, chave = acc[k], chaves[k]["chave"]
                if area != "LC" and not a["conferido"]:
                    conferir(area, k[1], chave[0], sub[f"TX_GABARITO_{area}"].dropna().str.strip())
                    a["conferido"] = True
                for L in np.unique(tam):
                    linhas = tam == L
                    texto = "".join(resp[linhas].tolist()).encode("latin-1", "replace")
                    m = np.frombuffer(texto, dtype=np.uint8).reshape(-1, int(L))
                    lg_L = lingua[linhas]
                    for g in ((0, 1) if area == "LC" else (0,)):
                        mg = m[lg_L == str(g)] if area == "LC" else m
                        if len(mg) == 0:
                            continue
                        if L == LEN_LC_ANTIGO:
                            proprio = mg[:, N_LANG * g:N_LANG * (g + 1)]
                            outro = mg[:, N_LANG * (1 - g):N_LANG * (2 - g)]
                            kl = chave[g, :N_LANG]
                            a["lang_check"][g] += (int((proprio == kl).sum()),
                                                   int((outro == kl).sum()), proprio.size)
                            x = np.concatenate([proprio, mg[:, 2 * N_LANG:]], axis=1)
                        else:
                            x = mg
                        acumular(a, chave, x, g)
        print(f"  {lidas:,} linhas lidas...", end="\r")
    print(f"\n  total: {lidas:,} linhas; {descartadas:,} respostas descartadas por tamanho inesperado")
    for area, cnt in tam_descartados.items():
        if cnt:
            print(f"    {area}: tamanhos descartados {dict(cnt.most_common(3))}")
    if descartadas > 0.01 * lidas:
        print("  ATENÇÃO: muitas respostas com tamanho inesperado; o layout deste ano pode ser diferente.")
    return chaves, acc


# Identifica a prova azul regular (com maior volume de participantes) por área
# Com isso, calcula estatísticas detalhadas por questão: percentual de acerto, percentual de erro,
# marcações em branco e indica se a questão foi anulada, gerando um DataFrame em ordem cronológica
def montar_saida(ano, itens, chaves, acc):
    print("\nProvas AZUL encontradas (participantes presentes):")
    escolhidas = {}
    for area in AREAS:
        cands = sorted(((int(a["n"][:, 0].sum()), k) for k, a in acc.items() if k[0] == area), reverse=True)
        for n, k in cands:
            print(f"  {area}  prova {k[1]}: {n:>10,}")
        if cands and cands[0][0] >= MIN_PARTICIPANTES:
            escolhidas[area] = cands[0][1]
        else:
            print(f"  AVISO: {area} sem participantes suficientes em {ano}; área NÃO incluída.")
    print("Usando a prova com mais participantes em cada área (a regular):",
          {a: k[1] for a, k in escolhidas.items()})

    linhas = []
    for area, k in escolhidas.items():
        a, idx_map = acc[k], chaves[k]["idx"]
        if a["lang_check"][:, 2].sum() > 0:
            for g, nome in ((0, "inglês"), (1, "espanhol")):
                c = a["lang_check"][g]
                if c[2]:
                    ok = c[0] > c[1]
                    print(f"  verificação LC/{k[1]} ({nome}): acerto no bloco assumido {100 * c[0] / c[2]:.1f}% "
                          f"x outro bloco {100 * c[1] / c[2]:.1f}%",
                          "OK" if ok else "<-- ATENÇÃO: blocos de língua possivelmente trocados")
        g = itens[(itens["SG_AREA"] == area) & (itens["CO_PROVA"] == k[1])]
        for r in g.itertuples():
            if r.Index not in idx_map:
                continue
            i = idx_map[r.Index]
            lg = lingua_do_item(r.TP_LINGUA)
            grupos = (0, 1) if lg is None else (lg,)
            n = sum(a["n"][x][i] for x in grupos)
            ac = sum(a["acerto"][x][i] for x in grupos)
            br = sum(a["branco"][x][i] for x in grupos)
            aban = getattr(r, "IN_ITEM_ABAN", np.nan)
            anulado = int(aban == 1 or chaves[k]["chave"][grupos[0], i] == 0)
            linhas.append({
                "ano": ano, "dia": dia_da_area(area, ano), "area": area, "co_prova": k[1],
                "posicao": r.CO_POSICAO, "co_item": r.CO_ITEM, "habilidade": r.CO_HABILIDADE,
                "lingua": "" if lg is None else ["ingles", "espanhol"][lg],
                "gabarito": r.TX_GABARITO, "n": int(n), "acertos": int(ac),
                "pct_acerto": round(100 * ac / n, 2) if n else np.nan,
                "pct_erro": round(100 * (1 - ac / n), 2) if n else np.nan,
                "pct_branco_ou_dupla": round(100 * br / n, 2) if n else np.nan,
                "dificuldade_tri": getattr(r, "NU_PARAM_B", np.nan),
                "discriminacao_tri": getattr(r, "NU_PARAM_A", np.nan),
                "anulado": anulado,
            })
    return pd.DataFrame(linhas).sort_values(["dia", "area", "posicao", "lingua"])


# Concatena os arquivos CSV individuais de cada ano em uma única tabela com o histórico compilado
# Gera um arquivo unificado ('todos_os_anos.csv') e extrai todas as questões válidas
# (não anuladas) com índice de erro >= limiar, mostrando quantas há por ano e área
def juntar(saida, limiar):
    arqs = sorted(glob.glob(os.path.join(saida, "erros_20*.csv")))
    if not arqs:
        sys.exit(f"Nenhum erros_AAAA.csv em {saida}/")
    df = pd.concat((pd.read_csv(a) for a in arqs), ignore_index=True)
    df.to_csv(os.path.join(saida, "todos_os_anos.csv"), index=False)

    altos = df[(df["anulado"] == 0) & (df["pct_erro"] >= limiar)].sort_values("pct_erro", ascending=False)
    destino = os.path.join(saida, f"questoes_erro_acima_{limiar:g}pct.csv")
    altos.to_csv(destino, index=False)

    print(f"{len(arqs)} anos juntados, {len(df):,} questões totais processadas.")
    print(f"Filtro aplicado: {len(altos)} questões com taxa de erro >= {limiar:g}%. Salvo em '{destino}'.")
    print("\nQuestões acima do limiar por ano e área (confira se alguma área está zerada):")
    print(pd.crosstab(altos["ano"], altos["area"]).reindex(
        index=sorted(df["ano"].unique()), columns=list(AREAS), fill_value=0).to_string())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--ano", type=int)
    p.add_argument("--itens", help="caminho do ITENS_PROVA_AAAA.csv")
    p.add_argument("--resultados", help="caminho do RESULTADOS_AAAA.csv (ou MICRODADOS_ENEM_AAAA.csv)")
    p.add_argument("--saida", default="saida")
    p.add_argument("--juntar", action="store_true")
    p.add_argument("--limiar", type=float, default=LIMIAR_PADRAO,
                   help="% mínimo de erro para listar a questão (padrão: 75)")
    args = p.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    if args.juntar:
        return juntar(args.saida, args.limiar)
    if not (args.ano and args.itens and args.resultados):
        p.error("informe --ano, --itens e --resultados (ou use --juntar)")

    print(f"ENEM {args.ano}")
    itens = ler_itens(args.itens)
    chaves, acc = processar(itens, args.resultados)
    df = montar_saida(args.ano, itens, chaves, acc)

    # Salva o arquivo geral com todas as questões do ano analisado
    destino = os.path.join(args.saida, f"erros_{args.ano}.csv")
    df.to_csv(destino, index=False)

    # Todas as questões válidas do ano com taxa de erro >= limiar (não só as 10 piores)
    altos = df[(df["anulado"] == 0) & (df["pct_erro"] >= args.limiar)].sort_values("pct_erro", ascending=False)
    destino_altos = os.path.join(args.saida, f"questoes_erro_acima_{args.limiar:g}pct_{args.ano}.csv")
    altos.to_csv(destino_altos, index=False)

    print(f"\nSalvo em {destino} (todas as questões) e em {destino_altos} "
          f"({len(altos)} questões com erro >= {args.limiar:g}%).")
    print("Por área:", altos.groupby("area").size().to_dict() if len(altos) else "nenhuma")

    cols = ["area", "posicao", "habilidade", "pct_erro", "dificuldade_tri"]
    if not altos.empty:
        print(f"\nQuestões com índice de erro >= {args.limiar:g}% ({len(altos)} encontradas):")
        print(altos[cols].to_string(index=False))
    else:
        print(f"\nNenhuma questão atingiu o índice de erro de {args.limiar:g}% nesta prova.")


if __name__ == "__main__":
    main()
