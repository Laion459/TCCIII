# Pacote `extrato_pdf`

Implementação do pipeline de extração e validação de extratos bancários em PDF.

## Pacotes

| Pacote | Responsabilidade |
|--------|------------------|
| `cli` | Linha de comando (`extrato-pdf`) |
| `pipeline` | Orquestração do fluxo completo |
| `modulos` | Validador, classificador, OCR, parser, regras, etc. |
| `modelos` | Dataclasses e enums de domínio |
| `util` | Configuração e utilitários |
| `web` | Interface local FastAPI |

Documentação: `../../docs/arquitetura.md` e `../../docs/especificacao_tecnica.md`.
