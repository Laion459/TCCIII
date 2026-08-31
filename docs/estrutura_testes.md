# Estrutura de testes e evidências

## Unitários

- Normalizador BR
- R06/R07/R08 e estados finais
- Pontuação de localização (pesos do TCC 2)
- Instituição SICOOB e ambiguidade
- Classificador com páginas sintéticas
- Parser com snippets do resumo

## Integração

- Pipeline com mock OCR
- Serialização em diretório temporário

## Funcionais

- CLI gera JSON + TXT + log
- `--condicao A|B|C` altera estratégia

## Experimentais / dados reais

- Base em `dados/entrada` (local, sensível)
- Referência em `dados/referencia_manual`
- Métricas em `resultados/metricas`
- Comparações em `resultados/comparacoes`

## Critérios de aprovação do software

- Status final sempre definido
- JSON parseável
- Testes de regras/normalizador passando

## Critérios empíricos do TCC

- Ver `checklist_validacao.md` e TCC 2 §5.8
- Não preencher métricas sem execução real
