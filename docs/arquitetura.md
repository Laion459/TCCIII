# Arquitetura — extrato_pdf

```
PDF → Validador → Extrator nativo → Classificador → Estratégia textual (A/B/C)
    → Localizador → Parser → Motor de regras → Serializador
    → resultado.json / relatorio.txt / execucao.log
```

## Módulos (`src/extrato_pdf/modulos`)

| Módulo | Função |
|--------|--------|
| `validador` | PDF válido/corrompido |
| `extrator_nativo` | Texto PyMuPDF |
| `classificador` | nativo / escaneado / híbrido |
| `extrator_ocr` | Tesseract por página |
| `estrategia_texto` | Condições A/B/C |
| `localizador` | Pontuação de páginas (§5.5) |
| `instituicao` | Padrões configuráveis |
| `parser` | Campos agregados (piloto SICOOB) |
| `normalizador` | Monetário BR → Decimal |
| `regras` | R01–R08 / status final |
| `serializador` | JSON, TXT, log |
| `metricas` | Comparação com referência |

## Condições experimentais

| Cond. | Texto |
|-------|-------|
| A | Somente nativo |
| B | Somente OCR |
| C | Integrado: nativo; OCR se escaneado; híbrido página a página |

## Pacotes

- `cli` — interface de linha de comando
- `pipeline` — orquestração (Algoritmo 1)
- `modelos` — dataclasses / enums
- `util` — configuração
- `web` — interface local FastAPI (painel, lote, métricas, configuração)

Especificação completa: `docs/especificacao_tecnica.md`.
