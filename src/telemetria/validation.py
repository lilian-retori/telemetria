"""Padronização, validação e auditoria de registros de telemetria."""

import pandas as pd

from .config import Config

COLUNAS_OBRIGATORIAS = ("VEIC", "DTHR", "LAT", "LON")


def padronizar_colunas(telemetria: pd.DataFrame) -> pd.DataFrame:
    """Converte data/hora e coordenadas para tipos apropriados.

    Valores inválidos são convertidos em ausentes para que possam ser identificados
    pela etapa de validação, sem interromper todo o processamento.
    """
    df = telemetria.copy()

    for coluna in ("LAT", "LON"):
        df[coluna] = pd.to_numeric(
            df[coluna].astype("string").str.replace(",", ".", regex=False),
            errors="coerce",
        )

    df["DTHR"] = pd.to_datetime(
        df["DTHR"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )
    return df


def validar_registros(
    telemetria: pd.DataFrame, config: Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa registros aceitos e rejeitados, incluindo motivo da rejeição.

    Duplicatas idênticas são removidas. Um veículo com o mesmo timestamp em
    coordenadas diferentes é considerado conflito, pois não há critério seguro
    para escolher uma posição sem informação adicional.
    """
    faltantes = set(COLUNAS_OBRIGATORIAS) - set(telemetria.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {sorted(faltantes)}")

    df = telemetria.copy()
    df["MOTIVO_REJEICAO"] = pd.NA

    estrutura_invalida = (
        df["VEIC"].isna() | df["DTHR"].isna() | df["LAT"].isna() | df["LON"].isna()
    )
    df.loc[estrutura_invalida, "MOTIVO_REJEICAO"] = "campo_obrigatorio_invalido"

    latitude_invalida = ~df["LAT"].between(config.min_latitude, config.max_latitude)
    longitude_invalida = ~df["LON"].between(config.min_longitude, config.max_longitude)
    coordenada_invalida = (latitude_invalida | longitude_invalida) & ~estrutura_invalida
    df.loc[coordenada_invalida, "MOTIVO_REJEICAO"] = "coordenada_fora_do_intervalo"

    candidatos = df["MOTIVO_REJEICAO"].isna()
    duplicata_identica = candidatos & df.duplicated(
        subset=["VEIC", "DTHR", "LAT", "LON"], keep="first"
    )
    df.loc[duplicata_identica, "MOTIVO_REJEICAO"] = "duplicata_identica"

    candidatos = df["MOTIVO_REJEICAO"].isna()

    conflito_timestamp = pd.Series(False, index=df.index)
    conflito_timestamp.loc[candidatos] = df.loc[candidatos].duplicated(
        subset=["VEIC", "DTHR"],
        keep=False,
    )

    df.loc[conflito_timestamp, "MOTIVO_REJEICAO"] = "timestamp_conflitante"

    aceitos = df.loc[df["MOTIVO_REJEICAO"].isna()].copy()
    rejeitados = df.loc[df["MOTIVO_REJEICAO"].notna()].copy()
    return aceitos, rejeitados


def criar_auditoria(
    total_original: int,
    rejeitados: pd.DataFrame,
    telemetria_com_metricas: pd.DataFrame,
) -> pd.DataFrame:
    """Cria tabela de contagens para auditoria das decisões de qualidade."""
    motivos = (
        rejeitados["MOTIVO_REJEICAO"]
        .value_counts(dropna=False)
        .rename_axis("categoria")
        .reset_index(name="quantidade")
    )

    pares_invalidos = int((~telemetria_com_metricas["INTERVALO_VALIDO"]).sum())
    velocidades_invalidas = int((~telemetria_com_metricas["VELOCIDADE_VALIDA"]).sum())

    linhas_extras = pd.DataFrame(
        {
            "categoria": [
                "registros_originais",
                "registros_aceitos_apos_validacao",
                "pares_com_intervalo_invalido",
                "pares_com_velocidade_invalida",
                "pares_com_velocidade_valida",
            ],
            "quantidade": [
                total_original,
                len(telemetria_com_metricas),
                pares_invalidos,
                velocidades_invalidas,
                int(telemetria_com_metricas["VELOCIDADE_VALIDA"].sum()),
            ],
        }
    )
    return pd.concat([linhas_extras, motivos], ignore_index=True)
