"""Gera apenas o perfis_horarios_top20.csv, sem rodar a auditoria inteira.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\gerar_perfis_top20.py

Pre-requisitos (ja existem se voce rodou a auditoria/reprocessamento):
- outputs/comparativo/auditoria_top20.csv
- outputs/comparativo/resumo_diario.csv   (colunas: data, tipo_dia)
- outputs/AAAA-MM-DD/tables/telemetria_com_metricas.csv

Saida unica:
- outputs/comparativo/auditoria/perfis_horarios_top20.csv

Nota: auditoria_espacial.py tambem gera este arquivo. Use-o para refazer
apenas o perfil sem recalcular todo o pipeline.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path("outputs")
RAIZ_COMP = RAIZ / "comparativo"
RAIZ_AUD = RAIZ_COMP / "auditoria"
PADRAO_PASTA_DIA = re.compile(r"\d{4}-\d{2}-\d{2}$")
TAMANHO_CELULA = 0.002
LIMIAR_KMH = 15


def celula_de(lat: float, lon: float) -> str:
    return (
        f"{np.floor(lat / TAMANHO_CELULA) * TAMANHO_CELULA:.6f}_"
        f"{np.floor(lon / TAMANHO_CELULA) * TAMANHO_CELULA:.6f}"
    )


def ler_top20() -> pd.DataFrame:
    arq = RAIZ_AUD / "auditoria_top20.csv"
    if not arq.exists():
        raise FileNotFoundError(f"{arq} nao existe. Rode auditoria_espacial.py primeiro.")
    df = pd.read_csv(arq)
    faltam = {"GARGALO", "lat_centro", "lon_centro"} - set(df.columns)
    if faltam:
        raise SystemExit(f"{arq} esta sem as colunas {sorted(faltam)}")
    return df


def ler_tipos_de_dia() -> dict:
    arq = RAIZ_COMP / "resumo_diario.csv"
    if not arq.exists():
        raise SystemExit(f"{arq} nao existe. Consulte o que gera resumo_diario.csv.")
    df = pd.read_csv(arq)
    col_data = next((c for c in df.columns if c.lower() == "data"), None)
    col_tipo = next((c for c in df.columns if c.lower() == "tipo_dia"), None)
    if not col_data or not col_tipo:
        raise SystemExit(f"{arq} precisa ter as colunas data e tipo_dia")
    df["data"] = pd.to_datetime(df[col_data], errors="coerce").dt.date.astype(str)
    return dict(zip(df["data"], df[col_tipo]))


def pastas_validas() -> list[Path]:
    return [
        p for p in RAIZ.iterdir()
        if p.is_dir()
        and PADRAO_PASTA_DIA.fullmatch(p.name)
        and (p / "tables" / "telemetria_com_metricas.csv").exists()
    ]


def gerar() -> Path:
    top20 = ler_top20()
    pastas = pastas_validas()
    tipos = ler_tipos_de_dia()

    mapa_celula = {}
    for r in top20.itertuples():
        chave = celula_de(r.lat_centro, r.lon_centro)
        mapa_celula[chave] = r.GARGALO
    celulas = set(mapa_celula)

    ocorrencias = []
    datas_processadas = []
    for pasta in pastas:
        arq = pasta / "tables" / "telemetria_com_metricas.csv"
        df = pd.read_csv(
            arq, usecols=lambda c: c in {"VEIC", "DTHR", "LAT", "LON", "VELOCIDADE_KMH"}
        )
        if len(df) == 0:
            continue
        df["DTHR"] = pd.to_datetime(df["DTHR"], errors="coerce", format="ISO8601")
        resto = df["DTHR"].isna()
        if resto.any():
            df.loc[resto, "DTHR"] = pd.to_datetime(
                df.loc[resto, "DTHR"], format="%d/%m/%Y %H:%M:%S", errors="coerce"
            )
        df = df.dropna(subset=["DTHR", "LAT", "LON", "VELOCIDADE_KMH"])
        df = df.loc[df["VELOCIDADE_KMH"] < LIMIAR_KMH]
        if df.empty:
            continue

        data = df["DTHR"].dt.date.iloc[0].isoformat()
        datas_processadas.append(data)
        df["CELULA"] = [celula_de(a, b) for a, b in zip(df["LAT"], df["LON"])]
        df = df.loc[df["CELULA"].isin(celulas)]
        if df.empty:
            continue

        df["GARGALO"] = df["CELULA"].map(mapa_celula)
        df["TIPO_DIA"] = tipos.get(data, "dia_util")
        df["HORA_INT"] = df["DTHR"].dt.hour
        df["DATA"] = data
        ocorrencias.append(df[["GARGALO", "TIPO_DIA", "HORA_INT", "DATA"]])

    if not ocorrencias:
        raise SystemExit("Nenhuma observacao lenta caiu nas celulas do Top 20.")

    ocorr = pd.concat(ocorrencias, ignore_index=True)
    print(f"Observacoes lentas agregadas no Top 20: {len(ocorr):,}")

    contagem_dias = {}
    for data in set(datas_processadas):
        t = tipos.get(data, "dia_util")
        contagem_dias[t] = contagem_dias.get(t, 0) + 1

    perfil = (
        ocorr.groupby(["GARGALO", "TIPO_DIA", "HORA_INT"])
        .agg(obs=("HORA_INT", "size"))
        .reset_index()
    )
    perfil["obs_por_dia"] = perfil.apply(
        lambda r: r["obs"] / max(contagem_dias.get(r["TIPO_DIA"], 1), 1), axis=1
    )

    saida = RAIZ_AUD / "perfis_horarios_top20.csv"
    perfil.to_csv(saida, index=False)
    print(f"Dias representados por tipo: {contagem_dias}")
    print(f"Salvo: {saida}")
    return saida


if __name__ == "__main__":
    gerar()