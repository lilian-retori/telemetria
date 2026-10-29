# Metodologia e Fundamentação — Análise de Pontualidade do Transporte Coletivo de Curitiba

## 2. Relevância para os ODS e para o ecossistema geoespacial

O projeto apoia diretamente o **ODS 11 — Cidades e Comunidades Sustentáveis**, meta 11.2 (sistemas de transporte público seguros, acessíveis e sustentáveis). O objeto de análise é a pontualidade histórica de 45 linhas do transporte coletivo de Curitiba em três períodos (março/2017, agosto/2023, setembro/2026), construída sobre rastreamento GPS de operação real.

Contribuições concretas:
- **Monitoramento federal de serviço público**: o pipeline mede pontualidade contra a tabela oficial URBS, produzindo indicador auditável para fiscalização de concessão.
- **Subsídio à gestão urbana**: gargalos georreferenciados (células de ~200 m) mostram onde melhorar infraestrutura — ex.: Rua José Loureiro (p90 37 min em 2026) e Terminal Pinheirinho, que melhorou de 30 para 25 minutos no período.
- **Reprodutibilidade**: todo o pipeline (coleta, snap, casamento, análise) é executável em Jupyter, com dados de entrada rastreáveis (45 linhas × 3 períodos).

No ecossistema geoespacial brasileiro, o trabalho dialoga com a prática de **snap GPS→malha viária em raio**, cruzamento espaço-temporal de fontes municipais abertas e validação de dados de transito por suposição de simetria de itinerários — práticas documentadas em SBC/CoURB (ver seção 3).

## 3. Exemplos de Literatura

**Borges, J. C. N.; Lüders, R.; Silva, T.; Munaretto, A. (2023).** *Algoritmo para Detecção de Itinerários do Transporte Público Usando Dados de GPS dos Ônibus.* SBC/CoURB. Disponível em: https://sol.sbc.org.br/index.php/courb/article/view/24567. Workchair brasileiro (UTFPR) que resolve exatamente o problema de snap de GPS em itinerários — base metodológica original deste pipeline. Identificam itinerários válidos em 90% dos casos por interpolação temporal.

**Taparia, A. (2020).** *Bus Journey and Arrival Time Prediction based on Archived AVL/GPS data using Machine Learning.* MSc Thesis, Trinity College Dublin. Compara Regressão Linear, ANN e LSTM para predição de tempo de viagem; **Gradient Boosting foi melhor na estimativa de chegada** e principais features foram dwell time em checkpoints — a referência empírica que orienta a escolha de modelo desta documentação.

**Lin, W. H.; Zeng, J.** *Real Time Bus Arrival Time Prediction with GPS Data.* Virginia Tech. Trabalho clássico que estrutura as variáveis (trip time + dwell time + horários de chegada antecipada) e mostra que trips anteriores podem ser integradas a modelos tabulares.

## 4. Descrição dos Dados

- **Fonte**: Espelho C3SL/URBS da Prefeitura de Curitiba — dados de transporte coletivo da cidade
- **Arquivos**: `*_veiculos.json.xz` (GPS em tempo real, ~3 milhões de registros/dia), `*_tabelaLinha.json.xz` (tabela de horários oficial), `*_shapeLinha.json.xz` (itinerários georreferenciados)
- **Formato**: JSON comprimido (xz); telemetria com LAT/LON em vírgula decimal; DTHR em dd/mm/aaaa
- **Pré-processamento**: snap GPS→shape em raio de 200 m; correção de calendário (dia operacional = arquivo −1); filtragem de dias com captura truncada; casamento por coordenada geográfica (não nome) entre períodos
- **Cobertura**: 45 linhas, ~43 checkpoints, três períodos; 2017 teve 8 dias excluídos; agosto/2023 teve 13 e 17/08 ausentes por falta de fonte local

## 5. Metodologia — Escolha: Machine Learning Clássico

**Escolha**: Gradient Boosting Regressor (`sklearn.ensemble.GradientBoostingRegressor`).

**Justificativa**:
1. **Natureza tabular dos dados**: após agregação, o dataset é (linha × horário × dia) com features categóricas discretas — habitat natural de GBM, não de redes sequenciais.
2. **Volume**: ~150 mil observações por ano, com 45 entidades e ~100 checkpoints — insuficiente para treinar redes de profundidade (>1000 parâmetros por checkpoint de partida) sem overfitting.
3. **Interpretabilidade**: GBM oferece importância de features e SHAP — essencial para resposta ao gestor; LSTM é caixa-preta para o especialista em trânsito.
4. **Evidência empírica externa**: Taparia (2020) mostrou GBM superior a LSTM em dados AVL de tamanho comparável para previsão de chegada.

**Modelagem**: Alvo = atraso em minutos por (linha × horário × dia_semana). Features: COD (linha), hora do dia em bins de 30 min, DIA (1/2/3). Validação temporal: treino em 2017 + 2023, teste em 2026. Métrica: MAE em minutos, comparado a baseline de média histórica da linha.

**Produto**: previsão do p90 de atraso por célula, o que pode ser traduzido em mapa de risco de atraso horários críticos. Deep learning (LSTM/GRU) fica como work future para dados de itinerário completo (checkpoints intermediários em série temporal).
