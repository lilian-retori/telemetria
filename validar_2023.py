#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
import subprocess, pandas as pd

def main():
    ap = argparse.ArgumentParser(description='Validação trimestre 2023 - mesmo pipeline de atraso')
    ap.add_argument('--de', required=True, help='YYYY-MM-DD')
    ap.add_argument('--ate', required=True, help='YYYY-MM-DD')
    ap.add_argument('--trajetorias', default='outputs/trajetorias_v2')
    ap.add_argument('--pontos', nargs='+', default=['data/external', 'coleta_curitiba'])
    ap.add_argument('--saida', default='outputs/validacao_2023')
    args = ap.parse_args()

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, 'atraso_tabela.py',
        '--trajetorias', args.trajetorias,
        '--coleta', 'coleta_curitiba',
        '--pontos'] + args.pontos + [
        '--de', args.de, '--ate', args.ate,
        '--saida', str(saida)
    ]
    print('Executando:', ' '.join(cmd))
    subprocess.run(cmd, check=True)

    # coleta o resumo gerado e adiciona metadados
    resumo_path = saida / 'resumo_atrasos.csv'
    if not resumo_path.exists():
        sys.exit('resumo_atrasos.csv não gerado — verifique trajetorias_v2 para o período de 2023')
    df = pd.read_csv(resumo_path)
    df['validacao'] = '2023_Q3'
    df.to_csv(saida / 'resumo_validacao_2023_q3.csv', index=False)
    print(df.groupby('DIA').agg(
        dias=('data','nunique'),
        linhas_mediana=('linhas','median'),
        p90_mediano=('atraso_p90_min','median'),
        p90_max=('atraso_p90_min','max')).round(1).to_string())
    print(f'\nSalvo em {saida}/resumo_validacao_2023_q3.csv')

if __name__ == '__main__':
    main()