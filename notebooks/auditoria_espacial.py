"""Auditoria espacial dos Top 20 gargalos de maior intensidade.

Rode com o ambiente virtual ativo, dentro de projeto-telemetria:

    python .\auditoria_espacial.py

Para cada gargalo do Top 20 (classe fora_de_parada), responde:
1. Quais linhas mais registraram lentidao ali (o corredor real)
2. Em quais horas a lentidao aparece (perfil por tipo de dia)
3. Em quantos dias do mes o gargalo esteve ativo

Mudanca em relacao a versao anterior: o Top 20 agora e da maior
INTENSIDADE (percentual_lentidao) e nao do maior volume bruto.
Gargalo e onde a maior fatia do trafego fica lenta, nao onde
passam mais onibus.

Entradas:
outputs/comparativo/gargalos_classificados.csv  (com percentual_lentidao)
outputs/comparativo/resumo_diario.csv           (tipos de dia)
outputs/AAAA-MM-DD/tables/telemetria_com_metricas.csv
data/external/*linhas.json.xz (opcional: traduz COD da linha)

Saidas em outputs/comparativo/auditoria/:
auditoria_top20.csv
perfis_horarios_top20.csv
perfis_horarios_top20.png
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ_OUT = Path("outputs")
RAIZ_COMP = RAIZ_OUT / "comparativo"
RAIZ_AUD = RAIZ_COMP / "auditoria"
RAIZ_EXT = Path("data") / "external"
RAIZ_AUD.mkdir(parents=True, exist_ok=True)

TAMANHO_CELULA = 0.002
LIMIAR_KMH = 15
TOP_N = 20
PADRAO_PASTA_DIA = re.compile(r"\d{4}-\d{2}-\d{2}$")


def celula_de(lat: float, lon: float) -> str:
    return (
        f"{np.floor(lat / TAMANHO_CELULA) * TAMANHO_CELULA:.6f}_"
        f"{np.floor(lon / TAMANHO_CELULA) * TAMANHO_CELULA:.6f}"
    )


def ler_json_lista(arquivo: Path) -> pd.DataFrame:
    """Le o formato URBS: lista JSON por linha."""
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
    return pd.DataFrame(registros)


def carregar_nomes_linhas() -> dict:
    arquivos = sorted(RAIZ_EXT.glob("*_linhas.json.xz")) or sorted(
        RAIZ_EXT.glob("*linhas.json.xz")
    )
    if not arquivos:
        print("(linhas.json.xz nao encontrado; codigos ficarao sem nome)")
        return {}
    df = ler_json_lista(arquivos[-1])
    colunas = {c.upper(): c for c in df.columns}
    col_cod, col_nome = colunas.get("COD"), colunas.get("NOME")
    if not (col_cod and col_nome):
        print("(colunas COD/NOME nao achadas; codigos ficarao sem nome)")
        return {}
    return dict(zip(df[col_cod].astype(str), df[col_nome].astype(str)))


def coluna_linha(df: pd.DataFrame) -> str | None:
    for candidato in ("COD_LINHA", "CODLINHA", "COD"):
        if candidato in df.columns:
            return candidato
    return None


def main() -> None:
    gargalos = pd.read_csv(RAIZ_COMP / "gargalos_classificados.csv")

    if "percentual_lentidao" not in gargalos.columns:
        raise SystemExit(
            "gargalos_classificados.csv sem percentual_lentidao. "
            "Rode primeiro o gargalos_filtrados.py novo e o cruzar_paradas.py."
        )

    top = (
        gargalos.loc[gargalos["classe"] == "fora_de_parada"]
        .sort_values("percentual_lentidao", ascending=False)
        .head(TOP_N)
        .reset_index(drop=True)
    )
    if top.empty:
        raise SystemExit("Sem gargalos fora_de_parada para auditar.")

    top["rank"] = range(1, len(top) + 1)
    top["rotulo"] = [
        f"#{r.rank} {r.parada_mais_proxima[:35]}"
        for r in top.itertuples()
    ]
    celulas_top = {
        celula_de(r.lat_centro, r.lon_centro): r.rotulo
        for r in top.itertuples()
    }

    tipos = pd.read_csv(RAIZ_COMP / "resumo_diario.csv")
    mapa_tipo = dict(zip(tipos["data"].astype(str), tipos["tipo_dia"]))

    nomes_linhas = carregar_nomes_linhas()

    pastas = sorted(
        p for p in RAIZ_OUT.iterdir()
        if p.is_dir()
        and PADRAO_PASTA_DIA.fullmatch(p.name)
        and (p / "tables" / "telemetria_com_metricas.csv").exists()
    )
    print(f"Auditando {len(celulas_top)} gargalos em {len(pastas)} dias...")

    ocorrencias = []
    for pasta in pastas:
        df = pd.read_csv(
            pasta / "tables" / "telemetria_com_metricas.csv",
            usecols=lambda c: c
            in {"VEIC", "DTHR", "LAT", "LON", "VELOCIDADE_KMH",
                "COD_LINHA", "CODLINHA", "COD"},
            parse_dates=["DTHR"],
            dtype={"COD_LINHA": "string", "CODLINHA": "string", "COD": "string"},
        )
        col_linha = coluna_linha(df)

        df = df.loc[df["VELOCIDADE_KMH"] < LIMIAR_KMH]
        if df.empty:
            continue

        df["CELULA"] = [
            celula_de(a, b) for a, b in zip(df["LAT"], df["LON"])
        ]
        df = df.loc[df["CELULA"].isin(celulas_top)]
        if df.empty:
            continue

        data = df["DTHR"].dt.date.iloc[0]
        df["HORA_INT"] = df["DTHR"].dt.hour
        df["TIPO_DIA"] = mapa_tipo.get(str(data), "dia_util")
        df["GARGALO"] = df["CELULA"].map(celulas_top)
        df["LINHA"] = df[col_linha].astype(str) if col_linha else "?"
        df["DATA"] = data

        ocorrencias.append(
            df[["GARGALO", "DATA", "TIPO_DIA", "HORA_INT", "LINHA"]]
        )

    if not ocorrencias:
        raise SystemExit("Nenhuma ocorrencia lenta nas celulas do Top 20.")

    ocorr = pd.concat(ocorrencias, ignore_index=True)
    print(f"Ocorrencias lentas nos Top 20: {len(ocorr):,}")

    resumo_linhas = (
        ocorr.groupby(["GARGALO", "LINHA"])
        .size()
        .reset_index(name="obs_lentas")
        .sort_values(["GARGALO", "obs_lentas"], ascending=[True, False])
    )
    top_linhas = (
        resumo_linhas.groupby("GARGALO")
        .head(3)
        .groupby("GARGALO")
        .apply(
            lambda g: " | ".join(
                f"{nomes_linhas.get(cod, cod)} ({n})"
                for cod, n in zip(g["LINHA"], g["obs_lentas"])
            ),
            include_groups=False,
        )
        .reset_index(name="linhas_dominantes")
    )

    dias_ativos = (
        ocorr.groupby("GARGALO")["DATA"]
        .nunique()
        .reset_index(name="dias_ativo")
    )
    total_obs = (
        ocorr.groupby("GARGALO")
        .size()
        .reset_index(name="obs_lentas_mes")
    )

    perfil = (
        ocorr.groupby(["GARGALO", "TIPO_DIA", "HORA_INT"])
        .size()
        .reset_index(name="obs")
    )
    dias_por_tipo = (
        ocorr[["TIPO_DIA", "DATA"]].drop_duplicates()
        .groupby("TIPO_DIA")["DATA"].nunique()
    )
    perfil["obs_por_dia"] = perfil.apply(
        lambda r: r["obs"] / dias_por_tipo.get(r["TIPO_DIA"], 1), axis=1
    )
    perfil.to_csv(RAIZ_AUD / "perfis_horarios_top20.csv", index=False)

    perfil_du = perfil.loc[perfil["TIPO_DIA"] == "dia_util"]
    pico = (
        perfil_du.loc[
            perfil_du.groupby("GARGALO")["obs_por_dia"].idxmax()
        ][["GARGALO", "HORA_INT"]]
        .rename(columns={"HORA_INT": "hora_pico_dia_util"})
        .reset_index(drop=True)
    )

    auditoria = (
        top[["rotulo", "lat_centro", "lon_centro", "parada_mais_proxima",
             "distancia_parada_m", "percentual_lentidao",
             "observacoes_validas"]]
        .rename(columns={"rotulo": "GARGALO"})
        .merge(total_obs, on="GARGALO")
        .merge(dias_ativos, on="GARGALO")
        .merge(pico, on="GARGALO", how="left")
        .merge(top_linhas, on="GARGALO", how="left")
    )
    auditoria.to_csv(RAIZ_AUD / "auditoria_top20.csv", index=False)

    print()
    print(auditoria.to_string(index=False, max_colwidth=45))

    n = len(auditoria)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(16, 3.2 * rows), sharex=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, garg in zip(axes, auditoria["GARGALO"]):
        sub = perfil_du.loc[perfil_du["GARGALO"] == garg]
        ax.bar(sub["HORA_INT"], sub["obs_por_dia"], color="firebrick")
        ax.set_title(garg, fontsize=8)
        ax.grid(alpha=0.3)
    for ax in axes[len(auditoria):]:
        ax.axis("off")
    fig.suptitle("Perfil horario de lentidao por gargalo (dias uteis) - Top intensidade")
    plt.tight_layout()
    plt.savefig(RAIZ_AUD / "perfis_horarios_top20.png", dpi=130)

    print()
    print("Arquivos salvos em", RAIZ_AUD)


if __name__ == "__main__":
    main()