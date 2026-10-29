"""Gera mapa de recorrencia espacial de baixa velocidade.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\mapa_recorrencia.py

Ele procura em outputs/AAAA-MM-DD/tables/telemetria_com_metricas.csv, por dia:
  1) guarda as observacoes com VELOCIDADE_KMH valida (nao nula, >= 0)
     e destas separa as que estao abaixo do limiar;
  2) agrega por celula geografica (~200 m), contando dias distintos com lentidao;
  3) calcula o percentual de lentidao sobre o total de observacoes validas
     da mesma celula.

Saidas:
  outputs/comparativo/recorrencia_por_celula.csv
  outputs/comparativo/mapa_recorrencia.html
"""

import re
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from folium import plugins

RAIZ = Path("outputs")
SAIDA = RAIZ / "comparativo"
SAIDA.mkdir(parents=True, exist_ok=True)

TAMANHO_CELULA = 0.002
LIMIAR_KMH = 15
MIN_OBSERVACOES = 5
PADRAO_PASTA_DIA = re.compile(r"\d{4}-\d{2}-\d{2}$")


def criar_celula(lat: float, lon: float) -> str:
    """Identificador da celula geografica a partir das coordenadas."""
    celula_lat = np.floor(lat / TAMANHO_CELULA) * TAMANHO_CELULA
    celula_lon = np.floor(lon / TAMANHO_CELULA) * TAMANHO_CELULA
    return f"{celula_lat:.6f}_{celula_lon:.6f}"


def carregar_dia(pasta_dia: Path) -> pd.DataFrame | None:
    """Carrega o dia e agrega por celula mantendo o total de pares validos.

    Observacoes com VELOCIDADE_KMH nula (pares invalidos do features) sao
    excluidas do denominador; as demais sao divididas entre 'lenta' e nao.
    Datas sao lidas de forma tolerante: o pipeline grava ISO, mas formatos
    com dia primeiro tambem podem aparecer.
    """
    arquivo = pasta_dia / "tables" / "telemetria_com_metricas.csv"
    if not arquivo.exists():
        return None

    df = pd.read_csv(
        arquivo,
        usecols=["VEIC", "DTHR", "LAT", "LON", "VELOCIDADE_KMH"],
    )
    df["DTHR"] = pd.to_datetime(df["DTHR"], errors="coerce", format="ISO8601")
    restantes = df["DTHR"].isna()
    if restantes.any():
        df.loc[restantes, "DTHR"] = pd.to_datetime(
            df.loc[restantes, "DTHR"],
            format="%d/%m/%Y %H:%M:%S",
            errors="coerce",
        )
    df = df.dropna(subset=["VEIC", "DTHR", "LAT", "LON", "VELOCIDADE_KMH"])
    df = df.loc[df["VELOCIDADE_KMH"] >= 0]
    if df.empty:
        return None

    df["CELULA"] = [criar_celula(a, o) for a, o in zip(df["LAT"], df["LON"])]
    df["DATA"] = df["DTHR"].dt.date
    df["LENTA"] = df["VELOCIDADE_KMH"] < LIMIAR_KMH

    agg = (
        df.groupby("CELULA", as_index=False)
        .agg(
            data=("DATA", "first"),
            observacoes_validas=("VELOCIDADE_KMH", "size"),
            observacoes_lentas=("LENTA", "sum"),
            vel_lentas_soma=(
                "VELOCIDADE_KMH",
                lambda x: float(x[df.loc[x.index, "LENTA"]].sum()),
            ),
            lat_soma_pesada=("LAT",
                lambda x: float((x * 1.0).sum())),
            lon_soma_pesada=("LON",
                lambda x: float((x * 1.0).sum())),
            veiculos=("VEIC", lambda x: frozenset(x)),
        )
    )
    return agg


def agregar_recorrencia(dias: list[pd.DataFrame]) -> pd.DataFrame:
    """Une as agregacoes diarias por celula e calcula indicadores finais."""
    frames = [d for d in dias if d is not None and not d.empty]
    if not frames:
        raise ValueError("Nenhum dia com observacoes validas encontrado.")

    todos = pd.concat(frames, ignore_index=True)
    print(f"Celulas unicas agregadas: {todos['CELULA'].nunique():,}")

    resultado = (
        todos.groupby("CELULA")
        .agg(
            dias_validos=("data", "nunique"),
            observacoes_validas=("observacoes_validas", "sum"),
            observacoes_lentas=("observacoes_lentas", "sum"),
            vel_lentas_soma=("vel_lentas_soma", "sum"),
            lat_total=("lat_soma_pesada", "sum"),
            lon_total=("lon_soma_pesada", "sum"),
            veiculos=("veiculos", lambda x: frozenset().union(*x)),
        )
        .reset_index()
    )
    resultado["dias_com_lentidao"] = (
        todos.loc[todos["observacoes_lentas"] > 0]
        .groupby("CELULA")["data"].nunique()
        .reindex(resultado["CELULA"])
        .fillna(0)
        .astype(int)
        .to_numpy()
    )
    resultado["velocidade_media_ponderada"] = (
        resultado["vel_lentas_soma"] / resultado["observacoes_lentas"].replace(0, np.nan)
    )
    resultado["lat_centro"] = resultado["lat_total"] / resultado["observacoes_validas"]
    resultado["lon_centro"] = resultado["lon_total"] / resultado["observacoes_validas"]
    resultado["percentual_lentidao"] = (
        resultado["observacoes_lentas"] / resultado["observacoes_validas"] * 100
    ).round(2)
    resultado["veiculos_unicos"] = resultado["veiculos"].map(len)
    resultado = resultado.drop(columns=["veiculos", "vel_lentas_soma", "lat_total", "lon_total"])

    resultado = resultado.loc[resultado["observacoes_lentas"] >= MIN_OBSERVACOES]
    resultado = resultado.sort_values(
        ["percentual_lentidao", "observacoes_lentas"], ascending=False
    ).reset_index(drop=True)
    return resultado


