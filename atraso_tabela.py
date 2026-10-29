#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atraso_tabela.py (v3 - correcao de calendario)
Mede atraso por viagem contra a tabela oficial da URBS.

CORRECOES vs v2:
  1. Tabela do dia: a auditoria mostrou que os arquivos do espelho sao datados
     na janela de captacao (GPS do dia d opera no arquivo datado d+1). A tabela
     passa a ser buscada PRIORITARIAMENTE no arquivo datado d+1, com fallback d.
     [Hipotese sobre a convencao; as tabelas contem os perfis DIA 1/2/3 em todo
     arquivo, entao o impacto pratico e a escolha do perfil, seguindo o weekday
     da DATA OPERACIONAL - o que ja era feito.]
  2. --de/--ate para intervalos. --pontos multiplo.
  3. Saida com lat/lon do checkpoint.

Metodo: "horario real" = mediana dos timestamps a <= RAIO_M do ponto de
controle, na janela +-JANELA_MIN do previsto. Atraso = real - previsto.

Uso:
  python atraso_tabela.py --de 2026-09-01 --ate 2026-09-29 --pontos data/external coleta_curitiba --trajetorias outputs/trajetorias_v2
  python atraso_tabela.py --de 2026-09-09 --ate 2026-09-09 --diagnostico
