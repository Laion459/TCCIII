# Decisões técnicas — status na implementação

Atualizado após implementação inicial do TCC 3.

| ID | Tema | Decisão adotada | Status |
|----|------|-----------------|--------|
| DP01 | Lib PDF | **PyMuPDF** (`pymupdf`) | Resolvido |
| DP02 | OCR | **pytesseract** + render PyMuPDF; `tesseract_cmd` em config | Resolvido |
| DP03 | Limiares classificação | `min_caracteres=40`; `percentual_minimo_nativo=90` | Resolvido |
| DP04 | Merge híbrido | Por página: nativo se >= min chars; senão OCR | Resolvido |
| DP05 | Totais entradas/saídas | Soma C/D na região do extrato SICOOB (ignorando saldos diários); sem conciliação linha a linha de validação | Resolvido |
| DP06 | Padrões saldo | Parser SICOOB: SALDO ANTERIOR + SALDO EM C.CORRENTE / último SALDO DO DIA | Resolvido (piloto) |
| DP07 | ID documento | `mapa_ids_documento` na config; senão hash | Resolvido |
| DP08 | CLI | `extrato-pdf PDF --condicao A\|B\|C --saida --config` | Resolvido |
| DP09 | TXT/log | Relatório humano + log com etapas/versões | Resolvido |
| DP10 | JSON falha | `null` + `status_processamento` + `alertas` | Resolvido |
| DP11 | 20 PDFs | Código aceita N; base ampliada a cargo do autor | Pendente (dados) |
| DP12 | Limiar localização | 8 (config) | Resolvido |
| DP13 | Divergência nativo/OCR | Alerta textual → `revisao_necessaria` via regras | Parcial (heurística simples) |
| DP14 | Empacotamento | `pyproject.toml` + `requirements.txt`; Python ≥ 3.11 | Resolvido |
| DP15 | LGPD | `.gitignore` em PDFs/resultados; não versionar PII | Resolvido (política) |

## Observação sobre classificação do piloto

Com limiar 90%, documentos com dezenas de páginas sem texto nativo tendem a `hibrido`, alinhado à referência manual do TCC 2. Ajuste fino permanece em `config/default.json`.
