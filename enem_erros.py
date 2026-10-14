#!/usr/bin/env python3
"""
enem_erros.py - % de erro por questão do ENEM (prova AZUL, aplicação regular).

Rode um ano por vez:
  python enem_erros.py --ano 2024 --itens ITENS_PROVA_2024.csv --resultados RESULTADOS_2024.csv

Depois de rodar todos os anos, junte tudo numa tabela só:
  python enem_erros.py --juntar

Requisitos: pip install pandas numpy
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

# Dicionário que mapeia as áreas do conhecimento (Linguagens, Ciências Humanas, 
# Ciências da Natureza e Matemática) para o respectivo dia de aplicação da prova
AREAS = {"LC": 1, "CH": 1, "CN": 2, "MT": 2}   # área -> dia da prova
ENC = "latin-1"        # os arquivos do INEP vêm em latin-1
CHUNK = 200_000        # blocos de linhas lidas por vez (baixe se faltar memória)
N_ITENS = 45           # questões por área
BRANCO, DUPLA = ord("."), ord("*")

# Carrega e limpa o arquivo de metadados das questões (ITENS_PROVA)
# Filtra as colunas obrigatórias, remove espaços em branco dos textos,
# converte a posição da questão para inteiro e trata os parâmetros 
# do TRI trocando a vírgula por ponto.
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
# Retorna None para questões comuns, 0 para Inglês e 1 para Espanhol para
# garantir o tratamento correto no cruzamento com as respostas dos alunos
def lingua_do_item(valor):
    """None = item comum às duas línguas; 0 = inglês; 1 = espanhol."""
    if pd.isna(valor) or str(valor).strip() == "":
        return None
    return int(float(valor))


# Filtra as questões da prova de cor AZUL e monta gabaritos de referência
# Cria uma matriz indexada por [idioma, posição da questão] contendo o código ASCII 
# da alternativa correta (A, B, C, D, E), ignorando provas incompletas.
def montar_chaves(itens):
    """(área, prova) -> gabarito por língua e posição inicial. Só provas de cor AZUL."""
    chaves = {}
    azul = itens[itens["TX_COR"] == "AZUL"]
    for (area, prova), g in azul.groupby(["SG_AREA", "CO_PROVA"]):
        if area not in AREAS:
            continue
        pos0 = g["CO_POSICAO"].min()
        if (g["CO_POSICAO"] - pos0).max() != N_ITENS - 1:
            print(f"  aviso: {area}/{prova} não tem {N_ITENS} posições; ignorada")
            continue
        chave = np.zeros((2, N_ITENS), dtype=np.uint8)   # [língua, posição]; 0 = item inválido
        for r in g.itertuples():
            gab = str(r.TX_GABARITO).strip().upper()
            cod = ord(gab) if gab in ("A", "B", "C", "D", "E") else 0
            i = r.CO_POSICAO - pos0
            lg = lingua_do_item(r.TP_LINGUA)
            for l in ((0, 1) if lg is None else (lg,)):
                chave[l, i] = cod
        chaves[(area, prova)] = {"chave": chave, "pos0": pos0}
    return chaves


# Faz um teste de integridade comparando o gabarito oficial 
# com as respostas registradas de um participante real, emitindo um alerta 
# caso haja divergência nos dados
def conferir(area, prova, chave0, gab_participante):
    """Compara o gabarito do ITENS_PROVA com o que vem na linha de um participante."""
    gab = gab_participante.iloc[0]
    ref = [chr(c) if c else "?" for c in chave0]
    bate = len(gab) == N_ITENS and all(
        r == g or r == "?" or g not in "ABCDE" for r, g in zip(ref, gab))
    print(f"  conferência {area}/{prova}:",
          "OK, gabarito bate com o do participante" if bate
          else "ATENÇÃO: gabarito NÃO bate, não confie neste resultado")


# Processa os microdados de resultados em blocos -> economizar memória
# Para cada participante, extrai a string de respostas e valida o tamanho
# Usa operações vetorizadas do NumPy para contar: o total de respondentes (n), a soma de acertos e a soma de respostas em branco/duplas.
def processar(itens, caminho_resultados):
    chaves = montar_chaves(itens)
    if not chaves:
        sys.exit("Nenhuma prova AZUL encontrada no ITENS_PROVA.")
    acc = {k: {"n": np.zeros((2, N_ITENS)), "acerto": np.zeros((2, N_ITENS)),
               "branco": np.zeros((2, N_ITENS)), "conferido": False} for k in chaves}

    usecols = ["TP_LINGUA"]
    for a in AREAS:
        usecols += [f"TP_PRESENCA_{a}", f"CO_PROVA_{a}", f"TX_RESPOSTAS_{a}"]
    usecols += [f"TX_GABARITO_{a}" for a in ("CN", "CH", "MT")]
    cab = pd.read_csv(caminho_resultados, sep=";", encoding=ENC, nrows=0).columns.str.strip()
    faltam = [c for c in usecols if c not in cab]
    if faltam:
        sys.exit(f"RESULTADOS sem as colunas: {faltam}")

    lidas = descartadas = 0
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
                ok = resp.str.len() == N_ITENS
                descartadas += int((~ok).sum())
                if not ok.any():
                    continue
                resp = resp[ok]
                lingua = sub.loc[ok, "TP_LINGUA"].to_numpy()
                texto = "".join(resp.tolist()).encode("latin-1", "replace")
                mat = np.frombuffer(texto, dtype=np.uint8).reshape(-1, N_ITENS)
                a, chave = acc[k], chaves[k]["chave"]
                if area != "LC" and not a["conferido"]:
                    conferir(area, k[1], chave[0], sub[f"TX_GABARITO_{area}"].dropna().str.strip())
                    a["conferido"] = True
                for g in ((0, 1) if area == "LC" else (0,)):
                    x = mat[lingua == str(g)] if area == "LC" else mat
                    if len(x) == 0:
                        continue
                    a["n"][g] += len(x)
                    a["acerto"][g] += (x == chave[g]).sum(axis=0)
                    a["branco"][g] += ((x == BRANCO) | (x == DUPLA)).sum(axis=0)
        print(f"  {lidas:,} linhas lidas...", end="\r")
    print(f"\n  total: {lidas:,} linhas; {descartadas:,} respostas descartadas por tamanho != {N_ITENS}")
    if descartadas > 0.01 * lidas:
        print("  ATENÇÃO: muitas respostas com tamanho inesperado; o layout deste ano pode ser diferente.")
    return chaves, acc


# Identifica a prova azul regular (com maior volume de participantes) por área
# Com isso, calcula estatísticas detalhadas por questão: percentual de acerto, percentual de erro, 
# marcações em branco e indica se a questão foi anulada, gerando um DataFrame em ordem cronológica.
def montar_saida(ano, itens, chaves, acc):
    print("\nProvas AZUL encontradas (participantes presentes):")
    escolhidas = {}
    for area in AREAS:
        cands = sorted(((int(a["n"][:, 0].sum()), k) for k, a in acc.items() if k[0] == area), reverse=True)
        for n, k in cands:
            print(f"  {area}  prova {k[1]}: {n:>10,}")
        if cands and cands[0][0] > 0:
            escolhidas[area] = cands[0][1]
    print("Usando a prova com mais participantes em cada área (a regular):",
          {a: k[1] for a, k in escolhidas.items()})

    linhas = []
    for area, k in escolhidas.items():
        a, pos0 = acc[k], chaves[k]["pos0"]
        g = itens[(itens["SG_AREA"] == area) & (itens["CO_PROVA"] == k[1])]
        for r in g.itertuples():
            i = r.CO_POSICAO - pos0
            lg = lingua_do_item(r.TP_LINGUA)
            grupos = (0, 1) if lg is None else (lg,)
            n = sum(a["n"][x][i] for x in grupos)
            ac = sum(a["acerto"][x][i] for x in grupos)
            br = sum(a["branco"][x][i] for x in grupos)
            aban = getattr(r, "IN_ITEM_ABAN", np.nan)
            anulado = int(aban == 1 or chaves[k]["chave"][grupos[0], i] == 0)
            linhas.append({
                "ano": ano, "dia": AREAS[area], "area": area, "co_prova": k[1],
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
# Gera um arquivo unificado ('todos_os_anos.csv') e extrai um ranking das 
# 100 questões válidas (não anuladas) que apresentaram a maior taxa de erro.
def juntar(saida):
    arqs = sorted(glob.glob(os.path.join(saida, "erros_20*.csv")))
    if not arqs:
        sys.exit(f"Nenhum erros_AAAA.csv em {saida}/")
    df = pd.concat((pd.read_csv(a) for a in arqs), ignore_index=True)
    df.to_csv(os.path.join(saida, "todos_os_anos.csv"), index=False)
    top = df[df["anulado"] == 0].sort_values("pct_erro", ascending=False).head(100)
    top.to_csv(os.path.join(saida, "top100_mais_erradas.csv"), index=False)
    print(f"{len(arqs)} anos juntados, {len(df):,} questões. Arquivos em {saida}/")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--ano", type=int)
    p.add_argument("--itens", help="caminho do ITENS_PROVA_AAAA.csv")
    p.add_argument("--resultados", help="caminho do RESULTADOS_AAAA.csv (ou MICRODADOS_ENEM_AAAA.csv)")
    p.add_argument("--saida", default="saida")
    p.add_argument("--juntar", action="store_true")
    args = p.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    if args.juntar:
        return juntar(args.saida)
    if not (args.ano and args.itens and args.resultados):
        p.error("informe --ano, --itens e --resultados (ou use --juntar)")

    print(f"ENEM {args.ano}")
    itens = ler_itens(args.itens)
    chaves, acc = processar(itens, args.resultados)
    df = montar_saida(args.ano, itens, chaves, acc)
    destino = os.path.join(args.saida, f"erros_{args.ano}.csv")
    df.to_csv(destino, index=False)
    print(f"\nSalvo em {destino} ({len(df)} linhas). As 10 questões com mais erros:")
    cols = ["area", "posicao", "habilidade", "pct_erro", "dificuldade_tri"]
    print(df[df["anulado"] == 0].sort_values("pct_erro", ascending=False).head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
