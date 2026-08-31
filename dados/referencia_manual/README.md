# dados/referencia_manual

Gabaritos (ground truth) produzidos **manualmente**, antes da comparação automática.

- Um arquivo JSON por documento; formato em `exemplo_formato.json`.
- Campos: instituição, período, saldos e totais agregados (sem anotação linha a linha).
- Os arquivos `D01`–`D03` cobrem o piloto inicial; a base será ampliada para o corpus completo.

```powershell
python scripts\calcular_metricas.py --resultados resultados\experimentos --referencias dados\referencia_manual --saida resultados\metricas
```

Não derive referências automaticamente a partir da saída do sistema.
