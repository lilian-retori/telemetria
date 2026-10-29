"""Consolida auditorias diarias em qualidade por dia e por veiculo.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\consolidar_qualidade.py

Entradas: outputs/AAAA-MM-DD/tables/auditoria.csv e qualidade_por_veiculo.csv
Saidas:    outputs/comparativo/qualidade_por_dia.csv
           outputs/comparativo/qualidade_por_veiculo_mes.csv
"""

import re
from pathlib import Path
import pandas as pd

RAIZ_OUT = Path("outputs")
SAIDA = RAIZ_OUT / "comparativo"
SAIDA.mkdir(parents=True, exist_ok=True)

PADRAO_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def linhas_auditoria(dia_dir):
    aud = pd.read_csv(dia_dir / "tables" / "auditoria.csv")
    d = {r["categoria"]: int(r["quantidade"]) for _, r in aud.iterrows()}
    return d


def main():
    dias = sorted(d for d in RAIZ_OUT.iterdir() if d.is_dir() and PADRAO_DIA.match(d.name))
    registros = []
    veiculos = []
    for dia_dir in dias:
        tabelas = dia_dir / "tables"
        aud = tabelas / "auditoria.csv"
        qual = tabelas / "qualidade_por_veiculo.csv"
        if not aud.exists() or not qual.exists():
            continue
        metrics = linhas_auditoria(tabelas) if False else linhas_auditoria(dia_dir)
        orig = metrics.get("registros_originais", 0)
        aceitos = metrics.get("registros_aceitos_apos_validacao", 0)
        validos = metrics.get("pares_com_velocidade_valida", 0)
        registros.append({
            "data": dia_dir.name,
            "registros_originais": orig,
            "registros_aceitos": aceitos,
            "pares_velocidade_valida": validos,
            "percentual_aceito": round(100 * aceitos / orig, 2) if orig else None,
            "percentual_velocidade_valida": round(100 * validos / aceitos, 2) if aceitos else None,
            "motivos": {
                "duplicata_identica": metrics.get("duplicata_identica", 0),
                "timestamp_conflitante": metrics.get("timestamp_conflitante", 0),
                "intervalo_acima_limite": metrics.get("pares_com_intervalo_invalido", 0),
            },
        })
        q = pd.read_csv(qual)
        q["data"] = dia_dir.name
        veiculos.append(q)

    df = pd.DataFrame(registros)
    df.to_csv(SAIDA / "qualidade_por_dia.csv", index=False)
    print(f"Dias consolidados: {len(df)}")
    print(df[["data","registros_aceitos","pares_velocidade_valida","percentual_velocidade_valida"]].to_string(index=False))

    if veiculos:
        todos = pd.concat(veiculos, ignore_index=True)
        por_veiculo = todos.groupby("VEIC").agg(
            dias=("data","nunique"),
            registros=("registros_aceitos","sum"),
            pares_validos=("pares_validos","sum"),
            pares_intervalo_acima_limite=("pares_intervalo_acima_limite","sum"),
            pares_velocidade_acima_limite=("pares_velocidade_acima_limite","sum"),
        ).assign(
            percentual_pares_validos=lambda x: (x.pares_validos*100/x.registros).round(2)
        ).reset_index()
        por_veiculo.to_csv(SAIDA / "qualidade_por_veiculo_mes.csv", index=False)
        piores = por_veiculo.nsmallest(10, "percentual_pares_validos")
        print("\nPiores 10 veiculos no mes (percent_pares_validos):")
        print(piores[["VEIC","dias","registros","percentual_pares_validos"]].to_string(index=False))
    print(f"\nArquivos salvos em {SAIDA}")

if __name__ == "__main__":
    main()