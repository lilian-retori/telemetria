"""Criacao de metricas de movimento a partir da telemetria."""

import numpy as np
import pandas as pd

from .config import Config
from .geometry import calcular_distancia_haversine


def adicionar_metricas_movimento(
    telemetria: pd.DataFrame, config: Config
) -> pd.DataFrame:
    """Calcula tempo, distancia, velocidade e causa de invalidacao por par.

    VELOCIDADE_KMH so existe entre pares do mesmo veiculo com intervalo
    maior que zero, dentro do maximo aceito e abaixo do limite plausivel.
    MOTIVO_PAR_INVALIDO documenta por que o restante foi descartado.
    """
    df = telemetria.sort_values(["VEIC", "DTHR"]).copy().reset_index(drop=True)
    grupo = df.groupby("VEIC", sort=False)

    df["DTHR_ANTERIOR"] = grupo["DTHR"].shift()
    df["LAT_ANTERIOR"] = grupo["LAT"].shift()
    df["LON_ANTERIOR"] = grupo["LON"].shift()
    df["INTERVALO_SEG"] = (df["DTHR"] - df["DTHR_ANTERIOR"]).dt.total_seconds()

    df["DISTANCIA_METROS"] = calcular_distancia_haversine(
        df["LAT_ANTERIOR"],
        df["LON_ANTERIOR"],
        df["LAT"],
        df["LON"],
    )

    df["INTERVALO_VALIDO"] = df["INTERVALO_SEG"].gt(0) & df["INTERVALO_SEG"].le(
        config.max_intervalo_seg
    )

    denominador = df["INTERVALO_SEG"].where(df["INTERVALO_VALIDO"])
    df["VELOCIDADE_KMH"] = df["DISTANCIA_METROS"].div(denominador).mul(3.6)

    df["MOTIVO_PAR_INVALIDO"] = pd.Series(pd.NA, index=df.index, dtype="string")

    df.loc[df["DTHR_ANTERIOR"].isna(), "MOTIVO_PAR_INVALIDO"] = (
        "primeira_posicao_veiculo"
    )
    df.loc[
        df["DTHR_ANTERIOR"].notna() & df["INTERVALO_SEG"].le(0),
        "MOTIVO_PAR_INVALIDO",
    ] = "intervalo_zero_ou_negativo"
    df.loc[
        df["DTHR_ANTERIOR"].notna()
        & df["INTERVALO_SEG"].gt(config.max_intervalo_seg),
        "MOTIVO_PAR_INVALIDO",
    ] = "intervalo_acima_limite"
    df.loc[
        df["MOTIVO_PAR_INVALIDO"].isna()
        & (df["VELOCIDADE_KMH"] > config.max_velocidade_kmh),
        "MOTIVO_PAR_INVALIDO",
    ] = "velocidade_acima_limite"

    df["VELOCIDADE_VALIDA"] = (
        df["MOTIVO_PAR_INVALIDO"].isna()
        & np.isfinite(df["VELOCIDADE_KMH"])
    )

    df.loc[~df["VELOCIDADE_VALIDA"], "VELOCIDADE_KMH"] = np.nan

    df["CLASSE_VELOCIDADE"] = pd.NA
    valida = df["VELOCIDADE_VALIDA"]
    df.loc[
        valida & (df["VELOCIDADE_KMH"] <= config.limiar_quase_parada_kmh),
        "CLASSE_VELOCIDADE",
    ] = "quase_parada"
    df.loc[
        valida
        & (df["VELOCIDADE_KMH"] > config.limiar_quase_parada_kmh)
        & (df["VELOCIDADE_KMH"] < config.limiar_baixa_velocidade_kmh),
        "CLASSE_VELOCIDADE",
    ] = "baixa_velocidade"
    df.loc[
        valida & (df["VELOCIDADE_KMH"] >= config.limiar_baixa_velocidade_kmh),
        "CLASSE_VELOCIDADE",
    ] = "velocidade_normal"

    df["BAIXA_VELOCIDADE"] = valida & (
        df["VELOCIDADE_KMH"] < config.limiar_baixa_velocidade_kmh
    )
    return df