# Checklist de validação operacional

Preencher após implementação e durante experimentos.  
Fonte de critérios: TCC 2 §5.8 e `docs/especificacao_tecnica.md`.

## Sanidade de saída (por PDF)

- [ ] Diretório de saída criado
- [ ] `resultado.json` existe e é JSON válido
- [ ] `relatorio.txt` existe e não está vazio
- [ ] `execucao.log` existe e registra versões/parâmetros
- [ ] `status_processamento` ∈ {consistente, inconsistente, incompleto, revisao_necessaria, nao_processavel}
- [ ] Campos monetários com 2 casas / coerentes com Decimal interno

## Critérios de sucesso do TCC (avaliação empírica)

- [ ] JSON válido para todos os PDFs processáveis
- [ ] Instituição correta na maioria dos documentos
- [ ] Saldos/totais dentro da tolerância quando layout permitir leitura
- [ ] Divergências R06 detectadas quando não fecham
- [ ] Status incompleto/revisao/nao_processavel quando evidência insuficiente
- [ ] Condição C ≥ A e B nas métricas agregadas
- [ ] Meta ≥ 80% campos principais em processáveis — **pendente ampliação da referência manual**

## Não marcar como concluído sem evidência

Este checklist não substitui tabelas de métricas em `resultados/metricas/`.
