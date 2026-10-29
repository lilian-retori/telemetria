# %% [markdown]
# # Modelo GBM — p90 do atraso por passagem programada
# **Alvo**: quantil 0,9 do atraso (regressão quantílica). **Validação**: temporal (treino em períodos anteriores, teste no posterior).
# **Como rodar**: execute a CÉLULA 1 primeiro (treina e salva resultados em `outputs/modelo_gbm/`). As células 2–5 só leem esses arquivos e podem ser rodadas em qualquer ordem.

# %% CÉLULA 1 — dados, features, treino e salvamento
from pathlib import Path
import time, json
import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import make_scorer, mean_pinball_loss
except ImportError as e:
    raise ImportError("Instale com: pip install scikit-learn") from e

Q = 0.9
SEED = 42
DIAS_FRACOS_17 = {'2017-03-02', '2017-03-03', '2017-03-07', '2017-03-10',
                  '2017-03-14', '2017-03-15', '2017-03-30', '2017-03-31'}

def achar_raiz():
    try:
        base = Path(__file__).resolve().parent
    except NameError:
        base = Path.cwd()
    for p in [base, *base.parents][:5]:
        if (p / 'outputs').is_dir():
            return p
    raise FileNotFoundError("Pasta 'outputs' nao encontrada acima de " + str(base))

RAIZ = achar_raiz()
SAIDA = RAIZ / 'outputs' / 'modelo_gbm'
SAIDA.mkdir(parents=True, exist_ok=True)

def localizar(nome, padroes):
    for p in padroes:
        achados = sorted(RAIZ.glob(p))
        if achados:
            print(f'{nome}: {achados[0]}')
            return achados[0]
    raise FileNotFoundError(f'{nome}: nada encontrado em {padroes}')

t0 = time.time()
f17 = localizar('2017', ['outputs/atrasos_por_ponto_2017.csv', 'outputs/atrasos_v2_2017/atrasos_por_ponto.csv'])
f23 = localizar('2023', ['outputs/atrasos_2023_base_explicita_v1/atrasos_por_ponto.csv',
                         'outputs/atrasos_por_ponto_2023_be.csv'])
f26 = localizar('2026', ['outputs/atrasos_por_ponto_2026.csv', 'outputs/atrasos_v2_2026/atrasos_por_ponto.csv'])

a17 = pd.read_csv(f17); a17 = a17[~a17.data.isin(DIAS_FRACOS_17)]
a23 = pd.read_csv(f23)
a26 = pd.read_csv(f26)
a17['periodo'], a23['periodo'], a26['periodo'] = 2017, 2023, 2026
df = pd.concat([a17, a23, a26], ignore_index=True)

# ---- features (todas conhecidas ANTES da viagem: tabela + calendario + local) ----
df['COD'] = df.COD.astype(str)
df['minuto'] = df.previsto.str[:2].astype(int) * 60 + df.previsto.str[3:5].astype(int)
df['hora'] = df.minuto // 60
df['ponto_id'] = df.lat.round(4).astype(str) + '_' + df.lon.round(4).astype(str)
df['linha_ponto'] = df.COD + '|' + df.ponto_id
df = df.sort_values(['data', 'COD', 'ponto_id', 'minuto']).reset_index(drop=True)
df['headway'] = df.groupby(['data', 'COD', 'ponto_id']).minuto.diff()          # NaN na 1a viagem do dia
df['viagens_hora'] = df.groupby(['data', 'COD', 'ponto_id', 'hora']).minuto.transform('count')

FEAT_CAT = ['COD', 'linha_ponto']                       # <= 255 categorias (limite do HistGradientBoosting)
FEAT_NUM = ['hora', 'minuto', 'DIA', 'headway', 'viagens_hora']
print('observacoes por periodo:', df.groupby('periodo').size().to_dict(), f'({time.time()-t0:.1f}s)')

