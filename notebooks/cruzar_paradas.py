"""Cruza gargalos recorrentes com pontos de parada de ônibus.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\cruzar_paradas.py

Entradas:
  outputs/comparativo/gargalos_filtrados.csv
  data/external/*pontosLinha*.json.xz

O arquivo pontosLinha vem como LISTA JSON por linha ([{...},{...}]),
com campos: NOME, NUM, LAT (vírgula decimal), LON, SEQ, SENTIDO, COD.

Saídas:
  outputs/comparativo/gargalos_classificados.csv
  outputs/comparativo/mapa_gargalos_classificados.html

Classificação pela distância do CENTRO da célula (~200 m) à parada mais próxima:
  <= 30 m   -> parada            (provável embarque/desembarque)
  <= 100 m  -> proximo_de_parada (zona de influência/fronteira)
  > 100 m   -> fora_de_parada    (candidato a lentidão de tráfego)
"""

import json
from pathlib import Path

import folium
import numpy as np
import pandas as pd

RAIZ_OUT = Path("outputs") / "comparativo"
RAIZ_EXT = Path("data") / "external"

RAIO_TERRA_M = 6_371_000.0
LIMIAR_PARADA_M = 30.0
LIMIAR_PROXIMO_M = 100.0


def distancia_m(lat1, lon1, lat2, lon2):
    """Haversine vetorizado: ponto (lat1, lon1) contra vetores lat2/lon2."""
    lat1r = np.radians(lat1)
    lon1r = np.radians(lon1)
    lat2r = np.radians(lat2)
    lon2r = np.radians(lon2)
    a = (
        np.sin((lat2r - lat1r) / 2) ** 2
        + np.cos(lat1r) * np.cos(lat2r) * np.sin((lon2r - lon1r) / 2) ** 2
    )
    a = np.clip(a, 0.0, 1.0)
    return 2 * RAIO_TERRA_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def para_float(valor):
    """Converte string com vírgula decimal para float; None se inválido."""
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None


def carregar_paradas() -> pd.DataFrame:
    arquivos = sorted(RAIZ_EXT.glob("*ontosLinha*.json.xz"))
    if not arquivos:
        raise FileNotFoundError(
            "Nenhum arquivo pontosLinha em data/external/."
        )
    arquivo = arquivos[-1]
    print("Lendo paradas de:", arquivo.name)

    registros = []
    with pd.io.common.get_handle(arquivo, "rt", compression="xz") as h:
        for linha in h.handle:
            linha = linha.strip()
            if not linha:
                continue
            conteudo = json.loads(linha)
            if isinstance(conteudo, list):
                registros.extend(conteudo)
            else:
                registros.append(conteudo)

    df = pd.DataFrame(registros)

    paradas = pd.DataFrame(
        {
            "NOME_PARADA": df["NOME"].astype("string"),
            "COD_LINHA": df["COD"].astype("string"),
            "LAT": df["LAT"].map(para_float),
            "LON": df["LON"].map(para_float),
        }
    ).dropna(subset=["LAT", "LON"])

    # Mesmo ponto físico aparece várias vezes (uma por linha que para ali).
    # Para distância, deduplicamos por coordenada+nome.
    paradas = paradas.drop_duplicates(
        subset=["NOME_PARADA", "LAT", "LON"]
    ).reset_index(drop=True)

    print("Paradas únicas carregadas:", len(paradas))
    return paradas


def classificar(dist_m: float) -> str:
    if dist_m <= LIMIAR_PARADA_M:
        return "parada"
    if dist_m <= LIMIAR_PROXIMO_M:
        return "proximo_de_parada"
    return "fora_de_parada"


def main() -> None:
    gargalos = pd.read_csv(RAIZ_OUT / "gargalos_filtrados.csv")
    paradas = carregar_paradas()

    lat_p = paradas["LAT"].to_numpy()
    lon_p = paradas["LON"].to_numpy()
    nomes_p = paradas["NOME_PARADA"].to_numpy()

    distancias = []
    nomes = []
    for row in gargalos.itertuples():
        d = distancia_m(row.lat_centro, row.lon_centro, lat_p, lon_p)
        i = int(np.argmin(d))
        distancias.append(d[i])
        nomes.append(str(nomes_p[i]))

    gargalos["parada_mais_proxima"] = nomes
    gargalos["distancia_parada_m"] = np.round(distancias, 1)
    gargalos["classe"] = gargalos["distancia_parada_m"].map(classificar)
    gargalos = gargalos.sort_values(
        "observacoes_lentas", ascending=False
    ).reset_index(drop=True)

    gargalos.to_csv(RAIZ_OUT / "gargalos_classificados.csv", index=False)

    print()
    print("Distribuição das classes:")
    print(gargalos["classe"].value_counts().to_string())
    print()
    print("Top 20 gargalos FORA DE PARADA (candidatos a tráfego):")
    fora = gargalos.loc[gargalos["classe"] == "fora_de_parada"]
    colunas = ["lat_centro", "lon_centro", "observacoes_lentas",
               "veiculos_unicos", "velocidade_media_ponderada",
               "distancia_parada_m", "parada_mais_proxima"]
    print(fora.head(20)[colunas].round(2).to_string())

    cores = {
        "parada": "#1a9850",
        "proximo_de_parada": "#fdae61",
        "fora_de_parada": "#d73027",
    }

    centro = [gargalos["lat_centro"].mean(), gargalos["lon_centro"].mean()]
    mapa = folium.Map(location=centro, zoom_start=12,
                      tiles="OpenStreetMap", control_scale=True)

    for classe, cor in cores.items():
        grupo = folium.FeatureGroup(name=classe)
        for row in gargalos.loc[gargalos["classe"] == classe].itertuples():
            popup = (
                f"<b>{row.parada_mais_proxima}</b><br>"
                f"Classe: {classe}<br>"
                f"Distância da parada: {row.distancia_parada_m} m<br>"
                f"Dias lento: {row.dias_com_lentidao}/31<br>"
                f"Observações lentas: {row.observacoes_lentas:,}<br>"
                f"Veículos únicos: {row.veiculos_unicos}"
            )
            folium.CircleMarker(
                location=[row.lat_centro, row.lon_centro],
                radius=6,
                color=cor,
                fill=True,
                fill_opacity=0.8,
                popup=folium.Popup(popup, max_width=320),
            ).add_to(grupo)
        grupo.add_to(mapa)

    legenda = (
        "<div style='position: fixed; bottom: 40px; left: 40px; z-index: 1000;"
        " background: white; padding: 12px; border: 2px solid #555;"
        " border-radius: 5px; font-size: 13px; line-height: 1.6;'>"
        "<b>Gargalos classificados — Set/2026</b><br>"
        "<span style='color:#d73027'>&#9679;</span> Fora de parada (&gt;100 m) — tráfego<br>"
        "<span style='color:#fdae61'>&#9679;</span> Próximo de parada (30–100 m)<br>"
        "<span style='color:#1a9850'>&#9679;</span> Parada (&le;30 m) — embarque"
        "</div>"
    )
    mapa.get_root().html.add_child(folium.Element(legenda))
    folium.LayerControl(collapsed=False).add_to(mapa)

    mapa.save(RAIZ_OUT / "mapa_gargalos_classificados.html")
    print()
    print("Arquivos salvos em", RAIZ_OUT)
    print("  - gargalos_classificados.csv")
    print("  - mapa_gargalos_classificados.html")


if __name__ == "__main__":
    main()