# Seções 3 e 5 — versão final (números do seu terminal, 27/10/2026)

## 3. Exemplos de literatura

**Borges, J. C. N.; Lüders, R.; Silva, T.; Munaretto, A. (2023).** Algoritmo para Detecção de Itinerários do Transporte Público Usando Dados de GPS dos Ônibus. *Anais do VII Workshop de Computação Urbana (CoUrb)*, SBC. DOI: 10.5753/courb.2023.739.
O artigo define o problema de compatibilizar registros de GPS dos ônibus com o itinerário da linha, usando também a localização dos pontos. Como o envio de GPS falha, o algoritmo ajusta sequências incompatíveis com o itinerário programado. Os autores reportam que itinerários válidos são detectados em cerca de 90% dos dados da base, com exclusão de marcações inválidas e interpolação temporal de horários em pontos faltantes.
*Relação com este projeto*: é o mesmo tipo de problema da etapa de snap GPS→shape. Este projeto usa outro método (distância ao shape com raio de 200 m); o artigo é trabalho relacionado, não a origem do método.

**Taparia, A. (2020).** Bus Journey and Arrival Time Prediction based on Archived AVL/GPS data using Machine Learning. MSc Thesis, University of Dublin, Trinity College.
Para o tempo total de viagem, o trabalho compara Regressão Linear, ANN e LSTM; o LSTM supera a regressão linear e fica comparável à ANN. Para o tempo de chegada em paradas, compara Média Histórica, Regressão Linear e Gradient Boosting; o Gradient Boosting supera os demais e é mais robusto.
*Relação com este projeto*: a comparação de Gradient Boosting contra uma média histórica é análoga ao desenho deste trabalho (GBM contra baseline histórico). A tese NÃO compara Gradient Boosting com LSTM na mesma tarefa; a escolha de ML clássico aqui se justifica pelo volume e pela natureza tabular dos dados, não por esse trabalho.

**Lin, W.-H.; Zeng, J.** Real Time Bus Arrival Time Prediction with GPS Data. Virginia Polytechnic Institute and State University (Center for Transportation Research).
Estudo experimental em Blacksburg Transit (ambiente rural, 30 ônibus com GPS) que compara quatro algoritmos de estimativa de chegada, com análise de aderência à tabela e padrões de atraso a partir de GPS. No local estudado, o tempo de espera em pontos de controle de horário foi a informação mais relevante para o desempenho. O artigo não usa aprendizado de máquina.
*Relação com este projeto*: referência para a análise de aderência à tabela horária a partir de GPS. Ano de publicação não confirmado no texto lido.

**Referências de Curitiba citadas por Borges et al. (2023), a conferir antes de usar** (existência confirmada na lista de referências do artigo; conteúdo não lido):
Vila, J. J. R. et al. (2016). Urban mobility challenges: an exploratory analysis of public transportation data in Curitiba. *Revista de Informática Aplicada*, 12(1).
Peixoto, A.; Rosa, M.; Lüders, R.; Fonseca, K. (2020). Plataforma computacional para construção de um banco de dados de grafo do sistema de transporte de Curitiba. IV Workshop de Computação Urbana, SBC.

## 5. Metodologia — Machine Learning (Gradient Boosting com regressão quantílica)

**5.1 Problema e alvo.** Estimar o quantil 0,9 (p90) do atraso de uma passagem programada, dado a linha, o ponto de controle, o horário e o tipo de dia. O p90 é o indicador central do relatório e mede a cauda do atraso. O atraso é o medido pelo método do projeto (mediana das passagens GPS a até 200 m do ponto, na janela de ±45 min do horário previsto), não o atraso real por viagem.

**5.2 Dados.** 409.154 passagens: 123.960 (março/2017, 22 dias), 137.719 (agosto/2023, 28 dias) e 147.475 (setembro/2026, 29 dias), 45 linhas. Em 2017 foram excluídos 8 dias com captura de GPS comprometida.

