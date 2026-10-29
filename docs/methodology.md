# Metodologia

## Unidade de análise

A unidade básica é o par de posições consecutivas do mesmo veículo. Para cada par, calcula-se distância geodésica e intervalo de tempo; a velocidade estimada é dada por:

\[
velocidade\_{km/h} = rac{distância\_{metros}}{tempo\_{segundos}} 	imes 3.6
\]

## Validação

O pipeline exige `VEIC`, `DTHR`, `LAT` e `LON`. Coordenadas devem estar nos intervalos geográficos globais e datas devem ser conversíveis. Duplicatas idênticas são removidas. Registros de um mesmo veículo com o mesmo timestamp, mas coordenadas diferentes, são marcados como conflitantes e excluídos do cálculo de movimento.

## Parâmetros padrão

| Parâmetro | Valor inicial | Finalidade |
|---|---:|---|
| Intervalo mínimo | maior que 0 s | Evitar divisão por zero e retrocesso temporal |
| Intervalo máximo | 300 s | Evitar interpretar deslocamentos longos como velocidade localizada |
| Velocidade máxima plausível | 80 km/h | Marcar outliers para investigação |
| Quase-parada | até 1 km/h | Categoria operacional separada |
| Baixa velocidade | menor que 15 km/h | Indicador exploratório de lentidão |

Esses parâmetros devem ser reavaliados conforme a frequência real da telemetria, contexto operacional e distribuição dos dados.

## Métricas

O resumo horário inclui observações válidas, observações de baixa velocidade, percentual de baixa velocidade, velocidade mediana e veículos únicos. O percentual lento é calculado apenas sobre observações com velocidade válida.

## Interpretação

O termo recomendado é **baixa velocidade observada**. Não se deve afirmar que cada ponto lento representa congestionamento. Para atribuir recorrência espacial, recomenda-se agregar os registros em células espaciais, trechos de rota ou buffers de pontos de parada e exigir cobertura mínima.

## Limitações

- A localização do veículo não identifica, por si só, a causa da velocidade baixa.
- Uma única data de observação não sustenta conclusões sobre padrões recorrentes de trânsito.
- Velocidade calculada entre pontos é uma aproximação e depende da frequência de coleta e da precisão do GPS.
- O projeto deve preservar privacidade: identificadores de veículo não precisam aparecer no mapa público.
