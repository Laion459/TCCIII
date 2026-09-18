# dados/referencia_manual

Gabaritos (ground truth) para comparação automática com as saídas do pipeline.

## Nomenclatura

Padrão único: `D{NN}_contas_{MMAAAA}.json`

| ID | Documento | Nota |
|----|-----------|------|
| D01–D03 | `contas 012025` … `032025` | Piloto original |
| D04–D10 | `contas 012023` … `072023` | Ordem cronológica |
| D11–D12 | `contas 082023`, `092023` | Caixa (anexo imagem; SI/SF manuais) |
| D13–D15 | `contas 102023` … `122023` | |
| D16–D19 | `contas 012024` … `042024` | |
| D20 | `contas 052025` | Extrato de **maio/2024** (nome do arquivo diverge) |
| D21–D27 | `contas 062024` … `122024` | |

Mapa canônico: `_validacao_independente/mapa_ids.json` e `config/default.json` → `mapa_ids_documento`.

## Formato

Um JSON por documento (ver `exemplo_formato.json`), com:
- instituição, período, saldo inicial, entradas, saídas, saldo final
- `paginas_extrato` (índices 0-based do PyMuPDF)
- observações metodológicas

## Status atual

| Situação | Quantidade |
|----------|------------|
| Referências com equação fechada (tol. R$ 0,01) | **27** (D01–D27) |
| Pendentes | **0** |

### Observações importantes

1. **`contas 052025.pdf` (D20)** contém o extrato de **maio/2024**, não maio/2025.
2. **`contas 112023.pdf` (D14)** e **`contas 122023.pdf` (D15)** apontam ambos para período **dez/2023**, com valores idênticos e extrato curto.
3. **`contas 082023.pdf` (D11)** e **`contas 092023.pdf` (D12)**: anexo Caixa em imagem (págs. 27–30); SI/SF conferidos visualmente; E/S alinhados ao consolidado Embracon com equação fechada.
4. Critério de aceite: `saldo_inicial + entradas − saídas = saldo_final` (± R$ 0,01).

## Regenerar / recalcular

```powershell
python dados\referencia_manual\_validacao_independente\validar_27.py
python scripts\calcular_metricas.py --resultados resultados\experimentos --referencias dados\referencia_manual --saida resultados\metricas
```

Não derive gabarito a partir de `resultados/experimentos` sem conferência da equação no texto do extrato.
