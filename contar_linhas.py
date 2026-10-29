#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contar_linhas.py
Conta quantas linhas existem nos arquivos *_linhas.json.xz da coleta,
consolidando por ano (util para responder "a malha encolheu ou expandiu?").

Criterios gerados:
  n_registros  : linhas no catalogo daquele dia (tal como veio)
  n_cod_unicos : CODs distintos naquele dia
  n_mes_max    : por (ano, mes), o maior n_cod_unicos observado no mes
                 (evita subcontar dia com arquivo parcial no espelho)

Uso:
  python contar_linhas.py --base coleta_curitiba
  python contar_linhas.py --base coleta_curitiba --saida outputs/linhas_ano

Saidas:
  pordia_linhas.csv   (data, ano, mes, n_registros, n_cod_unicos)
  pormes_linhas.csv   (ano, mes, dias_com_arquivo, n_mes_max)
  porano_linhas.csv   (ano, n_meses_cobertos, mediana_n_mes_max, max_n_mes_max)
"""

import argparse
import io
import json
import lzma
import re
import sys
from pathlib import Path

import pandas as pd

RE_LINHAS = re.compile(r"^(\d{4})_(\d{2})_(\d{2})_linhas\.json(\.xz)?$")


def abrir_utf8(path: Path):
    abre = lzma.open if path.suffix == ".xz" else open
    raw = abre(path, "rb")
    return io.TextIOWrapper(raw, encoding="utf-8-sig")


def ler_json(path: Path):
    with abrir_utf8(path) as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return [json.loads(l) for l in texto.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="coleta_curitiba")
    ap.add_argument("--saida", default="outputs/linhas_ano")
    args = ap.parse_args()

    arquivos = []
    for p in sorted(Path(args.base).rglob("*_linhas.json*")):
        m = RE_LINHAS.match(p.name)
        if m:
            arquivos.append((p, f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
                             int(m.group(1)), int(m.group(2))))
    print(f"{len(arquivos)} arquivos *_linhas.json* encontrados em {args.base}")
    if not arquivos:
        sys.exit(1)

    linhas_dia = []
    for i, (p, data, ano, mes) in enumerate(arquivos, 1):
        try:
            obj = ler_json(p)
            df = pd.DataFrame(obj)
            n_reg = len(df)
            n_cod = df["COD"].astype(str).str.strip().nunique() if "COD" in df.columns else pd.NA
        except Exception as e:
            n_reg, n_cod = -1, -1
            print(f"  [erro] {p.name}: {e}")
        linhas_dia.append({"data": data, "ano": ano, "mes": mes,
                           "n_registros": n_reg, "n_cod_unicos": n_cod})
        if i % 25 == 0 or i == len(arquivos):
            print(f"[{i}/{len(arquivos)}] ate {data}")

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    dia_df = pd.DataFrame(linhas_dia)
    dia_df = dia_df[dia_df.n_cod_unicos > 0]  # ignora leituras ruins
    dia_df.to_csv(saida / "pordia_linhas.csv", index=False)

    mes_df = (dia_df.groupby(["ano", "mes"])
                    .agg(dias_com_arquivo=("data", "nunique"),
                         n_mes_max=("n_cod_unicos", "max"))
                    .reset_index())
    mes_df.to_csv(saida / "pormes_linhas.csv", index=False)

    ano_df = (mes_df.groupby("ano")
                    .agg(n_meses_cobertos=("mes", "nunique"),
                         mediana_n_mes_max=("n_mes_max", "median"),
                         max_n_mes_max=("n_mes_max", "max"))
                    .reset_index())
    ano_df.to_csv(saida / "porano_linhas.csv", index=False)

    print("\nLinhas unicas por ano (maximo mensal):")
    print(ano_df.to_string(index=False))
    print(f"\nGravados em {saida}: pordia_linhas.csv, pormes_linhas.csv, porano_linhas.csv")


if __name__ == "__main__":
    main()