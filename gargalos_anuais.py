#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gargalos_anuais.py
Cruza atrasos por checkpoint entre dois periodos (ex.: mar/2017 vs set/2026).

Metodo
======
1. Le atrasos_por_ponto.csv de duas pastas (uma por periodo).
2. Gradeia os checkpoints em celulas de ~200 m (0.0022 grau de lat/lon em Curitiba).
3. Por celula/periodo: mediana, p90, n. Celulas so entram no ranking se
   n >= MIN_OBS nos dois periodos (evita basear em 2-3 passagens).
4. Piora = p90_2026 - p90_2017. Top de pioras = candidatos a gargalo novo.
5. Gera figura de dispersao lat/lon pintada por piora (vermelho = piorou).

Uso:
  python gargalos_anuais.py --anoA outputs/atrasos_v2_2017 --anoB outputs/atrasos_v2_2026

Saida:
  gargalos_cruzado.csv    (celula, p90_a, p90_b, piora_min, n_a, n_b)
  gargalos_cruzado.png    (mapa lat/lon por piora)
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CELULA = 0.0022   # ~200 m em Curitiba
MIN_OBS = 20


def carregar(pasta: Path):
    df = pd.read_csv(Path(pasta) / "atrasos_por_ponto.csv", dtype={"COD": str})
    return df.dropna(subset=["lat", "lon", "atraso_min"])


def gradear(df):
    df = df.copy()
    df["cel_lat"] = (df["lat"] / CELULA).round()
    df["cel_lon"] = (df["lon"] / CELULA).round()
    return df


def resumir(df):
    grp = df.groupby(["cel_lat", "cel_lon"]).agg(
        n=("atraso_min", "size"),
        mediana=("atraso_min", "median"),
        p90=("atraso_min", lambda s: float(s.quantile(0.9))),
    ).reset_index()
    return grp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anoA", required=True, help="pasta com atrasos_por_ponto.csv do periodo A (ex.: atrasos_v2_2017)")
    ap.add_argument("--anoB", required=True, help="pasta com atrasos_por_ponto.csv do periodo B (ex.: atrasos_v2_2026)")
    ap.add_argument("--saida", default="outputs/gargalos")
    ap.add_argument("--labelA", default=None)
    ap.add_argument("--labelB", default=None)
    args = ap.parse_args()

    a = carregar(args.anoA)
    b = carregar(args.anoB)
    if a.empty or b.empty:
        sys.exit("Um dos periodos veio vazio; verifique as pastas.")
    la = args.labelA or Path(args.anoA).name
    lb = args.labelB or Path(args.anoB).name

    ra = resumir(gradear(a))
    rb = resumir(gradear(b))
    m = ra.merge(rb, on=["cel_lat", "cel_lon"], suffixes=("_a", "_b"))
    m = m[(m.n_a >= MIN_OBS) & (m.n_b >= MIN_OBS)]
    m["piora_min"] = m.p90_b - m.p90_a
    m = m.sort_values("piora_min", ascending=False)

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    m.to_csv(saida / "gargalos_cruzado.csv", index=False)

    fig, ax = plt.subplots(figsize=(7, 8))
    ax.set_facecolor("#f5f5f5")
    sc = ax.scatter(m.cel_lon * CELULA, m.cel_lat * CELULA,
                    c=m.piora_min, cmap="RdYlGn_r", vmin=-15, vmax=15, s=50)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title(f"Piora de atraso p90 por celula ({la} -> {lb})")
    fig.colorbar(sc, ax=ax, label="piora (min)")
    fig.tight_layout()
    fig.savefig(saida / "gargalos_cruzado.png", dpi=130)

    print(f"Celulas cruzadas com n suficiente: {len(m)}")
    print("\nTop 10 piora de atraso p90 por celula (min):")
    top = m.nlargest(10, "piora_min")
    print(top[["cel_lat", "cel_lon", "p90_a", "p90_b", "piora_min", "n_a", "n_b"]].to_string(index=False))
    print(f"\nGravados: {saida}/gargalos_cruzado.csv, gargalos_cruzado.png")


if __name__ == "__main__":
    main()