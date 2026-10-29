# %%
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

try:
    PASTA_SCRIPT = Path(__file__).resolve().parent
except NameError:
    PASTA_SCRIPT = Path.cwd()

if not (PASTA_SCRIPT / 'kpis_3periodos.csv').exists():
    if (PASTA_SCRIPT.parent / 'notebooks' / 'kpis_3periodos.csv').exists():
        PASTA_SCRIPT = PASTA_SCRIPT.parent / 'notebooks'
if not (PASTA_SCRIPT / 'kpis_3periodos.csv').exists():
    raise FileNotFoundError(f'CSVs ausentes em {PASTA_SCRIPT}')
print(f'Dados lidos de: {PASTA_SCRIPT}')

# %% [markdown]
# # Pontualidade do Transporte Coletivo — Curitiba
# ## Comparativo: março/2017 | agosto/2023 | setembro/2026
#
# **Pipeline**: GPS -> snap em shape (raio 200 m) -> casamento com a tabela oficial URBS -> mediana de passagens na janela ±45 min.
#
# ## CAPA DE COBERTURA
#
# | Período | Dias totais | Dias analisáveis | Linhas | Obs. limpas | Nota |
# |---|---|---|---|---|---|
# | 2017-03 | 30 | 22 | 45 | 123.960 | 8 dias com GPS truncado |
# | 2023-08 | 28 | 28 | 45 | 137.719 | 13/08 e 17/08 sem GPS local |
# | 2026-09 | 29 | 29 | 45 | 147.475 | completo |
#
# **Limitações**: janela ±45 min; ~43 checkpoints com viés de terminal; casamento sem identidade de viagem; 48 células comuns linha x ponto; nomenclatura instável entre períodos (casado por coordenada).

# %%
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

try:
    DIR = Path(__file__).resolve().parent
except NameError:
    DIR = Path.cwd()
if not (DIR / 'kpis_3periodos.csv').exists():
    DIR = DIR.parent / 'notebooks'

kpi = pd.read_csv(DIR / 'kpis_3periodos.csv')
print(kpi.to_string(index=False))

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
axes[0].bar(kpi.periodo, kpi.p90_D1, color=['#44707C','#B37F1F','#2E86C1'])
axes[0].set_title('p90 - dias uteis (DIA 1)'); axes[0].set_ylabel('minutos'); axes[0].grid(axis='y', alpha=0.25)

x = range(len(kpi)); w = 0.35
axes[1].bar([i-w/2 for i in x], kpi.p90_sab, width=w, label='Sabado', color='#7D3C98')
axes[1].bar([i+w/2 for i in x], kpi.p90_dom, width=w, label='Domingo', color='#C0392B')
axes[1].set_xticks(list(x)); axes[1].set_xticklabels(kpi.periodo)
axes[1].set_title('p90 - fim de semana'); axes[1].set_ylabel('minutos'); axes[1].grid(axis='y', alpha=0.25); axes[1].legend()
plt.tight_layout(); plt.show()

# %% [markdown]
# **Leitura**: dias úteis melhoram continuamente (15,5 → 12,0 → 12,0 min). Domingo: 10 → 14 → 12. Sábado estável em 12–13.

# %%
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

try:
    DIR = Path(__file__).resolve().parent
except NameError:
    DIR = Path.cwd()
if not (DIR / 'kpis_3periodos.csv').exists():
    DIR = DIR.parent / 'notebooks'

scat = pd.read_csv(DIR / 'historico_linha_3periodos.csv')
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

for ax, (p1, p2) in zip(axes, [('2017','2023'),('2023','2026'),('2017','2026')]):
    e1, e2 = f'p90_{p1}', f'p90_{p2}'
    for _, r in scat.iterrows():
        cor = '#2E86C1' if r[e2] < r[e1]-2 else ('#C0392B' if r[e2] > r[e1]+2 else '#7F8C8D')
        ax.scatter(r[e1], r[e2], s=28, color=cor, alpha=0.7)
        ax.annotate(r.COD, (r[e1], r[e2]), fontsize=7, alpha=0.8)
    lim = max(scat[e1].max(), scat[e2].max()) + 2
    ax.plot([0,lim],[0,lim],'k--',alpha=0.3,linewidth=1)
    ax.set_xlabel(f'p90 {p1} (min)'); ax.set_ylabel(f'p90 {p2} (min)')
    ax.set_title(f'{p1} x {p2}'); ax.grid(alpha=0.2)
plt.tight_layout(); plt.show()

print(scat[['COD','p90_2017','p90_2023','p90_2026','delta_17_26']].sort_values('delta_17_26').to_string(index=False))

# %% [markdown]
# *Abaixo da diagonal = melhorou. Acima = piorou. Destaques: linha 902 (26 min em 2017), 464 (33,5 em 2026), 365 (24 em 2017).*

# %%
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

try:
    DIR = Path(__file__).resolve().parent
except NameError:
    DIR = Path.cwd()
if not (DIR / 'kpis_3periodos.csv').exists():
    DIR = DIR.parent / 'notebooks'

mapa = pd.read_csv(DIR / 'gargalos_mapa_3periodos.csv')
fig, axes = plt.subplots(1, 3, figsize=(16, 6), subplot_kw={'aspect':'equal'})

for ax, per in zip(axes, ['2017','2023','2026']):
    sc = ax.scatter(mapa.plon, mapa.plat, c=mapa[f'p90_{per}'], cmap='RdYlBu_r',
                    s=np.sqrt(mapa[f'obs_{per}'])/10, alpha=0.75, edgecolor='k', linewidth=0.5)
    fig.colorbar(sc, ax=ax, label='p90 (min)')
    ax.set_xlabel('longitude'); ax.set_ylabel('latitude')
    ax.set_title(f'p90 {per}'); ax.grid(alpha=0.2)
plt.tight_layout(); plt.show()

print('Gargalos - top 10 por p90 2026:')
print(mapa[['plat','plon','obs_2026','p90_2017','p90_2023','p90_2026','delta_17_26','status']]
      .sort_values('p90_2026', ascending=False).head(10).to_string(index=False))

# %% [markdown]
# ## Limitações e próximos passos
# 1. Janela ±45 min — cauda não medida.
# 2. Viés de terminal — adicionar pontos intermediários antes de falar de malha.
# 3. Sem identidade de viagem.
# 4. 2017 com dias purgados — justificativa documentada.
# 5. Intermitência de 2026 — documentada por data e linha.
#
# **Próximos passos**: refactor de checkpoints -> modelo preditivo ML (linha x horario x dia-semana, 3 periodos) -> investigacao da intermitencia de 2026.