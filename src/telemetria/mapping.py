"""Geração de WebGIS para visualização de telemetria."""

from pathlib import Path

import folium
import pandas as pd
from folium import plugins


def criar_mapa_baixa_velocidade(
    telemetria: pd.DataFrame,
    caminho_saida: Path,
    limiar_baixa_velocidade_kmh: float,
) -> None:
    """Cria mapa HTML das observações válidas abaixo do limiar configurado."""
    lentos = telemetria.loc[
        telemetria["VELOCIDADE_VALIDA"]
        & (telemetria["VELOCIDADE_KMH"] < limiar_baixa_velocidade_kmh)
    ].copy()

    if lentos.empty:
        raise ValueError(
            "Não há observações válidas de baixa velocidade para gerar o mapa."
        )

    centro = [lentos["LAT"].mean(), lentos["LON"].mean()]
    mapa = folium.Map(
        location=centro,
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    grupo_calor = folium.FeatureGroup(name="Densidade de baixa velocidade")
    dados_calor = lentos[["LAT", "LON"]].values.tolist()
    plugins.HeatMap(dados_calor, radius=8, blur=6, min_opacity=0.25).add_to(grupo_calor)
    grupo_calor.add_to(mapa)

    grupo_pontos = folium.FeatureGroup(name="Amostra de observações lentas")
    amostra = lentos.sort_values("DTHR").head(3_000)
    for linha in amostra.itertuples(index=False):
        popup = (
            f"Horário: {linha.DTHR:%Y-%m-%d %H:%M:%S}<br>"
            f"Velocidade: {linha.VELOCIDADE_KMH:.2f} km/h<br>"
            f"Classe: {linha.CLASSE_VELOCIDADE}"
        )
        folium.CircleMarker(
            location=[linha.LAT, linha.LON],
            radius=2,
            color="#d7191c",
            fill=True,
            fill_opacity=0.5,
            popup=popup,
        ).add_to(grupo_pontos)
    grupo_pontos.add_to(mapa)

    titulo = f"""
    <div style="position: fixed; top: 10px; left: 50px; z-index: 1000;
                background: white; padding: 10px; border: 1px solid #777;">
      <b>Mapa de baixa velocidade observada</b><br>
      Velocidade abaixo de {limiar_baixa_velocidade_kmh:.0f} km/h.<br>
      Não interpretar isoladamente como congestionamento.
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(titulo))
    folium.LayerControl(collapsed=False).add_to(mapa)

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(caminho_saida)