CATS = {c: sorted(df[c].unique()) for c in FEAT_CAT}
def preparar(d, feat_num=None):
    X = d[FEAT_CAT + (feat_num or FEAT_NUM)].copy()
    for c in FEAT_CAT:
        X[c] = pd.Categorical(X[c], categories=CATS[c])
    return X

def pinball(y, p, q=Q):
    return mean_pinball_loss(y, p, alpha=q)

def baseline_p90(train, test):
    """p90 historico por chaves progressivamente mais grossas (adversario justo)."""
    pred = pd.Series(np.nan, index=test.index)
    for k in (['linha_ponto', 'hora', 'DIA'], ['linha_ponto', 'DIA'], ['COD', 'DIA'], ['DIA']):
        tab = train.groupby(k).atraso_min.quantile(Q).rename('b').reset_index()
        m = test[k].merge(tab, on=k, how='left'); m.index = test.index
        pred = pred.fillna(m.b)
    return pred.fillna(train.atraso_min.quantile(Q))

def experimento(treino, teste, feat_num=None, rotulo='completo'):
    tr, te = df[df.periodo.isin(treino)], df[df.periodo == teste].copy()
    modelo = HistGradientBoostingRegressor(
        loss='quantile', quantile=Q, max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
        min_samples_leaf=60, categorical_features=[0, 1], random_state=SEED)
    modelo.fit(preparar(tr, feat_num), tr.atraso_min)
    te['p90_gbm'] = modelo.predict(preparar(te, feat_num))
    te['p90_base'] = baseline_p90(tr, te)
    te['p90_global'] = tr.atraso_min.quantile(Q)
    y = te.atraso_min.values
    res = dict(modelo=rotulo, treino='+'.join(map(str, treino)), teste=teste, n_teste=len(te),
               pinball_global=pinball(y, te.p90_global), pinball_baseline=pinball(y, te.p90_base),
               pinball_gbm=pinball(y, te.p90_gbm),
               cobertura_baseline=(y <= te.p90_base).mean(), cobertura_gbm=(y <= te.p90_gbm).mean())
    res['reducao_vs_baseline_pct'] = 100 * (1 - res['pinball_gbm'] / res['pinball_baseline'])
    return res, modelo, te

res_a, modelo_a, te_a = experimento([2017, 2023], 2026)      # cenario principal
res_b, _, _ = experimento([2017], 2023)                       # cenario secundario
res_c, _, _ = experimento([2017, 2023], 2026, feat_num=['hora', 'DIA', 'viagens_hora'], rotulo='sem minuto/headway')  # ablacao
metricas = pd.DataFrame([res_a, res_b, res_c]).round(4)
metricas.to_csv(SAIDA / 'metricas.csv', index=False)

# ---- incerteza: bootstrap por DIA (a unidade independente e o dia, nao a passagem) ----
def perda_vec(y, p, q=Q):
    d = y - p
    return np.where(d >= 0, q * d, (q - 1) * d)

te_a['perda_gbm'] = perda_vec(te_a.atraso_min.values, te_a.p90_gbm.values)
te_a['perda_base'] = perda_vec(te_a.atraso_min.values, te_a.p90_base.values)
por_dia = te_a.groupby('data')[['perda_gbm', 'perda_base']].sum()
g, b = por_dia.perda_gbm.values, por_dia.perda_base.values
rng = np.random.default_rng(SEED)
idx = rng.integers(0, len(g), size=(2000, len(g)))
reducao = 100 * (1 - g[idx].sum(1) / b[idx].sum(1))
ic = [float(np.percentile(reducao, 2.5)), float(np.percentile(reducao, 97.5))]
json.dump({'reducao_pct_ic95': ic, 'dias_teste': int(len(g))}, open(SAIDA / 'incerteza.json', 'w'))

