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
extrato-pdf-web
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
python scripts\gerar_pdfs_rasterizados.py
python scripts\run_experimentos.py --corpus pdf-nativo --condicoes A,C
python scripts\run_experimentos.py --corpus pdf-200-dpi --condicoes B,C
python scripts\calcular_metricas.py --resultados resultados\experimentos\pdf-nativo --referencias dados\referencia_manual --saida resultados\metricas\pdf-nativo
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
| `dados/entrada/pdf nativo/` | PDFs com texto nativo (não versionados - LGPD) |
| `dados/entrada/pdf-100-dpi/` | Mesmos arquivos, só imagem, rasterizados a 100 DPI |
| `dados/entrada/pdf-200-dpi/` | Mesmos arquivos, só imagem, rasterizados a 200 DPI |
| `dados/entrada/pdf-300-dpi/` | Mesmos arquivos, só imagem, rasterizados a 300 DPI |
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
- Corpus sem PDFs escaneados reais com referência manual. Há digitalizações sintéticas a 100, 200 e 300 DPI, com o mesmo nome de arquivo, só para varrer a resolução do OCR. Na condição C, OCR é aplicado às páginas com menos de 40 caracteres, inclusive quando o documento foi classificado como nativo.
