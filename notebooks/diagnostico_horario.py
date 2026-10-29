"""Diagnóstico: velocidade média por hora e investigação do fuso horário.

Rode DENTRO da pasta projeto-telemetria, com o ambiente virtual ativo:

    python scripts/diagnostico_horario.py

Ele lê outputs/tables/telemetria_com_metricas.csv (gerado pela pipeline)
e grava:
  outputs/tables/resumo_medio_hora.csv      -> média, mediana, min, max por hora
  outputs/figures/analise_media_hora.png    -> gráficos da média e da contagem
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ARQ = Path("outputs/tables/telemetria_com_metricas.csv")

df = pd.read_csv(
    ARQ,
    parse_dates=["DTHR"],
    dtype={
        "VEIC": "string",
        "COD_LINHA": "string",
    },
)
validos = df.loc[df["VELOCIDADE_VALIDA"]].copy()
validos["HORA_INT"] = validos["DTHR"].dt.hour

resumo = validos.groupby("HORA_INT").agg(
    observacoes=("VELOCIDADE_KMH", "size"),
    veiculos_unicos=("VEIC", "nunique"),
    velocidade_media_kmh=("VELOCIDADE_KMH", "mean"),
    velocidade_mediana_kmh=("VELOCIDADE_KMH", "median"),
    percentual_baixa_velocidade=("BAIXA_VELOCIDADE", "mean"),
).reset_index()
resumo["percentual_baixa_velocidade"] *= 100
resumo = resumo.round(3)

print("\nVELOCIDADE MÉDIA POR HORA (timestamps como vieram no arquivo):")
print(resumo.to_string(index=False))

Path("outputs/tables").mkdir(parents=True, exist_ok=True)
resumo.to_csv("outputs/tables/resumo_medio_hora.csv", index=False)

# --- INVESTIGAÇÃO DE FUSO HORÁRIO -------------------------
# Lógica: ônibus em Curitiba começam a operar às ~4h30-5h LOCAIS.
# Se o salto de frota acontece entre 04h-05h no timestamp, o timestamp já é local.
# Se o salto acontece às 01h-02h, o timestamp está 3h adiantado (isto é, UTC).
print("\nVERIFICAÇÃO DOS TIMESTAMPS:")
print("Primeiro timestamp:", df["DTHR"].min())
print("Último timestamp:", df["DTHR"].max())
print("Fuso presente na coluna:", df["DTHR"].dt.tz)

contagem_datas = (
    df["DTHR"]
    .dt.strftime("%Y-%m-%d")
    .value_counts()
    .sort_index()
)

print("\nQuantidade de registros por data:")
print(contagem_datas.to_string())

print(
    "\nAtenção: o padrão de atividade da frota "
    "não confirma o fuso horário."
)
print(
    "Se o fuso aparecer como None, os timestamps "
    "não têm informação de fuso associada nesta tabela."
)
print(
    "Isso não significa que sejam UTC. "
    "O fuso precisa ser confirmado na fonte."
)

fig, axes = plt.subplots(2, 1, figsize=(10, 8))
axes[0].bar(resumo["HORA_INT"], resumo["velocidade_media_kmh"], color="royalblue")
axes[0].set_title("Velocidade MÉDIA por hora (rótulos do timestamp)")
axes[0].set_ylabel("km/h"); axes[0].grid(alpha=0.3)

axes[1].bar(resumo["HORA_INT"], resumo["veiculos_unicos"], color="seagreen")
axes[1].set_title("Veículos únicos por hora (encontre o salto da frota)")
axes[1].set_xlabel("hora no timestamp"); axes[1].set_ylabel("veículos"); axes[1].grid(alpha=0.3)

plt.tight_layout()
Path("outputs/figures").mkdir(parents=True, exist_ok=True)
plt.savefig("outputs/figures/analise_media_hora.png", dpi=150)
print("\nGráfico salvo em outputs/figures/analise_media_hora.png")