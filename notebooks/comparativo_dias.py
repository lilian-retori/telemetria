"""Gera o resumo comparativo dos dias processados, classificando tipos de dia.

Rode com o ambiente virtual ativo:

    python .\comparativo_dias.py

Ele procura em outputs/AAAA-MM-DD/tables/ os arquivos auditoria.csv
e resumo_horario.csv, e grava:

  outputs/comparativo/resumo_diario.csv
  outputs/comparativo/comparativo_dias.png

Classificação:
- feriado: 2026-09-07 (Independência)
- anomalia_cobertura: 2026-09-08 (terça pós-feriado, frota reduzida)
- especial_eleicao: 2026-10-04 (domingo de eleição, frota ampliada)
- sabado / domingo / dia_util: demais dias
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = Path("outputs")
SAIDA = RAIZ / "comparativo"
SAIDA.mkdir(parents=True, exist_ok=True)

FERIADOS = {"2026-09-07"}
ANOMALIAS_COBERTURA = {"2026-09-08"}
ESPECIAIS_ELEICAO = {"2026-10-04"}

NOME_DIA = {
    "Monday": "Segunda",
    "Tuesday": "Terça",
    "Wednesday": "Quarta",
    "Thursday": "Quinta",
    "Friday": "Sexta",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}


def classificar_dia(data_str: str, dia_semana_en: str) -> str:
    if data_str in FERIADOS:
        return "feriado"
    if data_str in ANOMALIAS_COBERTURA:
        return "anomalia_cobertura"
    if data_str in ESPECIAIS_ELEICAO:
        return "especial_eleicao"
    if dia_semana_en == "Saturday":
        return "sabado"
    if dia_semana_en == "Sunday":
        return "domingo"
    return "dia_util"


def ler_dia(pasta_dia: Path) -> dict:
    pasta_tabelas = pasta_dia / "tables"
    resumo_hora = pd.read_csv(
        pasta_tabelas / "resumo_horario.csv",
        parse_dates=["HORA"],
    )
    auditoria = pd.read_csv(pasta_tabelas / "auditoria.csv")
    data_real = resumo_hora["HORA"].min().date()
    data_str = str(data_real)
    dia_semana_en = pd.Timestamp(data_real).day_name()

    validos = int(resumo_hora["observacoes_validas"].sum())
    lentos = int(resumo_hora["observacoes_baixa_velocidade"].sum())
    originais = auditoria.loc[
        auditoria["categoria"] == "registros_originais", "quantidade"
    ].iloc[0]

    return {
        "data": data_str,
        "dia_semana": NOME_DIA.get(dia_semana_en, dia_semana_en),
        "tipo_dia": classificar_dia(data_str, dia_semana_en),
        "registros_originais": int(originais),
        "pares_velocidade_valida": validos,
        "veiculos_max_por_hora": int(resumo_hora["veiculos_unicos"].max()),
        "percentual_baixa_velocidade": round(100 * lentos / validos, 2),
        "velocidade_mediana_hora_minima": round(
            resumo_hora["velocidade_mediana_kmh"].min(), 2
        ),
        "velocidade_mediana_hora_maxima": round(
            resumo_hora["velocidade_mediana_kmh"].max(), 2
        ),
        "horario_mais_lento": resumo_hora.loc[
            resumo_hora["velocidade_mediana_kmh"].idxmin(), "HORA"
        ].strftime("%H:00"),
    }


def main() -> None:
    pastas = []
    for pasta in sorted(RAIZ.iterdir()):
        if not pasta.is_dir() or pasta.name == "comparativo":
            continue
        tabelas = pasta / "tables"
        if (tabelas / "auditoria.csv").exists() and (
            tabelas / "resumo_horario.csv"
        ).exists():
            pastas.append(pasta)

    if len(pastas) < 2:
        raise ValueError(
            "Foram encontradas menos de 2 datas. "
            "Processe mais dias antes de comparar."
        )

    linhas = [ler_dia(pasta) for pasta in pastas]
    diario = pd.DataFrame(linhas).sort_values("data").reset_index(drop=True)
    diario.to_csv(SAIDA / "resumo_diario.csv", index=False)

    # Resumo por tipo de dia (exclui feriados e anomalias das médias)
    resumo_tipos = (
        diario.loc[
            ~diario["tipo_dia"].isin(["feriado", "anomalia_cobertura", "especial_eleicao"])
        ]
        .groupby("tipo_dia")
        .agg(
            dias=("data", "count"),
            percentual_medio=("percentual_baixa_velocidade", "mean"),
            percentual_min=("percentual_baixa_velocidade", "min"),
            percentual_max=("percentual_baixa_velocidade", "max"),
        )
        .round(2)
    )
    resumo_tipos.to_csv(SAIDA / "resumo_tipos_dia.csv")

    print("=== Resumo diário ===")
    print(diario.to_string(index=False))
    print("\n=== Resumo por tipo de dia (feriados/anomalias excluídos) ===")
    print(resumo_tipos.to_string())

    fig, axes = plt.subplots(2, 1, figsize=(12, 9))

    # Cores por tipo de dia
    cores = []
    for tipo in diario["tipo_dia"]:
        if tipo == "feriado":
            cores.append("gray")
        elif tipo == "anomalia_cobertura":
            cores.append("orange")
        elif tipo == "especial_eleicao":
            cores.append("purple")
        elif tipo == "sabado":
            cores.append("steelblue")
        elif tipo == "domingo":
            cores.append("lightgreen")
        else:
            cores.append("firebrick")

    axes[0].bar(
        diario["data"].astype(str),
        diario["percentual_baixa_velocidade"],
        color=cores,
    )
    axes[0].set_title("Percentual de baixa velocidade (<15 km/h) por dia")
    axes[0].set_ylabel("%")
    axes[0].tick_params(axis="x", rotation=90)
    axes[0].grid(alpha=0.3)

    axes[1].bar(
        diario["data"].astype(str),
        diario["veiculos_max_por_hora"],
        color="seagreen",
    )
    axes[1].set_title("Cobertura: máximo de veículos únicos por hora e dia")
    axes[1].set_ylabel("veículos")
    axes[1].tick_params(axis="x", rotation=90)
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(SAIDA / "comparativo_dias.png", dpi=150)
    print(f"\nArquivos salvos em: {SAIDA}")


if __name__ == "__main__":
    main()