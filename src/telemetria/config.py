"""Configurações centrais do projeto."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Parâmetros analíticos e caminhos de execução."""

    max_intervalo_seg: int = 300
    max_velocidade_kmh: float = 80.0
    limiar_baixa_velocidade_kmh: float = 15.0
    limiar_quase_parada_kmh: float = 1.0
    min_latitude: float = -90.0
    max_latitude: float = 90.0
    min_longitude: float = -180.0
    max_longitude: float = 180.0
    input_path: Path = Path("data/raw/2026_10_06_veiculos.json.xz")
    processed_dir: Path = Path("data/processed")
    tables_dir: Path = Path("outputs/tables")
    maps_dir: Path = Path("outputs/maps")
    figures_dir: Path = Path("outputs/figures")

    def criar_diretorios(self) -> None:
        """Cria os diretórios de saída quando ainda não existem."""
        for directory in (
            self.processed_dir,
            self.tables_dir,
            self.maps_dir,
            self.figures_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
