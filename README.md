# Telemetria de ônibus: baixa velocidade observada

Projeto geoespacial para analisar registros de telemetria de ônibus e identificar áreas e horários com **baixa velocidade observada**. O projeto não trata toda velocidade baixa como congestionamento: resultados são reportados com cobertura, regras de qualidade e limitações explícitas.

## Objetivo

Responder à pergunta:

> Quais áreas apresentam baixa velocidade recorrente nos veículos observados, em quais horários e com qual cobertura de dados?

## Estrutura

```text
src/telemetria/     Código do pacote
scripts/            Não utilizado; a execução é feita pelo módulo pipeline
data/raw/           Dados de entrada não versionados
data/processed/     Dados processados não versionados
outputs/tables/     Auditorias e métricas CSV
outputs/maps/       Mapas HTML
outputs/figures/    Figuras geradas
tests/              Testes automatizados
docs/               Documentação metodológica
```

## Instalação

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
```

No Windows:

```bash
.venv\Scripts\activate
```

No Linux/macOS:

```bash
source .venv/bin/activate
```

Instale o projeto e as ferramentas de desenvolvimento:

```bash
pip install -e ".[dev]"
```

Alternativamente:

```bash
pip install -r requirements.txt
```

## Dados de entrada

Coloque o arquivo JSON Lines compactado em `data/raw/`. O nome padrão esperado é:

```text
2026_10_06_veiculos.json.xz
```

O arquivo precisa ter as colunas:

- `VEIC`: identificador do veículo
- `DTHR`: data/hora no formato `dd/mm/aaaa HH:MM:SS`
- `LAT`: latitude
- `LON`: longitude

Coordenadas com vírgula decimal são aceitas. Dados brutos não devem ser enviados ao Git sem avaliação de privacidade, licença e tamanho do arquivo.

## Execução

```bash
telemetria-pipeline
```

Ou:

```bash
python -m telemetria.pipeline
```

Para informar outro arquivo:

```bash
python -m telemetria.pipeline --input data/raw/meu_arquivo.json.xz
```

Saídas principais:

- `outputs/tables/auditoria.csv`
- `outputs/tables/registros_rejeitados.csv`
- `outputs/tables/telemetria_com_metricas.csv`
- `outputs/tables/resumo_horario.csv`
- `outputs/maps/mapa_baixa_velocidade.html`

## Qualidade e interpretação

A velocidade é calculada entre posições consecutivas do mesmo veículo por meio da distância Haversine dividida pelo intervalo temporal. Pares com timestamps inválidos, coordenadas inválidas, intervalos não positivos ou lacunas excessivas são excluídos das métricas de velocidade.

O limiar padrão para baixa velocidade é inferior a 15 km/h. Esse valor é um parâmetro analítico, não prova de congestionamento. Consulte `docs/methodology.md` para limitações e decisões metodológicas.

## Testes e qualidade de código

```bash
pytest -q
ruff check src tests
black --check src tests
```

## Limitações

- Baixa velocidade pode representar parada operacional, semáforo, terminal, congestionamento, erro de GPS ou outros eventos.
- A análise é limitada ao período, à frota e à cobertura espacial disponíveis no arquivo de entrada.
- O mapa mostra observações de baixa velocidade; não é uma medição direta da velocidade de todo o tráfego urbano.
