#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snap_lote.py (v2 - correcao de calendario)
Snap em lote multi-dia.

CORRECAO vs versao original:
  A auditoria de calendario mostrou que o arquivo AAAA_MM_DD_veiculos.json.xz
  contem GPS do dia operacional AAAA_MM_DD - 1 (deslocamento sistematico).
  Portanto, as trajetorias sao nomeadas pela DATA DO DTHR (dia operacional),
  nao pelo nome do arquivo. Arquivos contendo 2 dias geram as duas datas.

  O shape continua buscado pela data do ARQUIVO (mesma janela de coleta do
  GPS, convencao uniforme do espelho C3SL). [Hipotese verificada apenas para
  GPS; reavalie se surgir divergencia de itinerario.]

Retomada: pula (data_operacional, linha) cujo segmentos_*.csv ja existe na saida.

Exemplos:
  python snap_lote.py --de 2017-03-01 --ate 2017-03-31 --linhas 303 --base coleta_curitiba\\2017 --telemetria coleta_curitiba\\2017
  python snap_lote.py --de 2026-09-01 --ate 2026-09-30 --arquivo-linhas linhas_ganchinho.txt --base coleta_curitiba\\2026 --telemetria coleta_curitiba\\2026
"""
import argparse
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from snap_trajetorias import (carregar_shapes, carregar_telemetria,
                              cortar_viagens, resumir_segmentos, snap_pontos)

RE_ARQ = re.compile(r"^(\d{4})_(\d{2})_(\d{2})_veiculos\.json\.xz$")
RAIZ = Path(__file__).resolve().parent
BASE_EXT = RAIZ / "data" / "external"
BASE_RAW = RAIZ / "data" / "raw"
SAIDA_PADRAO = RAIZ / "outputs" / "trajetorias"


def descobrir_arquivos(pasta_raw: Path, de: str, ate: str):
    datas = []
    for p in sorted(pasta_raw.rglob("*_veiculos.json.xz")):
        m = RE_ARQ.match(p.name)
        if m:
            data_arq = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            if de <= data_arq <= ate:
                datas.append((data_arq, p))
    return datas


def carregar_linhas(args):
    if args.arquivo_linhas:
        txt = Path(args.arquivo_linhas).read_text(encoding="utf-8")
        linhas = [l.strip() for l in txt.splitlines() if l.strip() and not l.startswith("#")]
    else:
        linhas = args.linhas or []
    return [str(l).strip() for l in linhas]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--de", required=True, help="primeira data AAAA-MM-DD (do NOME do arquivo)")
    ap.add_argument("--ate", required=True, help="ultima data AAAA-MM-DD (do NOME do arquivo)")
    ap.add_argument("--linhas", nargs="+", help="CODs, ex: 250 550 603")
    ap.add_argument("--arquivo-linhas", help="txt com um COD por linha")
    ap.add_argument("--base", default=str(BASE_EXT))
    ap.add_argument("--telemetria", default=str(BASE_RAW))
    ap.add_argument("--saida", default=str(SAIDA_PADRAO))
    args = ap.parse_args()

    linhas = carregar_linhas(args)
    if not linhas:
        sys.exit("Informe --linhas ou --arquivo-linhas.")

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    log_path = saida / "snap_lote.log"

    def log(msg):
        linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        print(linha)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(linha + "\n")

    datas = descobrir_arquivos(Path(args.telemetria), args.de, args.ate)
    log(f"Arquivos descobertos: {len(datas)} ({args.de}..{args.ate})")
    if not datas:
        sys.exit("Nenhum arquivo de telemetria no intervalo. Confira a pasta e o padrao de nome.")

    resumo = []
    resumo_csv = saida / "resumo_snap_lote.csv"
    if resumo_csv.exists():
        resumo = pd.read_csv(resumo_csv).to_dict("records")

    cache_shapes = {}
    for data_arq, arq in datas:
        try:
            df = carregar_telemetria(arq)
        except Exception as e:
            log(f"{arq.name}: FALHA ao ler telemetria ({e}); pulando arquivo")
            continue
        try:
            if data_arq not in cache_shapes:
                cache_shapes[data_arq] = carregar_shapes(Path(args.base), data_arq)
            shapes = cache_shapes[data_arq]
        except Exception as e:
            log(f"{arq.name}: FALHA ao ler shape ({e}); pulando arquivo")
            continue

        df["data_op"] = df["datahora"].dt.strftime("%Y-%m-%d")
        por_dia = df.groupby("data_op")
        log(f"{arq.name}: {len(df)} registros; dias operacionais: "
            + ", ".join(f"{d} ({len(g)})" for d, g in por_dia))

        for data_op, ddf in por_dia:
            pendentes = [l for l in linhas if not (saida / f"segmentos_l{l}_{data_op}.csv").exists()]
            if not pendentes:
                log(f"  {data_op}: todas as linhas ja processadas")
                continue
            for linha in pendentes:
                try:
                    sub = ddf[ddf["linha"] == linha]
                    if sub.empty:
                        log(f"  {linha}: sem registros em {data_op} (origem {arq.name})")
                        resumo.append({"data": data_op, "data_arquivo": data_arq, "linha": linha,
                                       "registros": 0, "aceitos": 0, "snap_pct": 0.0,
                                       "status": "sem_registros"})
                        continue
                    variantes = {k: v for k, v in shapes.items() if k[0] == linha}
                    if not variantes:
                        log(f"  {linha}: sem shape; pulando")
                        resumo.append({"data": data_op, "data_arquivo": data_arq, "linha": linha,
                                       "registros": len(sub), "aceitos": 0, "snap_pct": 0.0,
                                       "status": "sem_shape"})
                        continue
                    melhor = None
                    for (cod, shp), sh in variantes.items():
                        sn = snap_pontos(sub, sh)
                        if melhor is None or len(sn) > melhor[1]:
                            melhor = (shp, len(sn), sn)
                    shp, n_aceitos, sn = melhor
                    pct = 100 * n_aceitos / len(sub)
                    if sn.empty:
                        log(f"  {linha}: 0 aceitos em {data_op} (variante {shp})")
                        resumo.append({"data": data_op, "data_arquivo": data_arq, "linha": linha,
                                       "registros": len(sub), "aceitos": 0, "snap_pct": 0.0,
                                       "status": "vazio"})
                        continue
                    sn = cortar_viagens(sn)
                    sn.to_csv(saida / f"trajetoria_l{linha}_{data_op}.csv", index=False)
                    resumir_segmentos(sn).to_csv(saida / f"segmentos_l{linha}_{data_op}.csv", index=False)
                    log(f"  {linha}: {len(sub)} -> {n_aceitos} ({pct:.0f}%) variante {shp} "
                        f"[op {data_op} <- arq {data_arq}]")
                    resumo.append({"data": data_op, "data_arquivo": data_arq, "linha": linha,
                                   "registros": len(sub), "aceitos": n_aceitos,
                                   "snap_pct": round(pct, 1), "status": "ok"})
                except Exception as e:
                    log(f"  {linha}: ERRO INESPERADO em {data_op}: {e}")
                    traceback.print_exc()
                    resumo.append({"data": data_op, "data_arquivo": data_arq, "linha": linha,
                                   "registros": -1, "aceitos": -1, "snap_pct": -1.0,
                                   "status": "erro"})
            pd.DataFrame(resumo).to_csv(resumo_csv, index=False)

    log("Concluido. Resumo consolidado em resumo_snap_lote.csv")


if __name__ == "__main__":
    main()