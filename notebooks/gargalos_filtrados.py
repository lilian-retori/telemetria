"""Filtra gargalos recorrentes e gera mapa limpo.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\gargalos_filtrados.py

Entrada: outputs/comparativo/recorrencia_por_celula.csv
Saidas:  outputs/comparativo/gargalos_filtrados.csv
         outputs/comparativo/mapa_gargalos_filtrados.html

Regra para chamar uma celula de gargalo recorrente:
- dias_com_lentidao >= 25 (presente em quase todo o mes)
- veiculos_unicos >= 50 (muitos onibus diferentes: nao e garagem)
- observacoes_lentas >= 500 (volume estatistico minimo)

Com a nova recorrencia_por_celula.csv, o ranking agora usa
percentual_lentidao (lentas / validas) em vez do volume bruto.
Gargalo por intensidade, nao por fluxo.
"""

import os
from pathlib import Path

import folium
import pandas as pd
from folium import plugins

RAIZ = Path(os.environ.get("RAIZ_COMP", "outputs/comparativo"))

MIN_DIAS = 25
MIN_VEICULOS = 50
MIN_OBSERVACOES = 500
MIN_VALIDAS = 1000  # protege o percentual contra denominadores minusculos


def cor_por_intensidade(percentual: float) -> str:
    if percentual >= 60:
        return "#800026"
    if percentual >= 45:
        return "#bd0026"
    if percentual >= 30:
        return "#fc4e2a"
    return "#fecc5c"


def main() -> None:
    arquivo = RAIZ / "recorrencia_por_celula.csv"
    df = pd.read_csv(arquivo)

    if "percentual_lentidao" not in df.columns:
        raise SystemExit(
            "recorrencia_por_celula.csv sem percentual_lentidao. "
            "Rode primeiro o mapa_recorrencia.py novo."
        )

    filtrados = df.loc[
        (df["dias_com_lentidao"] >= MIN_DIAS)
        & (df["veiculos_unicos"] >= MIN_VEICULOS)
        & (df["observacoes_lentas"] >= MIN_OBSERVACOES)
        & (df["observacoes_validas"] >= MIN_VALIDAS)
    ].copy()

    filtrados = filtrados.sort_values(
        ["percentual_lentidao", "observacoes_lentas"], ascending=False
    ).reset_index(drop=True)

    filtrados.to_csv(RAIZ / "gargalos_filtrados.csv", index=False)

    print(f"Celulas no arquivo original: {len(df):,}")
    print(f"Celulas que passaram no filtro: {len(filtrados):,}")
    print()
    print("Top 20 gargalos por INTENSIDADE (percentual_lentidao):")
    colunas = ["lat_centro", "lon_centro", "percentual_lentidao",
               "observacoes_lentas", "observacoes_validas",
               "dias_com_lentidao", "veiculos_unicos", "velocidade_media_ponderada"]
    colunas = [c for c in colunas if c in filtrados.columns]
    print(filtrados.head(20)[colunas].round(3).to_string())

    if filtrados.empty:
        raise SystemExit("Nenhuma celula passou no filtro. Revise os limiares.")

    centro = [filtrados["lat_centro"].mean(), filtrados["lon_centro"].mean()]
    mapa = folium.Map(location=centro, zoom_start=12,
                      tiles="OpenStreetMap", control_scale=True)

    grupo_calor = folium.FeatureGroup(name="Mapa de calor (intensidade)")
    plugins.HeatMap(
        filtrados[["lat_centro", "lon_centro", "percentual_lentidao"]]
        .values.tolist(),
        radius=15, blur=12, min_opacity=0.3,
    ).add_to(grupo_calor)
    grupo_calor.add_to(mapa)

    grupo_pontos = folium.FeatureGroup(name="Gargalos (detalhes)", show=False)
    for i, row in enumerate(filtrados.itertuples(), start=1):
        popup = (
            f"<b>Gargalo #{i}</b><br>"
            f"Lentidao: <b>{row.percentual_lentidao:.1f}%</b> das validas<br>"
            f"Dias com lentidao: {row.dias_com_lentidao}/31<br>"
            f"Observacoes lentas: {row.observacoes_lentas:,}<br>"
            f"Observacoes validas: {row.observacoes_validas:,}<br>"
            f"Veiculos unicos: {row.veiculos_unicos}<br>"
            f"Velocidade media (lentas): {row.velocidade_media_ponderada:.1f} km/h"
        )
        folium.CircleMarker(
            location=[row.lat_centro, row.lon_centro],
            radius=6,
            color=cor_por_intensidade(row.percentual_lentidao),
            fill=True, fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=300),
        ).add_to(grupo_pontos)
    grupo_pontos.add_to(mapa)

    legenda = """
    <div style="position: fixed; bottom: 40px; left: 40px; z-index: 9999;
                background: white; padding: 10px; border: 2px solid #888;
                border-radius: 6px; font-size: 13px;">
    <b>Intensidade da lentidao</b><br>
    <span style="color:#800026">&#9679;</span> &ge; 60% das validas<br>
    <span style="color:#bd0026">&#9679;</span> 45-59%<br>
    <span style="color:#fc4e2a">&#9679;</span> 30-44%<br>
    <span style="color:#fecc5c">&#9679;</span> &lt; 30%
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(legenda))
    mapa.save(RAIZ / "mapa_gargalos_filtrados.html")
    print(f"Mapa salvo em {RAIZ / 'mapa_gargalos_filtrados.html'}")


if __name__ == "__main__":
    main()