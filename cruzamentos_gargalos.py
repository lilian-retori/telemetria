#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cruzamentos_gargalos.py
Reproduz os tres cruzamentos exploratorios do projeto (etapa 4):

  C1  Cluster horario x Classe espacial   -> saida: crosstab_cluster_classe.csv
  C2  Estrutural x Sazonal (tipo de dia)  -> saida: cruzamento_estrutural_sazonal.csv
  C3  Gargalo x Linhas dominantes         -> saida: cruzamento_gargalo_linhas.csv
                                                  linhas_por_exposicao_gargalos.csv

Metodo
======
C1: Para cada gargalo do top 20, constroi-se a assinatura horaria em dias uteis
    (obs_por_dia por hora, 0-23h), normalizada como fracao do total diario,
    padronizada (z-score) e agrupada com KMeans (k=4). A tabela de contingencia
    cluster x classe espacial (do gargalos_classificados.csv) testa se a classe
    espacial (definida por distancia a parada mais proxima + heuristica de nome)
    e corroborada pelo comportamento temporal.

C2: Para cada gargalo, media de obs_por_dia por tipo_dia (dia_util, sabado,
    domingo). Razao = dia_util / media(sabado, domingo). Regimes:
      >= 3.0   sazonal_util      (problema de janela de pico)
      >= 1.5   predominante_util (pendular diario)
      >= 0.67  estrutural        (trava todo dia)
      < 0.67   predominante_fds  (ex.: gargalo turistico de fim de semana)

C3: auditoria_top20.csv traz, por gargalo, "linhas_dominantes" no formato
    NOME (obs) | NOME (obs) | ... ; parseado com regex "^nome (n)$" por bloco
    separado por "|". Saida invertida: por linha, em quantos gargalos do top20
    aparece e o total de observacoes lentas associadas.

Uso: coloque na pasta do projeto e rode
     python cruzamentos_gargalos.py --pasta outputs/comparativo
Espera encontrar: perfis_horarios_top20.csv, gargalos_classificados.csv,
auditoria_top20.csv na pasta informada.
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

ROTULOS_CLUSTER = {0: "pico_tarde", 1: "pico_madrugada", 2: "pico_manha", 3: "fim_tarde_estendido"}


def etiquetar_regime(razao):
    if razao >= 3.0:
        return "sazonal_util"
    if razao >= 1.5:
        return "predominante_util"
    if razao >= 1 / 1.5:
        return "estrutural"
    return "predominante_fds"


def rodar(pasta: Path, saida: Path):
    pf = pd.read_csv(pasta / "perfis_horarios_top20.csv")
    g = pd.read_csv(pasta / "gargalos_classificados.csv")
    aud = pd.read_csv(pasta / "auditoria_top20.csv")

    # --- C1 ----------------------------------------------------------------------
    du = pf[pf.TIPO_DIA == "dia_util"]
    assinatura = du.pivot_table(index="GARGALO", columns="HORA_INT",
                                values="obs_por_dia", aggfunc="sum", fill_value=0)
    for h in range(24):
        if h not in assinatura.columns:
            assinatura[h] = 0.0
    assinatura = assinatura[sorted(assinatura.columns)]
    fracao = assinatura.div(assinatura.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    X = StandardScaler().fit_transform(fracao.values)
    km = KMeans(4, n_init=50, random_state=42).fit(X)
    cl = pd.DataFrame({"GARGALO": assinatura.index, "cluster": km.labels_})

    g2 = g.assign(nome=g["parada_mais_proxima"].str.slice(0, 30).str.strip().str.lower())
    cl2 = cl.assign(nome=cl["GARGALO"].str.replace(r"^#\d+\s*", "", regex=True)
                    .str.slice(0, 30).str.strip().str.lower())
    m = cl2.merge(g2[["nome", "classe"]].drop_duplicates("nome"), on="nome", how="left")
    assert m["classe"].notna().all(), "gargalo sem classe; revista a chave de join"
    tab = pd.crosstab(m.cluster.map(ROTULOS_CLUSTER), m.classe)
    tab.to_csv(saida / "crosstab_cluster_classe.csv")

    # --- C2 ----------------------------------------------------------------------
    piv = pf.pivot_table(index="GARGALO", columns="TIPO_DIA",
                         values="obs_por_dia", aggfunc="mean").fillna(0)
    piv["razao_util_fds"] = piv["dia_util"] / piv[["sabado", "domingo"]].mean(axis=1).replace(0, np.nan)
    piv = piv.dropna(subset=["razao_util_fds"]).copy()
    piv["regime"] = piv["razao_util_fds"].apply(etiquetar_regime)
    out = cl.merge(piv.reset_index()[["GARGALO", "dia_util", "sabado", "domingo",
                                      "razao_util_fds", "regime"]], on="GARGALO")
    out.to_csv(saida / "cruzamento_estrutural_sazonal.csv", index=False)

    # --- C3 ----------------------------------------------------------------------
    pares = []
    for _, r in aud.iterrows():
        for bloco in str(r["linhas_dominantes"]).split("|"):
            b = re.match(r"\s*(.+?)\s*\((\d+)\)\s*$", bloco.strip())
            if b:
                pares.append({"GARGALO": r["GARGALO"], "linha": b.group(1).strip(),
                              "obs_lentas_no_gargalo": int(b.group(2)),
                              "pct_lentidao_gargalo": r["percentual_lentidao"],
                              "pico_h": r["hora_pico_dia_util"]})
    xl = pd.DataFrame(pares)
    xl.to_csv(saida / "cruzamento_gargalo_linhas.csv", index=False)
    agregado = (xl.groupby("linha")
                  .agg(gargalos_top20=("GARGALO", "nunique"),
                       obs_lentas_total=("obs_lentas_no_gargalo", "sum"))
                  .reset_index().sort_values("obs_lentas_total", ascending=False))
    agregado.to_csv(saida / "linhas_por_exposicao_gargalos.csv", index=False)

    print("C1:", len(cl), "gargalos clusterizados; crosstab em", saida / "crosstab_cluster_classe.csv")
    print("C2:", len(out), "gargalos classificados; regime em", saida / "cruzamento_estrutural_sazonal.csv")
    print("C3:", len(xl), "pares gargalo-linha;", saida / "cruzamento_gargalo_linhas.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", default="outputs/comparativo")
    ap.add_argument("--saida", default="outputs/comparativo/cruzamentos")
    a = ap.parse_args()
    pasta, saida = Path(a.pasta), Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    rodar(pasta, saida)


if __name__ == "__main__":
    main()