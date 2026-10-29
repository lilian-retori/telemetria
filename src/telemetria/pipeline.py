"""Pipeline executavel da analise de telemetria."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .config import Config
from .features import adicionar_metricas_movimento
from .io import carregar_telemetria, salvar_csv
from .mapping import criar_mapa_baixa_velocidade
from .metrics import resumir_por_hora
from .validation import criar_auditoria, padronizar_colunas, validar_registros


def executar_pipeline(config: Config, etiqueta: str | None = None) -> None:
    """Executa leitura, validacao, metricas, auditoria e mapa.

    Cada execucao e salva em outputs/AAAA-MM-DD, usando a data real
    registrada na coluna DTHR apos a validacao dos dados.
    Se `etiqueta` for informada, vira sufixo: outputs/AAAA-MM-DD_etiqueta.
    """
    config.criar_diretorios()

    dados_brutos = carregar_telemetria(config.input_path)
    dados_padronizados = padronizar_colunas(dados_brutos)

    aceitos, rejeitados = validar_registros(dados_padronizados, config)

    if aceitos.empty:
        raise ValueError(
            "Nenhum registro valido restou apos a validacao. "
            "Verifique as colunas VEIC, DTHR, LAT e LON."
        )

    data_inicio = aceitos["DTHR"].min().date()
    data_fim = aceitos["DTHR"].max().date()

    if data_inicio != data_fim:
        nome_periodo = f"{data_inicio}_ate_{data_fim}"
    else:
        nome_periodo = str(data_inicio)

    if etiqueta:
        nome_periodo = f"{nome_periodo}_{etiqueta}"

    pasta_saida = config.tables_dir.parent / nome_periodo
    pasta_tabelas = pasta_saida / "tables"
    pasta_mapas = pasta_saida / "maps"
    pasta_figuras = pasta_saida / "figures"

    for pasta in (pasta_tabelas, pasta_mapas, pasta_figuras):
        pasta.mkdir(parents=True, exist_ok=True)

    telemetria = adicionar_metricas_movimento(aceitos, config)

    qualidade_veiculo = (
        telemetria.groupby("VEIC")
        .agg(
            registros_aceitos=("VEIC", "count"),
            pares_validos=("VELOCIDADE_VALIDA", "sum"),
            primeira_posicao=("MOTIVO_PAR_INVALIDO",
                lambda x: (x == "primeira_posicao_veiculo").sum()),
            pares_intervalo_zero_ou_negativo=("MOTIVO_PAR_INVALIDO",
                lambda x: (x == "intervalo_zero_ou_negativo").sum()),
            pares_intervalo_acima_limite=("MOTIVO_PAR_INVALIDO",
                lambda x: (x == "intervalo_acima_limite").sum()),
            pares_velocidade_acima_limite=("MOTIVO_PAR_INVALIDO",
                lambda x: (x == "velocidade_acima_limite").sum()),
        )
        .assign(
            percentual_pares_validos=lambda x: (
                x["pares_validos"].div(x["registros_aceitos"]).mul(100).round(2)
            )
        )
        .reset_index()
    )

    salvar_csv(qualidade_veiculo, pasta_tabelas / "qualidade_por_veiculo.csv")

    auditoria = criar_auditoria(
        total_original=len(dados_brutos),
        rejeitados=rejeitados,
        telemetria_com_metricas=telemetria,
    )

    resumo_horario = resumir_por_hora(telemetria)

    salvar_csv(rejeitados, pasta_tabelas / "registros_rejeitados.csv")
    salvar_csv(telemetria, pasta_tabelas / "telemetria_com_metricas.csv")
    salvar_csv(auditoria, pasta_tabelas / "auditoria.csv")
    salvar_csv(resumo_horario, pasta_tabelas / "resumo_horario.csv")

    criar_mapa_baixa_velocidade(
        telemetria,
        pasta_mapas / "mapa_baixa_velocidade.html",
        config.limiar_baixa_velocidade_kmh,
    )

    print("\nPipeline concluido.")
    print(f"Arquivo de origem: {config.input_path.name}")
    print(f"Data inicial encontrada em DTHR: {data_inicio}")
    print(f"Data final encontrada em DTHR: {data_fim}")
    print(f"Resultados salvos em: {pasta_saida}")
    print(f"Auditoria: {pasta_tabelas / 'auditoria.csv'}")
    print(f"Qualidade por veiculo: {pasta_tabelas / 'qualidade_por_veiculo.csv'}")
    print(f"Resumo horario: {pasta_tabelas / 'resumo_horario.csv'}")
    print(f"Mapa: {pasta_mapas / 'mapa_baixa_velocidade.html'}")


def parse_args() -> argparse.Namespace:
    """Le argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Analisa baixa velocidade em telemetria de onibus."
    )
    parser.add_argument("--input", type=Path, default=None,
        help="Caminho opcional para o arquivo JSON Lines .xz.")
    parser.add_argument("--max-intervalo-seg", type=int, default=None,
        help="Intervalo maximo aceito entre posicoes do mesmo veiculo.")
    parser.add_argument("--max-velocidade-kmh", type=float, default=None,
        help="Velocidade maxima considerada plausivel.")
    parser.add_argument("--limiar-baixa-velocidade-kmh", type=float, default=None,
        help="Limiar para classificar observacao como baixa velocidade.")
    parser.add_argument("--etiqueta", default=None,
        help="Sufixo opcional para nao sobrescrever resultados do mesmo dia.")
    return parser.parse_args()


def main() -> None:
    """Ponto de entrada do comando `telemetria-pipeline`."""
    args = parse_args()
    config = Config()

    if args.input is not None:
        config = replace(config, input_path=args.input)
    if args.max_intervalo_seg is not None:
        config = replace(config, max_intervalo_seg=args.max_intervalo_seg)
    if args.max_velocidade_kmh is not None:
        config = replace(config, max_velocidade_kmh=args.max_velocidade_kmh)
    if args.limiar_baixa_velocidade_kmh is not None:
        config = replace(config, limiar_baixa_velocidade_kmh=args.limiar_baixa_velocidade_kmh)

    executar_pipeline(config, etiqueta=args.etiqueta)


if __name__ == "__main__":
    main()