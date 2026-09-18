# Especificação técnica - TCC 3

**Projeto:** Extração e Análise de Consistência de Dados de Extratos Bancários em Documentos PDF Heterogêneos  
**Autor:** Leonardo Dario Borges  
**Requisitos formais:** `TCC 2/revisao/tcc2_pronto_posbanca.md`  
**Status:** implementado - pipeline CLI, interface web local, experimentos A/B/C

---

## 1. Escopo

### Entregue

1. Pipeline modular em Python (CLI + interface web local).
2. Módulos: validação, classificação PDF, texto nativo, OCR condicional, localização de extrato, identificação de instituição, extração de campos, normalização BR, motor de regras R01–R08 / RN01–RN08, serialização JSON/TXT/log.
3. Condições experimentais A (nativo), B (OCR), C (integrada).
4. Testes unitários, de integração e funcionais (`pytest`).
5. Scripts de lote experimental, cálculo de métricas e validação de saídas.
6. Comparação automática com referência manual (quando disponível).

### Fora do escopo

- Deep learning / NER treinado.
- Conciliação linha a linha ou saldo diário por lançamento.
- APIs bancárias, processamento em nuvem.
- Garantia universal para qualquer banco sem validação empírica.

### Corpus e referência

- Meta documental: ≥ 20 PDFs com extrato identificável (piloto: SICOOB).
- Referência manual (ground truth) produzida **antes** da comparação automática - ver `dados/referencia_manual/`.

---

## 2. Arquitetura

```
PDF → Validador → Extrator nativo → Classificador → Estratégia textual (A/B/C)
    → Localizador → Parser → Normalizador → Motor de regras → Serializador
    → saida/{resultado.json, relatorio.txt, execucao.log}
```

Visão resumida dos pacotes: `docs/arquitetura.md`.

### Condições experimentais

| Condição | Estratégia de texto |
|----------|---------------------|
| A | Somente extração nativa |
| B | OCR em todas as páginas (Tesseract) |
| C | Integrada: nativo; OCR se escaneado; híbrido página a página |

### Fluxo (Algoritmo 1)

1. Validar PDF → se inválido: `nao_processavel`.
2. Extrair texto nativo por página; classificar `nativo` | `escaneado` | `hibrido`.
3. Obter texto conforme condição A/B/C.
4. Pontuar e selecionar páginas de extrato (limiar configurável, padrão 25).
5. Identificar instituição; extrair período e valores agregados.
6. Normalizar monetário BR; aplicar R06/R07; definir status final.
7. Serializar JSON, TXT e log com versões de bibliotecas e parâmetros.

---

## 3. Regras de negócio e consistência

### RN (negócio)

| ID | Regra |
|----|-------|
| RN01 | C = crédito; D = débito |
| RN02 | Padrão monetário brasileiro |
| RN03 | Escopo: conta corrente |
| RN04 | Conta capital fora do escopo |
| RN05 | Ignorar SAC, ouvidoria, limite, saldo bloqueado |
| RN06 | Período delimita movimentações |
| RN07 | Instituição por padrões configuráveis |
| RN08 | Processar apenas região de extrato |

### R (consistência)

| ID | Regra |
|----|-------|
| R06 | `saldo_final_calculado = saldo_inicial + entradas - saídas` |
| R07 | Tolerância: \|diferença\| ≤ R$ 0,01 |
| R08 | Sinalizar revisão quando ausente, ambíguo ou divergente |

Status de processamento: `consistente`, `inconsistente`, `incompleto`, `revisao_necessaria`, `nao_processavel`.

---

## 4. Contrato de saída (JSON)

Campos principais: `documento`, `extrato`, `valores`, `validacao`, `alertas`, `experimento` (condição, versões, parâmetros).

Valores monetários ausentes são representados como `null`. Cálculo interno usa `Decimal`; serialização com duas casas decimais.

---

## 5. Configuração

| Arquivo | Conteúdo |
|---------|----------|
| `config/default.json` | Tolerância, limiar de localização, pesos, OCR, classificação PDF, mapa de IDs |
| `config/instituicoes.json` | Padrões por instituição (piloto: SICOOB) |

Parâmetros editáveis pela interface web em `/config` (validação, OCR, classificação).

Decisões de implementação: `docs/decisoes-pendentes.md` (DP01–DP15).

---

## 6. Testes

| Tipo | Pasta | Foco |
|------|-------|------|
| Unitários | `tests/unitarios/` | Normalizador, regras, localizador, parser, OCR (mock) |
| Integração | `tests/integracao/` | Pipeline, serializador |
| Funcionais | `tests/funcionais/` | CLI, rotas web |

```powershell
pytest -q
```

Detalhamento: `docs/estrutura_testes.md`.

---

## 7. Experimentos e métricas

Scripts em `scripts/`:

```powershell
python scripts\run_experimentos.py --entrada dados\entrada --saida resultados\experimentos --condicoes A,B,C
python scripts\calcular_metricas.py --resultados resultados\experimentos --referencias dados\referencia_manual --saida resultados\metricas
python scripts\validar_saidas.py --pasta resultados\experimentos
```

Métricas por campo (TCC 2 §5.8): acerto de instituição, período, saldos; erros monetários; consistência; taxa de revisão.

Checklist operacional: `docs/checklist_validacao.md`.

---

## 8. Interface web

Camada local (`127.0.0.1`) para operação e visualização - painel, processamento, lote, resultados, métricas experimentais, validação e configuração. O núcleo científico permanece o pipeline CLI; dados não saem da máquina (LGPD).

```powershell
extrato-pdf-web
```
