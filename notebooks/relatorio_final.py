"""Gera o relatório interativo final do projeto.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\relatorio_final.py

Correções desta versão:
  - O mapa é salvo como arquivo separado (mapa_gargalos_final.html) e o
    relatório o referencia com <iframe src="...">. Embutir via srcdoc
    impedia o carregamento dos tiles da Esri.
  - Basemap padrão: Esri World Street Map. OSM removido (bloqueado).
  - Camadas densas (parada/próximo) desligadas por padrão, com cluster.
  - Plugins extras: Fullscreen e MiniMap.

Saídas em outputs/comparativo/:
  relatorio_final.html
  mapa_gargalos_final.html
"""

import base64
from pathlib import Path

import folium
import pandas as pd
from folium import plugins

RAIZ = Path("outputs") / "comparativo"
RAIZ_AUD = RAIZ / "auditoria"

TILES_ESRI = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Street_Map/MapServer/tile/{z}/{y}/{x}"
)
ATTR_ESRI = "Tiles © Esri — Source: Esri, HERE, Garmin, OpenStreetMap"

ARQUIVO_MAPA = "mapa_gargalos_final.html"


def img_base64(caminho: Path) -> str:
    if not caminho.exists():
        return ""
    dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return "data:image/png;base64," + dados


def classificar_final(row) -> str:
    nome = str(row["parada_mais_proxima"]).lower()
    if row["classe"] == "fora_de_parada" and (
        "terminal" in nome or "estação tubo" in nome
    ):
        return "zona_terminal"
    return row["classe"]


def construir_mapa(gargalos: pd.DataFrame, n_dias: int) -> folium.Map:
    cores = {
        "parada": "#1a9850",
        "proximo_de_parada": "#fdae61",
        "fora_de_parada": "#d73027",
        "zona_terminal": "#7b2cbf",
    }
    rotulos = {
        "parada": "Parada (≤30 m) — embarque",
        "proximo_de_parada": "Próximo de parada (30–100 m)",
        "fora_de_parada": "Fora de parada (>100 m) — tráfego",
        "zona_terminal": "Zona de terminal/estação tubo",
    }

    centro = [gargalos["lat_centro"].mean(), gargalos["lon_centro"].mean()]

    mapa = folium.Map(
        location=centro,
        zoom_start=12,
        tiles=TILES_ESRI,
        attr=ATTR_ESRI,
        control_scale=True,
        prefer_canvas=True,
    )

    # Camadas densas: desligadas por padrão e agrupadas em clusters
    for classe in ("parada", "proximo_de_parada"):
        sub = gargalos.loc[gargalos["classe_final"] == classe]
        grupo = folium.FeatureGroup(name=rotulos[classe], show=False)
        cluster = plugins.MarkerCluster()
        for row in sub.itertuples():
            popup = (
                f"<b>{row.parada_mais_proxima}</b><br>"
                f"Classe: {rotulos[classe]}<br>"
                f"Dias lento: {row.dias_com_lentidao}/{n_dias}<br>"
                f"Observações lentas: {row.observacoes_lentas:,}"
            )
            folium.CircleMarker(
                location=[row.lat_centro, row.lon_centro],
                radius=4,
                color=cores[classe],
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(popup, max_width=300),
            ).add_to(cluster)
        cluster.add_to(grupo)
        grupo.add_to(mapa)

    # Camadas principais: visíveis por padrão
    for classe in ("fora_de_parada", "zona_terminal"):
        sub = gargalos.loc[gargalos["classe_final"] == classe]
        grupo = folium.FeatureGroup(name=rotulos[classe], show=True)
        for row in sub.itertuples():
            popup = (
                f"<b>{row.parada_mais_proxima}</b><br>"
                f"Classe: {rotulos[classe]}<br>"
                f"Distância da parada: {row.distancia_parada_m} m<br>"
                f"Dias lento: {row.dias_com_lentidao}/{n_dias}<br>"
                f"Observações lentas: {row.observacoes_lentas:,}<br>"
                f"Veículos únicos: {row.veiculos_unicos}"
            )
            folium.CircleMarker(
                location=[row.lat_centro, row.lon_centro],
                radius=5,
                color=cores[classe],
                fill=True,
                fill_opacity=0.85,
                popup=folium.Popup(popup, max_width=320),
            ).add_to(grupo)
        grupo.add_to(mapa)

    # Extras de navegação
    plugins.Fullscreen(position="topleft").add_to(mapa)
    plugins.MiniMap(toggle_display=True).add_to(mapa)

    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


