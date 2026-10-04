# Scripts auxiliares

| Script | Função |
|--------|--------|
| `gerar_pdfs_rasterizados.py` | Gera PDFs só com imagem a 100, 200 e 300 DPI, com o mesmo nome |
| `run_experimentos.py` | Processa lote de PDFs nas condições A, B e/ou C |
| `calcular_metricas.py` | Compara saídas com referência manual |
| `validar_saidas.py` | Verifica sanidade de JSON, TXT e log |
| `iniciar_web.ps1` | Inicia a interface web no Windows |

## Exemplos

```powershell
python scripts\gerar_pdfs_rasterizados.py
python scripts\run_experimentos.py --corpus pdf-nativo --condicoes A,C
python scripts\calcular_metricas.py --resultados resultados\experimentos --referencias dados\referencia_manual --saida resultados\metricas
python scripts\validar_saidas.py --pasta resultados\experimentos\condicao_a
```