# ---- importancia por permutacao (amostra) ----
amostra = te_a.sample(min(20000, len(te_a)), random_state=1)
scorer = make_scorer(mean_pinball_loss, alpha=Q, greater_is_better=False)
pi = permutation_importance(modelo_a, preparar(amostra), amostra.atraso_min, scoring=scorer, n_repeats=3, random_state=0)
imp = pd.DataFrame({'feature': FEAT_CAT + FEAT_NUM, 'importancia': pi.importances_mean}).sort_values('importancia', ascending=False)
imp.round(4).to_csv(SAIDA / 'importancia.csv', index=False)

# ---- calibracao (cobertura observada vs 90% desejado) ----
te_a['faixa'] = pd.cut(te_a.hora, [-1, 6, 9, 16, 19, 24], labels=['ate 6h', '7-9h', '10-16h', '17-19h', '20h+'])
te_a['decil_pred'] = pd.qcut(te_a.p90_gbm, 10, duplicates='drop', labels=False)
linhas = []
for col in ['DIA', 'faixa', 'decil_pred']:
    for nivel, gr in te_a.groupby(col, observed=True):
        linhas.append(dict(grupo=col, nivel=str(nivel), n=len(gr),
                           cobertura=(gr.atraso_min <= gr.p90_gbm).mean(),
                           pinball_gbm=pinball(gr.atraso_min, gr.p90_gbm),
                           pinball_base=pinball(gr.atraso_min, gr.p90_base)))
pd.DataFrame(linhas).round(4).to_csv(SAIDA / 'calibracao.csv', index=False)

te_a[['data', 'COD', 'PONTO', 'linha_ponto', 'hora', 'DIA', 'faixa', 'atraso_min', 'p90_gbm', 'p90_base']] \
    .to_csv(SAIDA / 'predicoes_2026.csv', index=False)

print(metricas.to_string(index=False))
print(f'\nReducao da perda vs baseline (2026): {res_a["reducao_vs_baseline_pct"]:.1f}%  IC95% bootstrap por dia: [{ic[0]:.1f}%, {ic[1]:.1f}%]')
print(imp.round(3).to_string(index=False))
print(f'\nResultados salvos em: {SAIDA}   ({time.time()-t0:.0f}s)')

# %% CÉLULA 2 — métricas: GBM vs baselines
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def _saida():
    try:
        base = Path(__file__).resolve().parent
    except NameError:
        base = Path.cwd()
    for p in [base, *base.parents][:5]:
        if (p / 'outputs' / 'modelo_gbm').is_dir():
            return p / 'outputs' / 'modelo_gbm'
    raise FileNotFoundError('Rode primeiro a CELULA 1 (treino).')

SAIDA = _saida()
m = pd.read_csv(SAIDA / 'metricas.csv')
print(m.to_string(index=False))

