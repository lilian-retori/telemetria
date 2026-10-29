"""Métricas e agregações para análise de telemetria."""

import pandas as pd


def resumir_por_hora(telemetria: pd.DataFrame) -> pd.DataFrame:
    """Resume cobertura e baixa velocidade por hora de observação.

    Apenas pares com velocidade válida entram no denominador. O timestamp usado é
    o do segundo ponto do par, pois é nele que a velocidade calculada é registrada.
    """
    validos = telemetria.loc[telemetria["VELOCIDADE_VALIDA"]].copy()
    if validos.empty:
        return pd.DataFrame(
            columns=[
                "HORA",
                "observacoes_validas",
                "observacoes_baixa_velocidade",
                "percentual_baixa_velocidade",
                "velocidade_mediana_kmh",
                "veiculos_unicos",
            ]
        )

    validos["HORA"] = validos["DTHR"].dt.floor("h")
    resumo = validos.groupby("HORA", as_index=False).agg(
        observacoes_validas=("VELOCIDADE_KMH", "size"),
        observacoes_baixa_velocidade=("BAIXA_VELOCIDADE", "sum"),
        velocidade_mediana_kmh=("VELOCIDADE_KMH", "median"),
        veiculos_unicos=("VEIC", "nunique"),
    )
    resumo["percentual_baixa_velocidade"] = (
        100 * resumo["observacoes_baixa_velocidade"] / resumo["observacoes_validas"]
    )
    return resumo
