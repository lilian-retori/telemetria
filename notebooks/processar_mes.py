"""Processa todos os arquivos veiculos*.json.xz de uma pasta.

Como usar, dentro de projeto-telemetria, com o ambiente virtual ativo::

    python .\processar_mes.py

Principios:
- Um arquivo por vez, na ordem por nome.
- A pasta de saida do dia e usada como marcador: se o CSV de qualidade
  por veiculo ja existe, o arquivo correspondente nao e reprocessado.
- O log e atualizado apos cada arquivo, nunca so no final do lote.
- Cada execucao mostra inicio, termino e duracao no terminal.
- A data de conteudo dos arquivos e o dia anterior ao nome do arquivo.
"""

import re
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("outputs")
LOG = OUT / "comparativo" / "processamento_log.csv"
LOG.parent.mkdir(parents=True, exist_ok=True)

PADRAO = re.compile(r"^(\d{4})_(\d{2})_(\d{2})_veiculos\.json\.xz$")


def arquivos_de_veiculos() -> list[Path]:
    return sorted(
        (p for p in RAW.iterdir() if p.name and PADRAO.match(p.name)),
        key=lambda p: p.name,
    )


def data_conteudo(arquivo: Path) -> date:
    """Data real da telemetria: o dia anterior a data do nome do arquivo."""
    m = PADRAO.match(arquivo.name)
    ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return date(ano, mes, dia) - timedelta(days=1)


def pasta_do_dia(arquivo: Path) -> Path:
    return OUT / data_conteudo(arquivo).isoformat()


def ja_processado(arquivo: Path) -> bool:
    """Concluido = qualidade_por_veiculo.csv presente na pasta do dia.

    O arquivo so e resolvido quando o pipeline dispara com exit code 0
    e o CSV de qualidade existe; marcacoes antigas faltando a coluna
    contam como pendente.
    """
    tabelas = pasta_do_dia(arquivo) / "tables"
    return (tabelas / "qualidade_por_veiculo.csv").exists()


def gravar_log(registros: list[dict]) -> None:
    pd.DataFrame(registros).to_csv(LOG, index=False)


def main() -> None:
    arquivos = arquivos_de_veiculos()
    if not arquivos:
        raise SystemExit("Nenhum arquivo *_veiculos.json.xz em data/raw.")

    print(f"{len(arquivos)} arquivos encontrados em {RAW}.")
    registros: list[dict] = []

    for i, arquivo in enumerate(arquivos, start=1):
        print(f"\n[{i}/{len(arquivos)}] {arquivo.name}")

        if ja_processado(arquivo):
            registros.append({
                "arquivo": arquivo.name,
                "status": "OK",
                "detalhe": f"ja existia {pasta_do_dia(arquivo) / 'tables' / 'qualidade_por_veiculo.csv'}",
            })
            gravar_log(registros)
            print("  PULADO (pasta do dia ja contem qualidade_por_veiculo.csv).")
            continue

        inicio = time.perf_counter()
        resultado = subprocess.run(
            ["telemetria-pipeline", "--input", str(arquivo)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duracao = time.perf_counter() - inicio

        if resultado.returncode != 0:
            registros.append({
                "arquivo": arquivo.name,
                "status": "ERRO",
                "detalhe": resultado.stderr.strip().splitlines()[-1]
                if resultado.stderr.strip() else "",
            })
            gravar_log(registros)
            print(f"  ERRO apos {duracao/60:.1f} min; detalhe no log.")
            continue

        gravar_log(registros + [{
            "arquivo": arquivo.name,
            "status": "OK",
            "detalhe": f"concluido em {duracao/60:.1f} min",
        }])
        print(f"  OK (duracao: {duracao/60:.1f} min).")

    print("\n--- RESUMO DO PROCESSAMENTO ---")
    log = pd.read_csv(LOG)
    ultimas = registros[-31:] if registros else []
    resumo = pd.DataFrame(ultimas) if ultimas else log
    print(resumo.to_string(index=False))
    print(f"\nLog atualizado em: {LOG}")
    erros = log.loc[log["status"] == "ERRO"] if not log.empty else log
    if not erros.empty:
        print(f"\nATENCAO: {len(erros)} arquivo(s) falharam.")


if __name__ == "__main__":
    main()