def main() -> None:
    diario = pd.read_csv(RAIZ / "resumo_diario.csv")
    tipos = pd.read_csv(RAIZ / "resumo_tipos_dia.csv")
    gargalos = pd.read_csv(RAIZ / "gargalos_classificados.csv")
    auditoria = pd.read_csv(RAIZ_AUD / "auditoria_top20.csv")

    gargalos["classe_final"] = gargalos.apply(classificar_final, axis=1)

    total_registros = int(diario["registros_originais"].sum())
    periodo_ini = diario["data"].min()
    periodo_fim = diario["data"].max()
    n_dias = len(diario)
    contagem_classes = gargalos["classe_final"].value_counts()

    # Mapa salvo como arquivo separado (o iframe do relatório usa src)
    mapa = construir_mapa(gargalos, n_dias)
    mapa.save(RAIZ / ARQUIVO_MAPA)

    tipos_html = tipos.to_html(index=False, classes="tabela", border=0)
    cols_aud = [
        "GARGALO", "obs_lentas_mes", "dias_ativo",
        "hora_pico_dia_util", "distancia_parada_m", "linhas_dominantes",
    ]
    auditoria_html = auditoria[cols_aud].to_html(
        index=False, classes="tabela", border=0
    )

    img_semana = img_base64(RAIZ / "comparativo_dias.png")
    img_perfis = img_base64(RAIZ_AUD / "perfis_horarios_top20.png")

    contagens_html = "".join(
        f"<li><b>{c}:</b> {n} células</li>" for c, n in contagem_classes.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Gargalos do Transporte Coletivo de Curitiba — Set/2026</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 0 auto;
         padding: 24px; color: #222; line-height: 1.55; }}
  h1 {{ color: #8b0000; }}
  h2 {{ border-bottom: 2px solid #ddd; padding-bottom: 4px; margin-top: 40px; }}
  .tabela {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  .tabela th {{ background: #8b0000; color: white; padding: 6px; text-align: left; }}
  .tabela td {{ border-bottom: 1px solid #ddd; padding: 6px; }}
  .tabela tr:nth-child(even) {{ background: #f7f7f7; }}
  iframe {{ width: 100%; height: 620px; border: 1px solid #ccc; }}
  img.grafico {{ width: 100%; border: 1px solid #ddd; }}
  .destaque {{ background: #fff3cd; padding: 12px; border-left: 4px solid #e0a800; }}
</style>
</head>
<body>

<h1>Gargalos do Transporte Coletivo de Curitiba</h1>
<p><b>Análise de recorrência de baixa velocidade na telemetria de ônibus</b><br>
Período: {periodo_ini} a {periodo_fim} ({n_dias} dias) &mdash;
{total_registros:,} registros de GPS processados</p>

<div class="destaque">
<b>Resultado central:</b> a lentidão segue um ciclo semanal claro
(domingo ~20%, sábado ~23%, dia útil ~27% das observações abaixo de 15 km/h),
com picos às 7h–8h e 17h–19h. A maioria dos pontos lentos recorrentes está
sobre ou perto de paradas — embarque, não congestionamento. Os gargalos fora
de parada concentram-se no Centro e no eixo sul (Capão Raso / Novo Mundo /
Boqueirão).
</div>

<h2>1. Ciclo semanal de lentidão (31 dias)</h2>
<img class="grafico" src="{img_semana}" alt="Comparativo diário">

<h2>2. Resumo por tipo de dia</h2>
<p>Feriado, dia pós-feriado com cobertura reduzida e o domingo de eleição
foram excluídos das médias.</p>
{tipos_html}

<h2>3. Mapa de gargalos classificados</h2>
<p>Regra: lentidão em ≥25 dos 31 dias, ≥50 veículos únicos e ≥500 observações.
Por padrão o mapa mostra apenas <b>tráfego (vermelho)</b> e
<b>terminais (roxo)</b>. As camadas verde e laranja ficam desligadas para não
poluir a leitura — ligue-as no controle de camadas (elas se agrupam em
clusters). Use o botão de tela cheia no canto superior esquerdo.</p>
<ul>{contagens_html}</ul>
<iframe src="{ARQUIVO_MAPA}"></iframe>

<h2>4. Top 20 gargalos auditados (fora de parada)</h2>
{auditoria_html}

<h2>5. Perfil horário por gargalo (dias úteis)</h2>
<p>Gargalos de tráfego apresentam picos claros nos horários de ponta;
curvas achatadas indicariam efeito operacional (terminal, pátio).</p>
<img class="grafico" src="{img_perfis}" alt="Perfis horários">

<h2>6. Metodologia e limitações</h2>
<ul>
  <li>Velocidade entre posições consecutivas (Haversine ÷ tempo); pares com
      intervalo ≤0 s ou &gt;300 s, e velocidades &gt;80 km/h, descartados.</li>
  <li>Grade de ~200 m; parada classificada pela distância do centro da célula
      à parada mais próxima (30 m / 100 m).</li>
  <li>Terminais e estações tubo formam classe própria: manobras e filas
      operacionais, não congestionamento de via.</li>
  <li>Arquivos URBS nomeados no dia N contêm registros do dia N−1;
      timestamps em horário local (GMT-3).</li>
  <li>Baixa velocidade ≠ congestionamento: o produto mede lentidão recorrente
      observada pela frota, não o tráfego geral da cidade.</li>
  <li>Análise descritiva (séries temporais + cartografia); não preditiva.</li>
</ul>

<p><small>Fonte: dados abertos URBS/C3SL-UFPR. Spate Tech Bootcamp 2026.</small></p>

</body>
</html>
"""

    saida = RAIZ / "relatorio_final.html"
    saida.write_text(html, encoding="utf-8")
    print("Relatório gerado em:", saida)
    print("Mapa separado em:", RAIZ / ARQUIVO_MAPA)
    print("Classes no mapa:")
    print(contagem_classes.to_string())


if __name__ == "__main__":
    main()