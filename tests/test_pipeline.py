from pathlib import Path

import pandas as pd

from telemetria.config import Config
from telemetria.pipeline import executar_pipeline


def test_pipeline_cria_saidas_com_base_minima(tmp_path: Path):
    entrada = tmp_path / "entrada.json.xz"

    dados = pd.DataFrame(
        {
            "VEIC": ["BA001", "BA001", "BA001"],
            "DTHR": [
                "06/10/2026 10:00:00",
                "06/10/2026 10:01:00",
                "06/10/2026 10:02:00",
            ],
            "LAT": [-25.4284, -25.4285, -25.4286],
            "LON": [-49.2733, -49.2734, -49.2735],
        }
    )

    dados.to_json(
        entrada,
        orient="records",
        lines=True,
        compression="xz",
    )

    config = Config(
        input_path=entrada,
        processed_dir=tmp_path / "processed",
        tables_dir=tmp_path / "tables",
        maps_dir=tmp_path / "maps",
        figures_dir=tmp_path / "figures",
    )

    executar_pipeline(config)

    pasta_resultados = config.tables_dir.parent / "2026-10-06"

    assert (pasta_resultados / "tables" / "auditoria.csv").exists()

    assert (pasta_resultados / "tables" / "resumo_horario.csv").exists()

    assert (pasta_resultados / "tables" / "telemetria_com_metricas.csv").exists()

    assert (pasta_resultados / "maps" / "mapa_baixa_velocidade.html").exists()
