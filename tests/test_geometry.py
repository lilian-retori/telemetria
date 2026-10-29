import numpy as np
import pandas as pd

from telemetria.geometry import calcular_distancia_haversine


def test_distancia_zero_para_mesma_coordenada():
    lat = pd.Series([-25.4284])
    lon = pd.Series([-49.2733])

    resultado = calcular_distancia_haversine(lat, lon, lat, lon)

    assert np.isclose(resultado.iloc[0], 0.0)


def test_distancia_e_simetrica():
    lat_a = pd.Series([-25.4284])
    lon_a = pd.Series([-49.2733])
    lat_b = pd.Series([-25.4384])
    lon_b = pd.Series([-49.2633])

    ida = calcular_distancia_haversine(lat_a, lon_a, lat_b, lon_b)
    volta = calcular_distancia_haversine(lat_b, lon_b, lat_a, lon_a)

    assert ida.iloc[0] > 0
    assert np.isclose(ida.iloc[0], volta.iloc[0])


def test_distancia_preserva_nan():
    resultado = calcular_distancia_haversine(
        pd.Series([np.nan]),
        pd.Series([-49.2733]),
        pd.Series([-25.4284]),
        pd.Series([-49.2733]),
    )

    assert pd.isna(resultado.iloc[0])
