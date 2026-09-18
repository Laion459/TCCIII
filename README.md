# Extração e Análise de Consistência de Extratos Bancários em PDF

**Pacote:** `extrato_pdf`  
**Autor:** Leonardo Dario Borges  
**Orientador:** Marcelo Dornbusch Lopes, M.Sc.  
**Instituição:** UNIVALI - Ciência da Computação - TCC 3

## Descrição

Pipeline local que classifica PDFs, obtém texto (nativo e/ou OCR), localiza o extrato, extrai saldos e totais, valida consistência aritmética (tolerância R$ 0,01) e gera JSON, TXT e log. Inclui interface web para operação e análise dos experimentos A/B/C.

## Objetivo experimental

Avaliar a abordagem integrada (condição C) frente à extração nativa isolada (A) e OCR isolado (B), conforme desenho do TCC 2.

## Tecnologias

- Python ≥ 3.11 (testado com 3.12)
- PyMuPDF, pytesseract, Pillow, FastAPI, pytest
- Tesseract OCR (Windows: configurar em `config/default.json`)

## Instalação

```powershell
cd "TCC 3\codigos"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Confirme `ocr.tesseract_cmd` em `config/default.json`. Para OCR mais rápido, ajuste `ocr.workers` (padrão: 4).

## Execução - CLI

```powershell
extrato-pdf "dados\entrada\contas 012025.pdf" --condicao C --saida resultados\experimentos\condicao_c
```

Saída por PDF em `<saida>/<nome>/`: `resultado.json`, `relatorio.txt`, `execucao.log`.

## Execução - interface web

```powershell
extrato-pdf-web
# http://127.0.0.1:8000
```

Menu: Painel · PDFs · Processar · Lote · Resultados · Métricas · Validação · Config · Ajuda.  
Processamento local (`127.0.0.1`); barra de progresso e cancelamento em lotes longos.

## Experimentos

```powershell
python scripts\run_experimentos.py --entrada dados\entrada --saida resultados\experimentos --condicoes A,B,C
python scripts\calcular_metricas.py --resultados resultados\experimentos --referencias dados\referencia_manual --saida resultados\metricas
python scripts\validar_saidas.py --pasta resultados\experimentos
```

A condição **B** (OCR em todas as páginas) é lenta em PDFs grandes.

## Testes

```powershell
pytest -q
```

## Estrutura de dados

| Pasta | Uso |
|-------|-----|
| `dados/entrada/` | PDFs do experimento (não versionados - LGPD) |
| `dados/referencia_manual/` | Ground truth manual por documento |
| `dados/documentos_teste/` | Reservada para fixtures de teste |
| `resultados/` | Saídas e métricas (local) |
| `config/` | Parâmetros e padrões de instituição |

## Documentação

| Arquivo | Conteúdo |
|---------|----------|
| `docs/especificacao_tecnica.md` | Especificação técnica do artefato |
| `docs/arquitetura.md` | Módulos e condições A/B/C |
| `docs/decisoes-pendentes.md` | Decisões DP01–DP15 |
| `docs/checklist_validacao.md` | Checklist operacional pós-experimento |
| `docs/estrutura_testes.md` | Estratégia de testes |

Requisitos formais e fundamentação: TCC 2 (`tcc2_pronto_posbanca.md`).

## Limitações

- Piloto calibrado para layouts Sicoob e Caixa (conta corrente) presentes na base.
- Sem deep learning; sem conciliação linha a linha.
- Corpus sem PDFs escaneados reais; condição C ≡ A na execução atual.
