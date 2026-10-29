#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selecionar_linhas.py
Gera o arquivo de CODs para alimentar snap_lote.py.

Criterios:
  - presente no catalogo de linhas dos dois periodos alvo
  - presente no dia de telemetria de referencia de cada periodo
  - volume minimo de registros GPS no dia (evita linha rara)

Uso:
  python selecionar_linhas.py --base coleta_curitiba
  python selecionar_linhas.py --base coleta_curitiba --top 50
"""

import argparse
import io
import json
import lzma
import sys
from pathlib import Path

import pandas as pd


def abrir_utf8(p: Path):
    abre = lzma.open if str(p).endswith(".json.xz") else open
    return io.TextIOWrapper(abre(p, "rb"), encoding="utf-8-sig")


def carregar_catalogo(p: Path):
    with abrir_utf8(p) as f:
        obj = json.load(f)
    df = pd.DataFrame(obj)
    return set(df["COD"].astype(str).str.strip())


def contar_linhas_telemetria(p: Path):
    cnt = {}
    with abrir_utf8(p) as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            cod = str(r.get("COD_LINHA", "")).strip()
            if cod:
                cnt[cod] = cnt.get(cod, 0) + 1
    return pd.Series(cnt)


def achar(pasta: Path, ext):
    cand = sorted(pasta.rglob(f"*{ext}*"))
    return cand[-1] if cand else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="coleta_curitiba", help="raiz com pastas por ano")
    ap.add_argument("--anoA", type=int, default=2017)
    ap.add_argument("--anoB", type=int, default=2026)
    ap.add_argument("--min_reg", type=int, default=2000,
                    help="minimo de registros GPS no dia pra considerar 'usaivel'")
    ap.add_argument("--top", type=int, default=None,
                    help="opcional: so as N primeiras por volume")
    ap.add_argument("--saida", default="linhas_selecionadas.txt")
    args = ap.parse_args()

    base = Path(args.base)
    pasta_a, pasta_b = base / str(args.anoA), base / str(args.anoB)

    cat_a = carregar_catalogo(achar(pasta_a, "_linhas.json"))
    cat_b = carregar_catalogo(achar(pasta_b, "_linhas.json"))
    print(f"Catalogo {args.anoA}: {len(cat_a)} | {args.anoB}: {len(cat_b)}")

    tel_a = achar(pasta_a, "_veiculos.json")
    tel_b = achar(pasta_b, "_veiculos.json")
    cnt_a = contar_linhas_telemetria(tel_a)
    cnt_b = contar_linhas_telemetria(tel_b)

    comuns = sorted(cat_a & cat_b)
    candidatas = []
    for cod in comuns:
        n_a = int(cnt_a.get(cod, 0))
        n_b = int(cnt_b.get(cod, 0))
        if n_a >= args.min_reg and n_b >= args.min_reg:
            candidatas.append((cod, n_a, n_b))
    print(f"Candidatas com n>={args.min_reg} nos dois periodos: {len(candidatas)}")

    candidatas.sort(key=lambda x: -(x[1] + x[2]))
    if args.top:
        candidatas = candidatas[:args.top]

    with open(args.saida, "w", encoding="utf-8") as f:
        f.write("# CODs selecionados por volume (presentes nos 2 periodos)\n")
        for cod, na, nb in candidatas:
            f.write(f"{cod}\n")

    print(f"Gravado: {args.saida}")


if __name__ == "__main__":
    main()