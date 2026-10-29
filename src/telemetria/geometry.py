"""Funções geométricas para coordenadas geográficas."""

import numpy as np
import pandas as pd

RAIO_TERRA_METROS = 6_371_000.0


def calcular_distancia_haversine(
    lat1: pd.Series,
    lon1: pd.Series,
    lat2: pd.Series,
    lon2: pd.Series,
) -> pd.Series:
    """Calcula a distância geodésica aproximada em metros.

    As entradas podem conter valores ausentes. Nesses casos, a saída correspondente
    será `NaN`, preservando o alinhamento do índice.
    """
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = [
        np.radians(serie.astype(float)) for serie in (lat1, lon1, lat2, lon2)
    ]

    a = (
        np.sin((lat2_rad - lat1_rad) / 2) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin((lon2_rad - lon1_rad) / 2) ** 2
    )
    a = np.clip(a, 0.0, 1.0)
    distancia = 2 * RAIO_TERRA_METROS * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return pd.Series(distancia, index=lat1.index, name="DISTANCIA_METROS")
