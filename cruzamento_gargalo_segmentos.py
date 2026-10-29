#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cruzamento_gargalo_segmentos.py
Cruza os gargalos do painel (gargalos_classificados.csv) com os segmentos
das trajetorias snapeadas (outputs/trajetorias/segmentos_l*.csv), para verificar
se a lentidao medida por trajeto coincide espacialmente com o gargalo do painel.

Metodo
======
1. Le gargalos_classificados.csv (celulas com lat/lon e % lentidao do mes).
2. Para cada linha com segmentos_*.csv na pasta de trajetorias: reconstrui o
   centroide de cada segmento de 100 m a partir do trajetoria_l*.csv (mediana
   de lat/lon dos pontos aceitos naquele segmento).
3. Para cada celula de gargalo, acha o segmento mais proximo da linha via
   haversine; registra distancia, % lentos do segmento e vel mediana.
4. Filtro analitico: celulas a ate 200 m do segmento sao consideradas
   "do corredor". Saida: uma linha por (celula, linha) com as metricas
   lado a lado (pct do painel x pct do trajeto).

Saida: cruzamento_gargalo_segmentos.csv (todos os pares) e
       cruzamento_corredor.csv (pares a <= 200 m).

Uso:
  python cruzamento_gargalo_segmentos.py --trajetorias outputs/trajetorias       --gargalos outputs/comparativo/gargalos_classificados.csv
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

RAIO_TERRA = 6371000.0
DIST_MAX_M = 200.0


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lat2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def centroides_por_segmento(pasta: Path):
    """Reconstrui o centroide (mediana lat/lon) de cada segmento de 100 m
    a partir dos arquivos trajetoria_l{cod}_{data}.csv."""
    quadros = {}
    for traj in sorted(pasta.glob("trajetoria_l*_*.csv")):
        m = re.match(r"trajetoria_l(.+?)_(\d{4}-\d{2}-\d{2})\.csv", traj.name)
        if not m:
            continue
        cod = m.group(1)
        t = pd.read_csv(traj, usecols=["lat", "lon", "s_m"])
        t["segmento"] = (t["s_m"] // 100).astype(int)
        c = t.groupby("segmento").agg(lat=("lat", "median"), lon=("lon", "median"))
        quadros.setdefault(cod, []).append(c)
    out = {}
    for cod, partes in quadros.items():
        out[cod] = pd.concat(partes).groupby(level=0).median()
    return out


def rodar(pasta_traj: Path, arq_gargalos: Path, pasta_saida: Path):
    g = pd.read_csv(arq_gargalos)
    g["pct_lent_celula"] = 100 * g["observacoes_lentas"] / g["observacoes_validas"]
    centroides = centroides_por_segmento(pasta_traj)
    if not centroides:
        raise SystemExit("Nenhum trajetoria_l*.csv encontrado; rode snap_lote.py antes.")

    pares = []
    for cod, cent in centroides.items():
        segs = sorted(pasta_traj.glob(f"segmentos_l{cod}_*.csv"))
        if not segs:
            continue
        seg = pd.concat([pd.read_csv(s) for s in segs]).groupby("segmento").agg(
            n=("n", "sum"), pct_lentos=("pct_lentos", "mean"),
            vel_mediana_kmh=("vel_mediana_kmh", "mean")).reset_index()
        seg = seg.merge(cent.reset_index(), on="segmento", how="left").dropna(subset=["lat"])
        dist = haversine_m(g["lat_centro"].to_numpy()[:, None], g["lon_centro"].to_numpy()[:, None],
                           seg["lat"].to_numpy()[None, :], seg["lon"].to_numpy()[None, :])
        j = np.nanargmin(dist, axis=1)
        pares.append(pd.DataFrame({
            "CELULA": g.CELULA,
            "parada": g.parada_mais_proxima,
            "classe": g.classe,
            "pct_gargalo_perm": g.pct_lent_celula,
            "linha": cod,
            "segmento": seg.loc[j, "segmento"].values,
            "dist_gargalo_ao_seg_m": np.round(dist[np.arange(len(g)), j], 1),
            "pct_lentos_seg": seg.loc[j, "pct_lentos"].values,
            "vel_mediana_seg": np.round(seg.loc[j, "vel_mediana_kmh"].values, 1)}))
    cruz = pd.concat(pares, ignore_index=True)
    cruz = cruz.sort_values("pct_gargalo_perm", ascending=False)
    cruz.to_csv(pasta_saida / "cruzamento_gargalo_segmentos.csv", index=False)
    corredor = cruz[cruz.dist_gargalo_ao_seg_m <= DIST_MAX_M]
    corredor.to_csv(pasta_saida / "cruzamento_corredor.csv", index=False)
    print(f"{len(corredor)} celulas a <= {DIST_MAX_M:.0f} m de algum segmento; "
          f"arquivos em {pasta_saida}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trajetorias", default=r"outputs/trajetorias")
    ap.add_argument("--gargalos", default=r"outputs/comparativo/gargalos_classificados.csv")
    ap.add_argument("--saida", default=r"outputs/comparativo/cruzamentos")
    a = ap.parse_args()
    pasta = Path(a.saida); pasta.mkdir(parents=True, exist_ok=True)
    rodar(Path(a.trajetorias), Path(a.gargalos), pasta)


if __name__ == "__main__":
    main()