fig, ax = plt.subplots(figsize=(10, 4.8))
rot = [f"{r.modelo}\ntreino {r.treino}\nteste {r.teste}" for r in m.itertuples()]
x = range(len(m)); w = 0.26
for i, (col, nome, cor) in enumerate([('pinball_global', 'p90 global', '#B0B7BB'),
                                      ('pinball_baseline', 'baseline (linha x ponto x hora x dia)', '#44707C'),
                                      ('pinball_gbm', 'GBM', '#C0392B')]):
    barras = ax.bar([k + (i - 1) * w for k in x], m[col], width=w, label=nome, color=cor)
    ax.bar_label(barras, fmt='%.2f', fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels(rot)
ax.set_ylabel('perda pinball a 0,9 (menor = melhor)')
ax.set_title('Erro do p90 previsto'); ax.legend(fontsize=8); ax.grid(axis='y', alpha=0.25)
plt.tight_layout(); plt.savefig(SAIDA / 'fig_metricas.png', dpi=200, bbox_inches='tight'); plt.show()

# %% CÉLULA 3 — importância das features
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def _saida():
    try:
        base = Path(__file__).resolve().parent
    except NameError:
        base = Path.cwd()
    for p in [base, *base.parents][:5]:
        if (p / 'outputs' / 'modelo_gbm').is_dir():
            return p / 'outputs' / 'modelo_gbm'
    raise FileNotFoundError('Rode primeiro a CELULA 1 (treino).')

imp = pd.read_csv(_saida() / 'importancia.csv').sort_values('importancia')
fig, ax = plt.subplots(figsize=(7, 4))
ax.barh(imp.feature, imp.importancia, color='#2E86C1')
ax.set_xlabel('aumento da perda ao embaralhar a feature'); ax.set_title('Importancia por permutacao (teste 2026)')
ax.grid(axis='x', alpha=0.25)
plt.tight_layout(); plt.savefig(_saida() / 'fig_importancia.png', dpi=200, bbox_inches='tight'); plt.show()
print(imp.sort_values('importancia', ascending=False).to_string(index=False))

# %% CÉLULA 4 — calibração: o p90 previsto cobre 90% das passagens?
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def _saida():
    try:
        base = Path(__file__).resolve().parent
    except NameError:
        base = Path.cwd()
    for p in [base, *base.parents][:5]:
        if (p / 'outputs' / 'modelo_gbm').is_dir():
            return p / 'outputs' / 'modelo_gbm'
    raise FileNotFoundError('Rode primeiro a CELULA 1 (treino).')

cal = pd.read_csv(_saida() / 'calibracao.csv')
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
d = cal[cal.grupo == 'decil_pred'].copy(); d['k'] = d.nivel.astype(float)
axes[0].plot(d.k, d.cobertura * 100, marker='o', color='#C0392B')
axes[0].axhline(90, ls='--', color='k', alpha=0.4)
axes[0].set_xlabel('decil do p90 previsto (0 = menores previsoes)'); axes[0].set_ylabel('% de passagens abaixo do p90 previsto')
axes[0].set_title('Calibracao por decil'); axes[0].grid(alpha=0.25)
f = cal[cal.grupo == 'faixa']
axes[1].bar(f.nivel, f.cobertura * 100, color='#44707C')
axes[1].axhline(90, ls='--', color='k', alpha=0.4)
axes[1].set_ylim(80, 97); axes[1].set_title('Cobertura por faixa horaria'); axes[1].set_ylabel('%')
axes[1].grid(axis='y', alpha=0.25)
plt.tight_layout(); plt.savefig(_saida() / 'fig_calibracao.png', dpi=200, bbox_inches='tight'); plt.show()
print(cal.to_string(index=False))

# %% CÉLULA 5 — tradução para o gestor (previsto x observado em 2026)
from pathlib import Path
import pandas as pd

def _saida():
    try:
        base = Path(__file__).resolve().parent
    except NameError:
        base = Path.cwd()
    for p in [base, *base.parents][:5]:
        if (p / 'outputs' / 'modelo_gbm').is_dir():
            return p / 'outputs' / 'modelo_gbm'
    raise FileNotFoundError('Rode primeiro a CELULA 1 (treino).')

SAIDA = _saida()
p = pd.read_csv(SAIDA / 'predicoes_2026.csv')
u = p[p.DIA == 1]
q90 = lambda s: s.quantile(0.9)
pico = u[u.faixa == '17-19h'].groupby(['COD', 'PONTO']).agg(p90_prev_pico=('p90_gbm', 'mean'), p90_obs_pico=('atraso_min', q90))
entre = u[u.faixa == '10-16h'].groupby(['COD', 'PONTO']).agg(p90_prev_entre=('p90_gbm', 'mean'), p90_obs_entre=('atraso_min', q90))
tab = pd.concat([pico, entre], axis=1).dropna().round(0).sort_values('p90_obs_pico', ascending=False).reset_index()
tab.to_csv(SAIDA / 'tabela_gestor.csv', index=False)
print(tab.head(15).to_string(index=False))
r = tab.iloc[0]
print(f"\nLeitura para o gestor: na linha {r.COD}, ponto {r.PONTO}, dia util, pico da tarde (17-19h): "
      f"observado em 2026, 9 de cada 10 passagens tiveram atraso de ate {int(r.p90_obs_pico)} min "
      f"(o modelo previa em media {int(r.p90_prev_pico)} min).")