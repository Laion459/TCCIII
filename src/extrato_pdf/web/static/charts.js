/**
 * Gráficos SVG/CSS para métricas experimentais (sem dependências externas).
 */
(function () {
  const CORES_COND = {
    A: "var(--chart-a, #2563eb)",
    B: "var(--chart-b, #6366f1)",
    C: "var(--chart-c, #0ea5e9)",
  };

  const CORES_STATUS = {
    consistente: "var(--ok)",
    inconsistente: "var(--err)",
    incompleto: "var(--warn)",
    revisao_necessaria: "var(--info)",
    nao_processavel: "var(--muted)",
  };

  function el(id) {
    return document.getElementById(id);
  }

  function maxValor(obj) {
    return Math.max(0, ...Object.values(obj));
  }

  function renderTaxaConsistente(containerId, corpus, condicoes) {
    const node = el(containerId);
    if (!node) return;
    const valores = condicoes.map((c) => corpus[c]?.taxa_consistente ?? 0);
    const max = Math.max(100, ...valores, 1);
    node.innerHTML = condicoes
      .map((c, i) => {
        const v = valores[i];
        const h = Math.round((v / max) * 100);
        return `<div class="chart-bar-col">
          <div class="chart-bar-wrap">
            <div class="chart-bar-fill" style="height:${h}%;background:${CORES_COND[c]}" title="${v}%"></div>
          </div>
          <span class="chart-bar-val">${v}%</span>
          <span class="chart-bar-label">Cond. ${c}</span>
        </div>`;
      })
      .join("");
  }

  function renderStatusGrouped(containerId, chartStatus, condicoes) {
    const node = el(containerId);
    if (!node) return;
    if (!chartStatus.length) {
      node.innerHTML = '<p class="muted">Sem dados de status por condição.</p>';
      return;
    }
    const max = Math.max(
      1,
      ...chartStatus.flatMap((row) => condicoes.map((c) => row.valores[c] || 0))
    );
    node.innerHTML = chartStatus
      .map((row) => {
        const cor = CORES_STATUS[row.status] || "var(--muted)";
        const barras = condicoes
          .map((c) => {
            const v = row.valores[c] || 0;
            const w = Math.round((v / max) * 100);
            return `<div class="chart-hbar-row">
              <span class="chart-hbar-cond">${c}</span>
              <div class="chart-hbar-track"><div class="chart-hbar-fill" style="width:${w}%;background:${CORES_COND[c]}"></div></div>
              <span class="chart-hbar-val">${v}</span>
            </div>`;
          })
          .join("");
        return `<div class="chart-status-group">
          <div class="chart-status-title"><span class="dot" style="background:${cor}"></span>${row.status}</div>
          ${barras}
        </div>`;
      })
      .join("");
  }

  function renderAcertosGrouped(containerId, chartAcertos, condicoes) {
    const node = el(containerId);
    if (!node) return;
    const temDados = chartAcertos.some((r) => condicoes.some((c) => (r.valores[c] || 0) > 0));
    if (!temDados) {
      node.innerHTML = '<p class="muted">Nenhuma comparação com referência manual ainda.</p>';
      return;
    }
    node.innerHTML = chartAcertos
      .map((row) => {
        const barras = condicoes
          .map((c) => {
            const v = row.valores[c] || 0;
            return `<div class="chart-bar-col chart-bar-col--sm">
              <div class="chart-bar-wrap chart-bar-wrap--sm">
                <div class="chart-bar-fill" style="height:${v}%;background:${CORES_COND[c]}"></div>
              </div>
              <span class="chart-bar-val">${v}%</span>
              <span class="chart-bar-label">${c}</span>
            </div>`;
          })
          .join("");
        return `<div class="chart-metric-group">
          <div class="chart-metric-title">${row.metrica}</div>
          <div class="chart-bar-group">${barras}</div>
        </div>`;
      })
      .join("");
  }

  function classeHeatmap(status) {
    if (!status) return "heatmap-empty";
    if (status === "consistente") return "heatmap-ok";
    if (status === "inconsistente") return "heatmap-err";
    if (status in { incompleto: 1, revisao_necessaria: 1 }) return "heatmap-warn";
    return "heatmap-muted";
  }

  function renderHeatmap(containerId, heatmap, condicoes) {
    const node = el(containerId);
    if (!node) return;
    if (!heatmap.length) {
      node.innerHTML = '<p class="muted">Nenhum experimento registrado.</p>';
      return;
    }
    const head = condicoes.map((c) => `<th>${c}</th>`).join("");
    const rows = heatmap
      .map((row) => {
        const cols = condicoes
          .map((c) => {
            const st = row[c];
            const label = st || "-";
            return `<td><span class="heatmap-cell ${classeHeatmap(st)}" title="${label}">${label.slice(0, 4)}</span></td>`;
          })
          .join("");
        return `<tr><td class="heatmap-doc">${row.documento}</td>${cols}</tr>`;
      })
      .join("");
    node.innerHTML = `<table class="heatmap-table"><thead><tr><th>Documento</th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderLaboratorio(lab) {
    if (!lab) return;
    renderTaxaConsistente("chart-taxa", lab.corpus, lab.condicoes);
    renderStatusGrouped("chart-status", lab.chart_status, lab.condicoes);
    renderAcertosGrouped("chart-acertos", lab.chart_acertos, lab.condicoes);
    renderHeatmap("chart-heatmap", lab.heatmap, lab.condicoes);
  }

  window.ExtratoCharts = { renderLaboratorio, renderTaxaConsistente, renderHeatmap };
})();
