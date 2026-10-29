#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comparar_shapes.py
Compara trajetos (shapeLinha) entre dois periodos, POR COD de linha.

Correcao (v2): codigos de variante (SHP) nao sao estaveis entre anos,
entao cruzamos so por COD e, dentro do COD, pareamos a variante mais
semelhante (menor distancia de Chamfer simetrica).

Metodo
======
1. Um shapeLinha por periodo (default: dia 15 de mar/ago por ano presente).
2. Por COD: conjunto de variantes em A e em B (polylines de lat/lon).
3. Distancia simetrica de Chamfer em metros entre variantes A e B.
4. Melhor par por COD: minimo de Chamfer; status nova/extinta/mantida.

Saida:
  comparacao_AAAA_AAAA.csv (cod, status, shp_a, shp_b, chamfer_m)

Uso:
  python comparar_shapes.py --base coleta_curitiba
"""

import argparse
import io
import json
import lzma
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIO_TERRA = 6371000.0
NPTS = 150


def abrir_utf8(p: Path):
    abre = lzma.open if p.suffix == ".xz" else open
    return io.TextIOWrapper(abre(p, "rb"), encoding="utf-8-sig")


def ler_json(p: Path):
    with abrir_utf8(p) as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return [json.loads(l) for l in texto.splitlines() if l.strip()]


def hav_m(lat1, lon1, lat2, lon2):
    lat1, lat2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    a = np.sin((lat1 - lat2) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def amostrar(pts, n=NPTS):
    if len(pts) <= n:
        return pts
    idx = np.linspace(0, len(pts) - 1, n).astype(int)
    return pts[idx]


def chamfer_simetrico(a, b):
    a = amostrar(a); b = amostrar(b)
    m = hav_m(a[:, 0][:, None], a[:, 1][:, None], b[:, 0][None, :], b[:, 1][None, :])
    return float(m.min(1).mean() + m.min(0).mean())


def carregar_shapes(p: Path):
    df = pd.DataFrame(ler_json(p))
    df["COD"], df["SHP"] = df["COD"].astype(str).str.strip(), df["SHP"].astype(str).str.strip()
    lat = pd.to_numeric(df["LAT"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    lon = pd.to_numeric(df["LON"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df = df.assign(lat=lat, lon=lon).dropna(subset=["lat", "lon"])
    out = {}
    for (cod, shp), g in df.groupby(["COD", "SHP"], sort=False):
        out.setdefault(cod, {})[shp] = g[["lat", "lon"]].to_numpy()
    return out


def achar_shape_periodo(base: Path, ano: int, mes: int):
    alvo = Path(base)
    cand = sorted(alvo.rglob(f"{ano}_{mes:02d}_15_shapeLinha.json*"))
    if not cand:
        cand = sorted(alvo.rglob(f"{ano}_{mes:02d}_*_shapeLinha.json*"))
    return cand[0] if cand else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="coleta_curitiba")
    ap.add_argument("--refA", default="2017-03-15")
    ap.add_argument("--refB", default="2026-09-15")
    ap.add_argument("--saida", default="outputs/comparacao_shapes")
    args = ap.parse_args()

    ya, ma = map(int, args.refA[:7].split("-"))
    yb, mb = map(int, args.refB[:7].split("-"))
    fa = achar_shape_periodo(args.base, ya, ma)
    fb = achar_shape_periodo(args.base, yb, mb)
    if not fa or not fb:
        sys.exit(f"shapeLinha nao encontrado para {args.refA} ou {args.refB} em {args.base}")
    print(f"A: {fa.name}")
    print(f"B: {fb.name}")

    sa = carregar_shapes(fa)
    sb = carregar_shapes(fb)
    all_cods = sorted(set(sa) | set(sb))

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    resultado = []
    for cod in all_cods:
        va = sa.get(cod)
        vb = sb.get(cod)
        if va is None:
            resultado.append({"cod": cod, "status": "nova", "shp_a": None, "shp_b": None, "chamfer_m": None})
            continue
        if vb is None:
            resultado.append({"cod": cod, "status": "extinta", "shp_a": None, "shp_b": None, "chamfer_m": None})
            continue
        melhor = None
        for shp_a, pa in va.items():
            for shp_b, pb in vb.items():
                d = chamfer_simetrico(pa, pb)
                if melhor is None or d < melhor[2]:
                    melhor = (shp_a, shp_b, d, pa, pb)
        shp_a, shp_b, d, pa, pb = melhor
        resultado.append({"cod": cod, "status": "mantida",
                          "shp_a": shp_a, "shp_b": shp_b,
                          "chamfer_m": round(d, 1)})

    df = pd.DataFrame(resultado).sort_values(["status", "chamfer_m"],
                                              ascending=[True, False], na_position="last")
    df.to_csv(saida / f"comparacao_{ya}_{yb}.csv", index=False)

    keep = df[df.status == "mantida"]
    print(f"\nMantidas: {len(keep)} | novas: {(df.status=='nova').sum()} | extintas: {(df.status=='extinta').sum()}")
    print("\nTop 10 maiores mudancas (mantidas):")
    print(keep.nlargest(10, "chamfer_m")[["cod", "shp_a", "shp_b", "chamfer_m"]].to_string(index=False))
    print(f"\nGravado: {saida / f'comparacao_{ya}_{yb}.csv'}")


if __name__ == "__main__":
    main()