**5.3 Features** (todas conhecidas antes da viagem): linha, par linha×ponto (coordenadas arredondadas), minuto do dia, hora, tipo de dia (1 útil, 2 sábado, 3 domingo), headway (minutos desde a viagem anterior da tabela, no mesmo ponto) e número de viagens programadas na hora. Variáveis derivadas da medição (horário real, número de observações no raio) foram excluídas por vazamento.

**5.4 Modelo.** HistGradientBoostingRegressor (scikit-learn) com loss='quantile', quantile=0,9; 300 iterações, taxa de aprendizado 0,06, 31 folhas, mínimo de 60 amostras por folha, semente 42. Escolha de ML clássico justificada por: dados tabulares, volume moderado (~150 mil passagens por período), interpretabilidade para o gestor e custo de implementação.

**5.5 Validação.** Temporal, sem embaralhar. Cenário principal: treino em 2017+2023, teste em 2026. Cenário secundário: treino em 2017, teste em 2023. Controle: modelo sem as features minuto e headway. Métricas: perda pinball a 0,9 (menor é melhor) e cobertura (fração das passagens com atraso ≤ p90 previsto; meta 90%). Baseline: p90 histórico por linha×ponto×hora×tipo de dia, com fallback para chaves mais grossas. Incerteza: bootstrap por dia (2.000 reamostragens).

**5.6 Resultados.**

| Cenário | p90 global | Baseline | GBM | Redução vs baseline | Cobertura GBM |
|---|---:|---:|---:|---:|---:|
| Treino 2017+2023 → teste 2026 | 1,940 | 1,7534 | 1,6169 | 7,8% (IC95% 7,1–8,7%) | 90,6% |
| Treino 2017 → teste 2023 | 2,017 | 1,9329 | 1,6800 | 13,1% | 91,8% |
| Sem minuto/headway, teste 2026 | 1,940 | 1,7534 | 1,6731 | 4,6% | 90,8% |

Importância por permutação (teste 2026): minuto do dia 0,326; headway 0,236; linha×ponto 0,224; viagens na hora 0,025; tipo de dia 0,008; hora 0,004; linha 0,001.

Cobertura por faixa horária: até 6h 93,4%; 7–9h 91,3%; 10–16h 89,1%; 17–19h 91,0%; 20h+ 90,2%. Por tipo de dia: úteis 90,9%; sábados 90,2%; domingos 88,4%. No pico da manhã (7–9h) a perda do GBM (1,590) é praticamente igual à do baseline (1,599).

**5.7 Limitações.**
1. O teste principal usa um único mês (setembro/2026); o intervalo de confiança cobre a variação entre dias, não a sazonal.
2. Cerca de 43% do ganho (7,8% para 4,6%) depende de minuto e headway, o que sugere reconhecimento de viagens específicas da tabela; o ganho de padrão geral é de aproximadamente 4,6%.
3. O modelo é bem calibrado no conjunto, mas erra bastante em pontos isolados (ex.: linha 865, Rua Paulo Gorski, pico da tarde: previsto 12 min, observado 34 min).
4. O alvo herda os limites do método de medição: janela de ±45 min, mediana de passagens, ~43 checkpoints com viés de terminal e ausência de identificação de viagem.
5. O modelo prevê pontos já vistos no treino (97% dos pares linha×ponto de 2026 existiam em 2017/2023); não generaliza para pontos novos.
6. Headway calculado apenas entre viagens casadas, o que pode distorcer o intervalo real da tabela.

**5.8 Uso para o gestor.** Reportar o p90 observado por linha×ponto×faixa como indicador principal e o modelo como complemento para estimar a cauda esperada. Em dia útil de 2026, no pico da tarde (17–19h), os maiores p90 observados foram: linha 865 / Rua Paulo Gorski (34 min), linha 865 / Praça Tiradentes (33), linha 825 / Bairro Vila Marqueto (29), linha 815 / Tuiuti Barigui (27) e linha 150 / Canal da Música (26). Na linha 865 o atraso se concentra no pico (p90 de 33–34 min contra 5–8 min entre os picos).
