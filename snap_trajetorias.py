#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snap_trajetorias.py
Snap GPS -> shape por linha, etapa 4 (projeto Curitiba).

Formatos confirmados pelas amostras de 15/10/2026:
  Telemetria (NDJSON por linha, em data/raw/AAAA_MM_DD_veiculos.json.xz):
      {"VEIC":"BA011","LAT":"-25,428233","LON":"-49,272261",
       "DTHR":"08/09/2026 23:59:57","COD_LINHA":"170"}
      ATENCAO: LAT/LON usam VIRGULA como separador decimal; DTHR eh dd/mm/aaaa.
      Sem velocidade: calculada por pares consecutivos do mesmo veiculo.
  Shapes (data/external/AAAA_MM_DD_shapeLinha.json.xz): campos SHP, LAT, LON, COD.
      COD = linha; SHP = itinerario (ida/volta/variantes).

Modos:
  --listar-linhas TEXTO     procura linhas por nome (ex.: --listar-linhas PINHEIRINHO)
  --amostra ARQ             espia os campos de um arquivo de telemetria
  processamento             python snap_trajetorias.py --datas 2026-09-09 --linhas 170 250

Observacao de fronteira: o arquivo AAAA_MM_DD contem registros com DTHR do
dia seguinte (captacao noturna cruza a virada); o script corta por dia do DTHR.
"""

import argparse
import io
import json
import lzma
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

TOLERANCIA_M = 60.0
SEGMENTO_M = 100.0
LENTO_KMH = 15.0
FOLEGA_MIN = 15
RAIO_TERRA = 6371000.0
VEL_MAX_KMH = 140.0


def abrir_utf8(path: Path):
    abre = lzma.open if path.suffix == ".xz" else open
    raw = abre(path, "rb")
    return io.TextIOWrapper(raw, encoding="utf-8-sig")


def ler_json_ou_ndjson(path: Path):
    with abrir_utf8(path) as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        if "Extra data" not in str(e):
            raise
        return [json.loads(l) for l in texto.splitlines() if l.strip()]


def amostra_telemetria(path: Path, n=3):
    with abrir_utf8(path) as f:
        vistos = 0
        for i, linha in enumerate(f):
            txt = linha.strip()
            if not txt:
                continue
            print(f"linha {i+1} crua: {txt[:300]}")
            vistos += 1
            if vistos >= n:
                break


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).upper()


def listar_linhas(base: Path, termo: str):
    arquivos = sorted(p for p in base.glob("*linhas.json.xz") if " (1)" not in p.name)
    if not arquivos:
        sys.exit("Nenhum arquivo *linhas.json.xz encontrado na pasta externa.")
    arq = arquivos[-1]
    dados = ler_json_ou_ndjson(arq)
    df = pd.DataFrame(dados)
    t = sem_acento(termo)
    achados = df[df["NOME"].map(sem_acento).str.contains(t, na=False)]
    print(f"Fonte: {arq.name} | {len(df)} linhas no catalogo")
    if achados.empty:
        print(f"Nenhuma linha com '{termo}' no nome.")
    else:
        print(achados[["COD", "NOME", "CATEGORIA_SERVICO"]].to_string(index=False))


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lat2 = np.radians(np.asarray(lat1)), np.radians(np.asarray(lat2))
    dlat = lat2 - lat1
    dlon = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def carregar_telemetria(path: Path) -> pd.DataFrame:
    obj = ler_json_ou_ndjson(path)
    if isinstance(obj, dict):
        obj = [r for chave, valor in obj.items()
               for r in (valor if isinstance(valor, list) else [valor]) if isinstance(r, dict)]
    df = pd.DataFrame(obj).rename(columns={
        "VEIC": "veiculo", "LAT": "lat", "LON": "lon",
        "DTHR": "datahora", "COD_LINHA": "linha"})
    if "veiculo" not in df.columns or "COD_LINHA" in df.columns:
        pass
    faltam = [c for c in ["veiculo", "lat", "lon", "datahora", "linha"] if c not in df.columns]
    if faltam:
        raise KeyError(f"Campos ausentes em {path.name}: {faltam}")
    # separador decimal virgula -> ponto
    for col in ("lat", "lon"):
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df["datahora"] = pd.to_datetime(df["datahora"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df["linha"] = df["linha"].astype(str).str.strip()
    df = df.dropna(subset=["lat", "lon", "datahora"])
    df = df[df["lat"].between(-26.2, -24.6) & df["lon"].between(-50.0, -48.4)]
    df = df.sort_values(["veiculo", "datahora"]).reset_index(drop=True)

    # velocidade calculada por pares consecutivos do mesmo veiculo
    g = df.groupby("veiculo", sort=False)
    dlat = df["lat"]
    dist = haversine_m(dlat, df["lon"], g["lat"].shift(), g["lon"].shift())
    dt = g["datahora"].diff().dt.total_seconds()
    df["vel_kmh"] = dist / dt * 3.6
    df.loc[(dt <= 0) | (dt > 3600) | (df["vel_kmh"] > VEL_MAX_KMH), "vel_kmh"] = np.nan
    return df


def carregar_shapes(base: Path, data_ref: str) -> dict:
    alvo = base / f"{data_ref.replace('-', '_')}_shapeLinha.json.xz"
    if not alvo.exists():
        candidatos = [c for c in sorted(base.glob("*shapeLinha*.json.xz")) if " (1)" not in c.name]
        if not candidatos:
            raise FileNotFoundError(f"Nenhum shapeLinha em {base}")
        alvo = candidatos[-1]
        print(f"  shape do dia nao encontrado; usando {alvo.name}")
    obj = ler_json_ou_ndjson(alvo)
    df = pd.DataFrame(obj)
    for c in ("COD", "SHP"):
        df[c] = df[c].astype(str).str.strip()
    df["_lat"] = pd.to_numeric(df["LAT"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df["_lon"] = pd.to_numeric(df["LON"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["_lat", "_lon"])
    out = {}
    for (cod, shp), g in df.groupby(["COD", "SHP"], sort=False):
        if len(g) >= 2:
            out[(cod, shp)] = g[["_lat", "_lon"]].reset_index(drop=True)
    print(f"Shapes: {len(out)} itinerarios, {df['COD'].nunique()} linhas ({alvo.name})")
    return out


def snap_pontos(df_linha: pd.DataFrame, shape: pd.DataFrame):
    slat = shape["_lat"].to_numpy(); slon = shape["_lon"].to_numpy()
    lat1, lon1 = slat[:-1], slon[:-1]
    lat2, lon2 = slat[1:], slon[1:]
    seg_comp = haversine_m(lat1, lon1, lat2, lon2)
    s_acum = np.concatenate([[0], np.cumsum(seg_comp)])
    lat0 = np.radians(slat[0])

    def xy(lat, lon):
        lat, lon = np.asarray(lat), np.asarray(lon)
        return (np.radians(lon - slon[0]) * np.cos(lat0) * RAIO_TERRA,
                np.radians(lat - slat[0]) * RAIO_TERRA)
    ax, ay = xy(lat1, lon1); bx, by = xy(lat2, lon2)
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    px, py = xy(df_linha["lat"].to_numpy(), df_linha["lon"].to_numpy())
    melhor_d = np.full(len(px), np.inf)
    melhor_s = np.zeros(len(px))
    for i in range(len(ax)):
        if d2[i] == 0:
            continue
        t = np.clip(((px - ax[i]) * dx[i] + (py - ay[i]) * dy[i]) / d2[i], 0, 1)
        dist = np.hypot(px - (ax[i] + t * dx[i]), py - (ay[i] + t * dy[i]))
        ok = dist < melhor_d
        melhor_d[ok] = dist[ok]
        melhor_s[ok] = s_acum[i] + t[ok] * seg_comp[i]
    res = df_linha.copy()
    res["dist_ao_shape_m"] = melhor_d
    res["s_m"] = melhor_s
    return res[res["dist_ao_shape_m"] <= TOLERANCIA_M]


def cortar_viagens(df: pd.DataFrame) -> pd.DataFrame:
    partes = []
    for veic, g in df.groupby("veiculo"):
        g = g.sort_values("datahora")
        gap = g["datahora"].diff().dt.total_seconds().gt(FOLEGA_MIN * 60)
        partes.append(g.assign(viagem=f"{veic}_{gap.cumsum()}"))
    return pd.concat(partes, ignore_index=True) if partes else df


def resumir_segmentos(df: pd.DataFrame):
    df = df.copy()
    df["segmento"] = (df["s_m"] // SEGMENTO_M).astype(int)
    agg = df.groupby("segmento").agg(
        n=("s_m", "size"), veiculos=("veiculo", pd.Series.nunique),
        viagens=("viagem", pd.Series.nunique), s_ini_m=("s_m", "min"),
        vel_mediana_kmh=("vel_kmh", "median")).reset_index()
    pct = df.groupby("segmento")["vel_kmh"].apply(lambda s: (s < LENTO_KMH).mean() * 100).rename("pct_lentos")
    return agg.merge(pct, on="segmento")

from pathlib import Path

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base_padrao = str(Path(__file__).resolve().parent)
    ap.add_argument("--base", default=base_padrao + r"\data\external")
    ap.add_argument("--telemetria", default=base_padrao + r"\data\raw")
    ap.add_argument("--saida", default=base_padrao + r"\outputs\trajetorias")
    ap.add_argument("--datas", nargs="+")
    ap.add_argument("--linhas", nargs="+", help="COD_LINHA da telemetria, ex.: --linhas 170 250")
    ap.add_argument("--amostra", help="arquivo de telemetria para espionar campos")
    ap.add_argument("--listar-linhas", metavar="TEXTO", help="busca linha por nome no catalogo")
    args = ap.parse_args()

    if args.amostra:
        amostra_telemetria(Path(args.amostra))
        return
    if args.listar_linhas:
        listar_linhas(Path(args.base), args.listar_linhas)
        return
    if not args.datas or not args.linhas:
        sys.exit("Informe --datas e --linhas (ex.: --datas 2026-09-09 --linhas 170). Para achar o COD use --listar-linhas NOME.")

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    for data in args.datas:
        arq = Path(args.telemetria) / f"{data.replace('-', '_')}_veiculos.json.xz"
        if not arq.exists():
            print(f"{data}: {arq.name} nao encontrado; pulando")
            continue
        print(f"\n=== {data} ===")
        df = carregar_telemetria(arq)
        print(f"  {len(df)} registros limpos | {df['linha'].nunique()} linhas | {df['veiculo'].nunique()} veiculos")
        shapes = carregar_shapes(Path(args.base), data)
        for linha in args.linhas:
            sub = df[df["linha"] == linha]
            if sub.empty:
                print(f"  linha {linha}: sem registros no dia")
                continue
            variantes = {k: v for k, v in shapes.items() if k[0] == linha}
            if not variantes:
                print(f"  linha {linha}: sem shape; pulando")
                continue
            melhor = None
            for (cod, shp), sh in variantes.items():
                sn = snap_pontos(sub, sh)
                if melhor is None or len(sn) > melhor[1]:
                    melhor = (shp, len(sn), sn)
            shp, _, sn = melhor
            pct = 100 * len(sn) / len(sub)
            ok_meta = pct >= 80
            print(f"  linha {linha} (itinerario {shp}): {len(sub)} pts -> {len(sn)} aceitos ({pct:.0f}%){'' if ok_meta else ' <-- ABAIXO DA META 80%'}")
            if sn.empty:
                continue
            sn = cortar_viagens(sn)
            sn.to_csv(saida / f"trajetoria_l{linha}_{data}.csv", index=False)
            resumir_segmentos(sn).to_csv(saida / f"segmentos_l{linha}_{data}.csv", index=False)
            print(f"    gravados trajetoria_l{linha}_{data}.csv e segmentos_l{linha}_{data}.csv")
    print("\nConcluido. Envie um segmentos_*.csv para a validacao.")


if __name__ == "__main__":
    main()