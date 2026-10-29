import pandas as pd

from telemetria.config import Config
from telemetria.features import adicionar_metricas_movimento


def test_primeiro_registro_nao_tem_velocidade():
    df = pd.DataFrame(
        {
            "VEIC": ["BA001"],
            "DTHR": pd.to_datetime(["2026-10-06 10:00:00"]),
            "LAT": [-25.4284],
            "LON": [-49.2733],
        }
    )

    resultado = adicionar_metricas_movimento(df, Config())

    assert not resultado.loc[0, "INTERVALO_VALIDO"]
    assert not resultado.loc[0, "VELOCIDADE_VALIDA"]
    assert pd.isna(resultado.loc[0, "VELOCIDADE_KMH"])


def test_nao_calcula_velocidade_para_tempo_zero():
    df = pd.DataFrame(
        {
            "VEIC": ["BA001", "BA001"],
            "DTHR": pd.to_datetime(["2026-10-06 10:00:00", "2026-10-06 10:00:00"]),
            "LAT": [-25.4284, -25.4294],
            "LON": [-49.2733, -49.2743],
        }
    )

    resultado = adicionar_metricas_movimento(df, Config())

    assert not resultado.loc[1, "INTERVALO_VALIDO"]
    assert not resultado.loc[1, "VELOCIDADE_VALIDA"]
    assert pd.isna(resultado.loc[1, "VELOCIDADE_KMH"])


def test_ordena_temporalmente_antes_de_calcular():
    df = pd.DataFrame(
        {
            "VEIC": ["BA001", "BA001"],
            "DTHR": pd.to_datetime(["2026-10-06 10:01:00", "2026-10-06 10:00:00"]),
            "LAT": [-25.4294, -25.4284],
            "LON": [-49.2743, -49.2733],
        }
    )

    resultado = adicionar_metricas_movimento(df, Config())

    assert resultado.loc[0, "DTHR"] < resultado.loc[1, "DTHR"]
    assert resultado.loc[1, "VELOCIDADE_VALIDA"]


def test_lacuna_acima_do_limite_invalida_velocidade():
    df = pd.DataFrame(
        {
            "VEIC": ["BA001", "BA001"],
            "DTHR": pd.to_datetime(["2026-10-06 10:00:00", "2026-10-06 10:10:01"]),
            "LAT": [-25.4284, -25.4294],
            "LON": [-49.2733, -49.2743],
        }
    )

    resultado = adicionar_metricas_movimento(df, Config(max_intervalo_seg=300))

    assert not resultado.loc[1, "INTERVALO_VALIDO"]
    assert not resultado.loc[1, "VELOCIDADE_VALIDA"]


def test_nao_cruza_veiculos_distintos():
    df = pd.DataFrame(
        {
            "VEIC": ["BA001", "BA002"],
            "DTHR": pd.to_datetime(["2026-10-06 10:00:00", "2026-10-06 10:01:00"]),
            "LAT": [-25.4284, -25.4294],
            "LON": [-49.2733, -49.2743],
        }
    )

    resultado = adicionar_metricas_movimento(df, Config())

    assert resultado["VELOCIDADE_VALIDA"].sum() == 0