"""
import argparse
import json
import lzma
import re
import sys
import unicodedata
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAIO_M = 200.0
JANELA_MIN = 45
RAIO_TERRA = 6371000.0

ALIAS_NOME = ["NOME", "NOME_PTO_PARADA_TH", "NOME_PTO", "PONTO", "NOME_ABREVIADO", "NOME_PTO_ABREVIADO", "POI_NAME"]
ALIAS_LAT = ["LAT", "LATITUDE", "POI_LAT"]
ALIAS_LON = ["LON", "LONGITUDE", "LNG", "POI_LON"]
QUALI = {"BAIRRO", "ESTACAO", "TUBO", "TERMINAL", "PRACA", "TRAVESSA", "RUA", "AV", "ALAMEDA", "LARGO"}

DIA_POR_WEEKDAY = {0: "1", 1: "1", 2: "1", 3: "1", 4: "1", 5: "2", 6: "3"}


def limpar_qualificador(s):
    return re.sub(r"\(.*?\)", "", str(s)).strip()


def norm(s):
    s = unicodedata.normalize("NFKD", limpar_qualificador(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
    return " ".join(s.split())


def abrir(path: Path):
    return lzma.open(path, "rt", encoding="utf-8") if path.suffix == ".xz" else open(path, "r", encoding="utf-8")


def ler_json_ou_ndjson(path: Path):
    with abrir(path) as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return [json.loads(l) for l in texto.splitlines() if l.strip()]


def carregar_tabela(pasta: Path, data: str):
    """Busca tabelaLinha do dia operacional `data`: primeiro no arquivo datado
    data+1 (convencao do espelho), com fallback para data e data-1."""
    d0 = pd.Timestamp(data)
    for cand in (d0 + timedelta(days=1), d0, d0 - timedelta(days=1)):
        padrao = f"{cand.strftime('%Y_%m_%d')}_tabelaLinha.json*"
        alvo = list(Path(pasta).rglob(padrao))
        if alvo:
            df = pd.DataFrame(ler_json_ou_ndjson(alvo[0]))
            df["COD"] = df["COD"].astype(str).str.strip()
            df["minutos_prev"] = (df["HORA"].str.slice(0, 2).astype(int) * 60
                                  + df["HORA"].str.slice(3, 5).astype(int))
            df["PONTO_NORM"] = df["PONTO"].map(norm)
            df["_arquivo_tabela"] = alvo[0].name
            return df
    return None


def filtrar_dia(tabela, data):
    dia_alvo = DIA_POR_WEEKDAY[pd.Timestamp(data).weekday()]
    disponiveis = sorted(set(tabela["DIA"].astype(str)))
    if dia_alvo not in disponiveis:
        dia_alvo = disponiveis[0]
        print(f"  aviso: DIA do weekday ausente; usando DIA={dia_alvo}")
    return tabela[tabela["DIA"].astype(str) == dia_alvo]


def numerico(serie):
    return pd.to_numeric(serie.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def carregar_pontos(bases):
    coord, achados = {}, []
    for base in bases:
        for padrao in ("*pois*", "*pontosLinha*"):
            achados.extend(sorted(Path(base).rglob(f"*_{padrao}.json*")))
    for p in achados:
        if p.suffix not in (".xz", ".gz") and not p.name.endswith(".json"):
            continue
        try:
            obj = ler_json_ou_ndjson(p)
        except Exception:
            continue
        df = pd.DataFrame([r for r in obj if isinstance(r, dict)])
        col_nome = next((c for c in ALIAS_NOME if c in df.columns), None)
        col_lat = next((c for c in ALIAS_LAT if c in df.columns), None)
        col_lon = next((c for c in ALIAS_LON if c in df.columns), None)
        if not (col_nome and col_lat and col_lon):
            continue
        df["_n"] = df[col_nome].map(norm)
        df["_lat"] = numerico(df[col_lat])
        df["_lon"] = numerico(df[col_lon])
        df = df.dropna(subset=["_lat", "_lon"])
        for _, r in df.iterrows():
            coord.setdefault(r["_n"], (r["_lat"], r["_lon"]))
    return coord, achados


def score_palavras(q_words, c_words):
    comum = sum(1 for q in q_words if any(w.startswith(q) or q.startswith(w) for w in c_words))
    return comum / len(q_words)


def casar_tiers(base, coord, limiar):
    if base in coord:
        return coord[base]
    for nome, c in coord.items():
        if nome.startswith(base) or base.startswith(nome):
            return c
    qw = base.split()
    melhor, melhor_c = 0.0, None
    for nome, c in coord.items():
        s = score_palavras(qw, nome.split())
        if s > melhor:
            melhor, melhor_c = s, c
    if melhor >= limiar:
        return melhor_c
    return None


def casar_ponto(ponto_norm, coord):
    c = casar_tiers(ponto_norm, coord, 0.75)
    if c is not None:
        return c
    toks = ponto_norm.split()
    if len(toks) >= 2 and toks[0] in QUALI:
        curto = " ".join(toks[1:])
        c = casar_tiers(curto, coord, 1.0)
        if c is not None:
            return c
        cand = [cc for nome, cc in coord.items() if curto in nome.split()]
        if cand:
            return (sum(x[0] for x in cand) / len(cand),
                    sum(x[1] for x in cand) / len(cand))
    return None


def hav_m(lat1, lon1, lat2, lon2):
    lat1, lat2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((lat1 - lat2) / 2) ** 2 + np.cos(lat1) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def processar_dia(data, args, ponto_coord, pasta_traj):
    tabela = carregar_tabela(args.coleta, data)
    if tabela is None:
        print(f"{data}: sem tabelaLinha; pulando")
        return None
    arq_usado = tabela["_arquivo_tabela"].iloc[0]
    tabela = filtrar_dia(tabela, data)
    nomes_unicos = tabela["PONTO_NORM"].unique()
    coord_ok = {n: casar_ponto(n, ponto_coord) for n in nomes_unicos}
    cob = sum(v is not None for v in coord_ok.values())
    print(f"{data}: tabela {len(tabela)} reg, {len(nomes_unicos)} pontos, "
          f"{cob} com coord | fonte: {arq_usado}")

    lances = []
    for traj in sorted(pasta_traj.glob(f"trajetoria_l*_{data}.csv")):
        cod = traj.name.split("_")[1][1:]
        linha_tab = tabela[tabela.COD == cod]
        if linha_tab.empty:
            continue
        t = pd.read_csv(traj, parse_dates=["datahora"])
        t["min_dia"] = (t["datahora"].dt.hour * 60 + t["datahora"].dt.minute)
        for ponto_norm, c in coord_ok.items():
            if c is None:
                continue
            prog = linha_tab[linha_tab.PONTO_NORM == ponto_norm]
            if prog.empty:
                continue
            dist = hav_m(c[0], c[1], t["lat"].to_numpy(), t["lon"].to_numpy())
            mins = np.sort(t["min_dia"].to_numpy()[dist <= RAIO_M])
            if len(mins) == 0:
                continue
            for _, r in prog.iterrows():
                ini = np.searchsorted(mins, r["minutos_prev"] - JANELA_MIN)
                fim = np.searchsorted(mins, r["minutos_prev"] + JANELA_MIN)
                if fim <= ini:
                    continue
                real = float(np.median(mins[ini:fim]))
                atraso = real - r["minutos_prev"]
                if atraso > 720:
                    atraso -= 1440
                elif atraso < -720:
                    atraso += 1440
                lances.append({"data": data, "COD": cod, "DIA": r["DIA"], "TABELA": r["TABELA"],
                               "NUM": r["NUM"], "PONTO": r["PONTO"],
                               "previsto": r["HORA"],
                               "real": f"{int(real // 60):02d}:{int(real % 60):02d}",
                               "atraso_min": round(atraso, 1),
                               "n_obs_raio": int(fim - ini),
                               "lat": c[0], "lon": c[1]})
    return pd.DataFrame(lances)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datas", nargs="+", default=None)
    ap.add_argument("--de", default=None)
    ap.add_argument("--ate", default=None)
    ap.add_argument("--trajetorias", default=r"outputs/trajetorias")
    ap.add_argument("--coleta", default=r"coleta_curitiba")
    ap.add_argument("--pontos", nargs="+", default=[r"data/external", r"coleta_curitiba"])
    ap.add_argument("--saida", default=r"outputs/atrasos")
    ap.add_argument("--diagnostico", action="store_true")
    args = ap.parse_args()

    if args.datas:
        datas = args.datas
    else:
        if not (args.de and args.ate):
            sys.exit("Informe --datas ou --de e --ate.")
        ini, fim = pd.Timestamp(args.de), pd.Timestamp(args.ate)
        datas = [(ini + timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range((fim - ini).days + 1)]

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    ponto_coord, fontes = carregar_pontos(args.pontos)
    print(f"Pontos com coordenada: {len(ponto_coord)} (fontes: {len(fontes)} arquivos)")
    if not ponto_coord:
        sys.exit("Sem coordenadas de pontos; verifique --pontos.")

    if args.diagnostico:
        data = datas[0]
        tabela = carregar_tabela(args.coleta, data)
        if tabela is None:
            sys.exit(f"Sem tabelaLinha para {data}")
        tabela = filtrar_dia(tabela, data)
        nomes = tabela["PONTO_NORM"].unique()
        casados = [n for n in nomes if casar_ponto(n, ponto_coord)]
        nao = [n for n in nomes if n not in set(casados)]
        print(f"{data}: {len(casados)}/{len(nomes)} casados ({100 * len(casados) / len(nomes):.0f}%)")
        print("Exemplos casados:", casados[:10])
        print("Exemplos NAO casados:", nao[:10])
        print("DIA codes:", sorted(tabela["DIA"].unique()), "| fonte:", tabela["_arquivo_tabela"].iloc[0])
        return

    todos, resumos = [], []
    for data in datas:
        lances = processar_dia(data, args, ponto_coord, Path(args.trajetorias))
        if lances is None or lances.empty:
            continue
        todos.append(lances)
        for dia_cod, grp in lances.groupby("DIA"):
            resumos.append({"data": data, "DIA": dia_cod, "pontos_casados": len(grp),
                            "linhas": grp.COD.nunique(),
                            "atraso_mediano_min": round(float(grp.atraso_min.median()), 1),
                            "atraso_p90_min": round(float(grp.atraso_min.quantile(0.9)), 1)})
    if todos:
        full = pd.concat(todos, ignore_index=True)
        full.to_csv(saida / "atrasos_por_ponto.csv", index=False)
        pd.DataFrame(resumos).to_csv(saida / "resumo_atrasos.csv", index=False)
        print(pd.DataFrame(resumos).to_string(index=False))
        print(f"\nGravados em {saida}: atrasos_por_ponto.csv, resumo_atrasos.csv")
    else:
        print("Nenhum lance casado. Rode --diagnostico.")


if __name__ == "__main__":
    main()