def cor_por_recorrencia(dias: int) -> str:
    if dias >= 25: return "#800026"
    if dias >= 20: return "#bd0026"
    if dias >= 15: return "#e31a1c"
    if dias >= 10: return "#fc4e2a"
    if dias >= 5:  return "#fd8d3c"
    return "#fecc5c"


def criar_mapa(df: pd.DataFrame) -> folium.Map:
    centro = [df["lat_centro"].mean(), df["lon_centro"].mean()]
    mapa = folium.Map(location=centro, zoom_start=12,
                      tiles="OpenStreetMap", control_scale=True)
    for row in df.itertuples():
        popup = (
            f"<b>Celula {row.CELULA}</b><br>"
            f"Dias com lentidao: {row.dias_com_lentidao}/{row.dias_validos}<br>"
            f"Observacoes lentas: {row.observacoes_lentas:,}<br>"
            f"Observacoes validas: {row.observacoes_validas:,}<br>"
            f"Lentidao: {row.percentual_lentidao:.2f}%<br>"
            f"Veiculos unicos: {row.veiculos_unicos}<br>"
            f"Velocidade media (lentas): {row.velocidade_media_ponderada:.1f} km/h"
        )
        cor = cor_por_recorrencia(row.dias_com_lentidao)
        folium.CircleMarker(
            location=[row.lat_centro, row.lon_centro],
            radius=8, color=cor, fill=True, fill_color=cor,
            fill_opacity=0.7, popup=popup,
        ).add_to(mapa)

    legenda = """
    <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000;
                background: white; padding: 12px; border: 2px solid #777;
                border-radius: 5px; font-size: 14px;">
      <b>Recorrencia de baixa velocidade</b><br>
      <i class="fa fa-circle" style="color:#800026"></i> 25+ dias<br>
      <i class="fa fa-circle" style="color:#bd0026"></i> 20-24 dias<br>
      <i class="fa fa-circle" style="color:#e31a1c"></i> 15-19 dias<br>
      <i class="fa fa-circle" style="color:#fc4e2a"></i> 10-14 dias<br>
      <i class="fa fa-circle" style="color:#fd8d3c"></i> 5-9 dias<br>
      <i class="fa fa-circle" style="color:#fecc5c"></i> 1-4 dias<br>
      <hr>
      Velocidade &lt; 15 km/h | Grade ~200m x ~200m<br>
      Lentidao = lenta / validas (denominador correto)
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(legenda))
    return mapa


def main() -> None:
    pastas = []
    for pasta in sorted(RAIZ.iterdir()):
        if not pasta.is_dir():
            continue
        # apenas pastas de data exata; pastas de teste com etiqueta ficam fora
        if not PADRAO_PASTA_DIA.fullmatch(pasta.name):
            continue
        if (pasta / "tables" / "telemetria_com_metricas.csv").exists():
            pastas.append(pasta)

    if len(pastas) < 2:
        raise ValueError("Processe pelo menos 2 dias antes do mapa.")

    print(f"Carregando {len(pastas)} dias (agregado por celula)...")
    dias = []
    for pasta in pastas:
        d = carregar_dia(pasta)
        if d is not None and not d.empty:
            dias.append(d)
            print(f"  {pasta.name}: {len(d):,} celulas com dados validos")
        else:
            print(f"  {pasta.name}: sem observacoes validas (ignorado)")

    recorrencia = agregar_recorrencia(dias)
    print(f"Celulas com >= {MIN_OBSERVACOES} obs. lentas: {len(recorrencia):,}")
    print(recorrencia.head(10)[[
        "CELULA", "dias_com_lentidao", "observacoes_lentas",
        "observacoes_validas", "percentual_lentidao", "veiculos_unicos"
    ]].to_string(index=False))

    recorrencia.to_csv(SAIDA / "recorrencia_por_celula.csv", index=False)
    cmapa = criar_mapa(recorrencia)
    cmapa.save(SAIDA / "mapa_recorrencia.html")
    print(f"Arquivos salvos em: {SAIDA}")


if __name__ == "__main__":
    main()