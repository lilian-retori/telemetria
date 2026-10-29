import pandas as pd

from telemetria.metrics import resumir_por_hora


def test_calcula_percentual_lento_com_denominador_correto():
    df = pd.DataFrame(
        {
            "DTHR": pd.to_datetime(
                [
                    "2026-10-06 10:00:00",
                    "2026-10-06 10:10:00",
                    "2026-10-06 10:20:00",
                    "2026-10-06 10:30:00",
                ]
            ),
            "VEIC": ["A", "A", "B", "B"],
            "VELOCIDADE_KMH": [5.0, 10.0, 20.0, 30.0],
            "BAIXA_VELOCIDADE": [True, True, False, False],
            "VELOCIDADE_VALIDA": [True, True, True, True],
        }
    )

    resumo = resumir_por_hora(df)

    assert resumo.loc[0, "observacoes_validas"] == 4
    assert resumo.loc[0, "observacoes_baixa_velocidade"] == 2
    assert resumo.loc[0, "percentual_baixa_velocidade"] == 50.0
    assert resumo.loc[0, "veiculos_unicos"] == 2
    assert resumo.loc[0, "velocidade_mediana_kmh"] == 15.0


def test_ignora_velocidades_invalidas_no_denominador():
    df = pd.DataFrame(
        {
            "DTHR": pd.to_datetime(["2026-10-06 10:00:00", "2026-10-06 10:01:00"]),
            "VEIC": ["A", "A"],
            "VELOCIDADE_KMH": [5.0, None],
            "BAIXA_VELOCIDADE": [True, False],
            "VELOCIDADE_VALIDA": [True, False],
        }
    )

    resumo = resumir_por_hora(df)

    assert resumo.loc[0, "observacoes_validas"] == 1
    assert resumo.loc[0, "percentual_baixa_velocidade"] == 100.0
