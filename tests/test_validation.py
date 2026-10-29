import pandas as pd
import pytest

from telemetria.config import Config
from telemetria.validation import padronizar_colunas, validar_registros


def registro_base():
    return {
        "VEIC": "BA001",
        "DTHR": "06/10/2026 10:00:00",
        "LAT": "-25,4284",
        "LON": "-49,2733",
    }


def test_padroniza_virgula_decimal_e_data():
    df = padronizar_colunas(pd.DataFrame([registro_base()]))

    assert df.loc[0, "LAT"] == -25.4284
    assert df.loc[0, "LON"] == -49.2733
    assert pd.notna(df.loc[0, "DTHR"])


def test_rejeita_coordenada_fora_do_intervalo():
    registro = registro_base()
    registro["LAT"] = "95"
    df = padronizar_colunas(pd.DataFrame([registro]))

    aceitos, rejeitados = validar_registros(df, Config())

    assert aceitos.empty
    assert rejeitados.iloc[0]["MOTIVO_REJEICAO"] == "coordenada_fora_do_intervalo"


def test_remove_duplicata_identica():
    df = padronizar_colunas(pd.DataFrame([registro_base(), registro_base()]))

    aceitos, rejeitados = validar_registros(df, Config())

    assert len(aceitos) == 1
    assert len(rejeitados) == 1
    assert rejeitados.iloc[0]["MOTIVO_REJEICAO"] == "duplicata_identica"


def test_detecta_timestamp_conflitante():
    primeiro = registro_base()
    segundo = registro_base()
    segundo["LAT"] = "-25,5000"
    df = padronizar_colunas(pd.DataFrame([primeiro, segundo]))

    aceitos, rejeitados = validar_registros(df, Config())

    assert aceitos.empty
    assert set(rejeitados["MOTIVO_REJEICAO"]) == {"timestamp_conflitante"}


def test_falha_quando_coluna_esta_ausente():
    df = pd.DataFrame({"VEIC": ["BA001"]})

    with pytest.raises(ValueError, match="Colunas ausentes"):
        validar_registros(df, Config())
