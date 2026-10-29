#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auditoria_calendario.py
Audita o calendario dos arquivos de telemetria antes de qualquer processamento.

Para cada *_veiculos.json.xz encontrado no intervalo informado, mede:
  - data do nome do arquivo (AAAA_MM_DD) vs datas internas (DTHR)
  - primeiro/ultimo horario interno
  - registros por data interna
  - deslocamento data-nome -> data dominante (em dias)
  - total de registros, linhas e veiculos unicos
  - se o arquivo contem mais de um dia

Saidas (--saida):
  auditoria_calendario_detalhe.csv  (arquivo x data interna)
  auditoria_calendario_resumo.csv   (1 linha por arquivo)

Uso:
  python auditoria_calendario.py --de 2017-03-01 --ate 2017-03-31 --base coleta_curitiba
  python auditoria_calendario.py --de 2026-09-01 --ate 2026-09-30 --base coleta_curitiba
"""
import argparse
import io
import json
import lzma
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def abrir_utf8(path: Path):
    abre = lzma.open if str(path).endswith(".json.xz") else open
    raw = abre(path, "rb")
    return io.TextIOWrapper(raw, encoding="utf-8-sig")


def iter_registros(path: Path):
    """Le registro a registro (JSON ou NDJSON), sem carregar tudo de uma vez."""
    with abrir_utf8(path) as f:
        texto = f.read()
    try:
        obj = json.loads(texto)
        if isinstance(obj, list):
            for r in obj:
                if isinstance(r, dict):
                    yield r
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    for r in v:
                        if isinstance(r, dict):
                            yield r
        return
    except json.JSONDecodeError:
        pass
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            r = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            yield r


def auditar_arquivo(path: Path):
    nome = path.name  # ex.: 2017_03_02_veiculos.json.xz
    data_nome = f"{nome[0:4]}-{nome[5:7]}-{nome[8:10]}"

    dts, linhas, veics = [], set(), set()
    for r in iter_registros(path):
        dt = r.get("DTHR")
        if dt:
            dts.append(dt)
        l = r.get("COD_LINHA")
        if l:
            linhas.add(str(l).strip())
        v = r.get("VEIC")
        if v:
            veics.add(str(v).strip())

    s = pd.to_datetime(pd.Series(dts), format="%d/%m/%Y %H:%M:%S", errors="coerce").dropna()
    detalhe = s.dt.strftime("%Y-%m-%d").value_counts().sort_index()

    linhas_det = []
    for data_int, n in detalhe.items():
        delta = (pd.Timestamp(data_int) - pd.Timestamp(data_nome)).days if n > 0 else None
        linhas_det.append({
            "arquivo": nome, "data_nome": data_nome, "data_interna": data_int,
            "registros": int(n), "deslocamento_dias": int(delta) if delta is not None else None})
    dominante = detalhe.idxmax() if len(detalhe) else None
    resumo = {
        "arquivo": nome, "data_nome": data_nome,
        "registros_total": int(s.size),
        "registros_sem_data": int(dts.__len__() - s.size),
        "min_dthr": str(s.min()) if len(s) else None,
        "max_dthr": str(s.max()) if len(s) else None,
        "n_linhas": len(linhas), "n_veiculos": len(veics),
        "n_dias_internos": int(len(detalhe)),
        "data_dominante": dominante,
        "deslocamento_dominante_dias":
            (pd.Timestamp(dominante) - pd.Timestamp(data_nome)).days if dominante else None,
    }
    return resumo, linhas_det


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--de", required=True)
    ap.add_argument("--ate", required=True)
    ap.add_argument("--base", default="coleta_curitiba", help="raiz com subpastas por ano")
    ap.add_argument("--saida", default="outputs/auditoria_calendario")
    args = ap.parse_args()

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for p in sorted(Path(args.base).rglob("*_veiculos.json*")):
        n = p.name
        if len(n) >= 10 and n[:4].isdigit() and n[5:7].isdigit():
            data = f"{n[0:4]}-{n[5:7]}-{n[8:10]}"
            if args.de <= data <= args.ate:
                arquivos.append(p)
    print(f"{len(arquivos)} arquivos no intervalo {args.de}..{args.ate}")
    if not arquivos:
        sys.exit(1)

    resumos, detalhes = [], []
    for i, p in enumerate(arquivos, 1):
        try:
            resumo, det = auditar_arquivo(p)
        except Exception as e:
            resumo, det = {"arquivo": p.name, "data_nome": None, "erro": str(e)}, []
        resumo["ordem"] = i
        resumos.append(resumo); detalhes.extend(det)
        print(f"[{i}/{len(arquivos)}] {p.name}: nome={resumo.get('data_nome')} "
              f"dominante={resumo.get('data_dominante')} "
              f"desl={resumo.get('deslocamento_dominante_dias')} "
              f"dias={resumo.get('n_dias_internos')} regs={resumo.get('registros_total')}")

    df_r = pd.DataFrame(resumos)
    df_d = pd.DataFrame(detalhes)
    df_r.to_csv(saida / "auditoria_calendario_resumo.csv", index=False)
    df_d.to_csv(saida / "auditoria_calendario_detalhe.csv", index=False)

    ok = df_r.dropna(subset=["deslocamento_dominante_dias"])
    hist = ok["deslocamento_dominante_dias"].value_counts().sort_index()
    print(" Distribuicao do deslocamento data-nome -> data dominante (dias):")
    print(hist.to_string())
    multi = df_r[df_r.get("n_dias_internos", 0) > 1] if "n_dias_internos" in df_r else df_r.iloc[0:0]
    if len(multi):
        print(f" ATENCAO: {len(multi)} arquivos com mais de um dia interno:")
    print(multi[["arquivo", "n_dias_internos", "data_dominante"]].to_string(index=False))
    print(f" Gravados: {saida/'auditoria_calendario_resumo.csv'} e detalhe correspondente.")


if __name__ == "__main__":
    main()