"""Leitura e gravação de dados e produtos analíticos."""

from pathlib import Path

import pandas as pd

from .validation import COLUNAS_OBRIGATORIAS


def carregar_telemetria(caminho: Path) -> pd.DataFrame:
    """Lê JSON Lines compactado e verifica a presença das colunas essenciais."""
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo de entrada não encontrado: {caminho.resolve()}"
        )

    telemetria = pd.read_json(caminho, compression="xz", lines=True)
    faltantes = set(COLUNAS_OBRIGATORIAS) - set(telemetria.columns)
    if faltantes:
        raise ValueError(
            "Arquivo não possui as colunas obrigatórias: "
            + ", ".join(sorted(faltantes))
        )

    return telemetria


def salvar_csv(df: pd.DataFrame, caminho: Path, index: bool = False) -> None:
    """Salva um DataFrame em CSV criando os diretórios necessários."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=index)
