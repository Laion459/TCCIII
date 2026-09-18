/**
 * Acompanhamento de jobs (SSE) - lote e processamento unitário.
 */
(function () {
  const ETAPAS = [
    ["validacao", "Validação"],
    ["texto_nativo", "Texto nativo"],
    ["classificacao", "Classificação"],
    ["ocr", "OCR"],
    ["localizacao", "Localização"],
    ["parser", "Parser"],
    ["regras", "Regras"],
    ["serializacao", "Saída"],
  ];

  function fmtSegundos(s) {
    if (s == null || Number.isNaN(s)) return "-";
    const n = Math.max(0, Math.round(s));
    const m = Math.floor(n / 60);
    const r = n % 60;
    return m > 0 ? `${m}m ${r}s` : `${r}s`;
  }

  function badgeClass(status) {
    if (status === "consistente" || status === "ok" || status === "concluido") return "ok";
    if (status === "cancelado") return "warn";
    if (status === "erro" || status === "falha" || status === "inconsistente") return "err";
    if (status === "processando" || status === "executando") return "info";
    return "warn";
  }

  function el(id) {
    return document.getElementById(id);
  }

  function indiceEtapa(etapa) {
    if (!etapa) return -1;
    return ETAPAS.findIndex(([id]) => id === etapa);
  }

  function renderStepper(job, stepperId) {
    const nav = el(stepperId);
    if (!nav) return;
    nav.hidden = false;
    const ol = nav.querySelector(".pipeline-steps");
    if (!ol) return;

    const atual = indiceEtapa(job.etapa);
    const emOcr = job.etapa === "ocr" && job.sub_progresso;

    ol.innerHTML = ETAPAS.map(([id, rotulo], idx) => {
      let estado = "pendente";
      if (job.status === "concluido" || idx < atual) estado = "concluida";
      else if (idx === atual) estado = "ativa";
      if (id === "ocr" && !job.etapa && job.status === "concluido") {
        /* OCR pode ser pulado */
      }
      if (id === "ocr" && emOcr) estado = "ativa";
      if (job.status === "concluido") estado = "concluida";
      if (job.status === "erro" && idx === atual) estado = "erro";

      const icone =
        estado === "concluida" ? "✓" : estado === "erro" ? "!" : estado === "ativa" ? "●" : "○";
      return `<li class="pipeline-step pipeline-step--${estado}" data-etapa="${id}">
        <span class="pipeline-step-icon" aria-hidden="true">${icone}</span>
        <span class="pipeline-step-label">${rotulo}</span>
      </li>`;
    }).join("");

    nav.setAttribute(
      "aria-valuetext",
      atual >= 0 ? ETAPAS[atual][1] : job.status === "concluido" ? "Concluído" : "Aguardando"
    );
  }

  function renderProgresso(job, opts) {
    const painel = el(opts.painelId);
    if (!painel) return;
    painel.hidden = false;

    if (opts.stepperId) renderStepper(job, opts.stepperId);

    const pct = job.percentual ?? 0;
    const bar = el(opts.barId);
    const barLabel = el(opts.barLabelId);
    if (bar) {
      bar.style.width = `${pct}%`;
      bar.parentElement?.setAttribute("aria-valuenow", String(Math.round(pct)));
    }
    if (barLabel) {
      const sub = job.sub_progresso;
      if (sub && sub.total > 0) {
        barLabel.textContent = `${job.concluidos}/${job.total} PDFs (${pct}%) · OCR ${sub.concluidas}/${sub.total}`;
      } else {
        barLabel.textContent = `${job.concluidos}/${job.total} (${pct}%)`;
      }
    }

    const subBar = el(opts.subBarId);
    const subLabel = el(opts.subBarLabelId);
    const subPainel = el(opts.subPainelId);
    if (subPainel) {
      const ativo = job.sub_progresso && job.sub_progresso.total > 0;
      subPainel.hidden = !ativo;
      if (ativo && subBar) {
        const subPct = job.percentual_sub ?? 0;
        subBar.style.width = `${subPct}%`;
      }
      if (ativo && subLabel) {
        const sp = job.sub_progresso;
        subLabel.textContent =
          `OCR: ${sp.concluidas}/${sp.total} páginas (${sp.workers} workers) - ${job.percentual_sub ?? 0}%`;
      }
    }

    const msg = el(opts.mensagemId);
    if (msg) msg.textContent = job.mensagem || "";

    const atual = el(opts.atualId);
    if (atual) {
      if (job.arquivo_atual && job.sub_progresso && job.sub_progresso.total > 0) {
        const sp = job.sub_progresso;
        atual.textContent =
          `${job.arquivo_atual} - OCR ${sp.concluidas}/${sp.total} páginas (${sp.workers} workers)`;
      } else if (job.arquivo_atual) {
        atual.textContent = job.mensagem || `Arquivo atual: ${job.arquivo_atual}`;
      } else if (job.status === "concluido") {
        atual.textContent = "Finalizado";
      } else {
        atual.textContent = "";
      }
    }

    const tempo = el(opts.tempoId);
    if (tempo) {
      tempo.textContent = `Decorrido: ${fmtSegundos(job.duracao_s)} · ETA: ${fmtSegundos(job.eta_s)}`;
    }

    const contagem = el(opts.contagemId);
    if (contagem && job.contagem) {
      contagem.innerHTML = Object.entries(job.contagem)
        .map(([k, v]) => `<span class="badge ${badgeClass(k)}">${k}: ${v}</span>`)
        .join(" ");
    }

    const tbody = el(opts.tabelaBodyId);
    if (tbody && job.itens) {
      tbody.innerHTML = job.itens
        .map((item) => {
          const st = item.resultado_status || item.status;
          const link = item.caminho_relativo
            ? `<a href="/resultados/ver?path=${encodeURIComponent(item.caminho_relativo)}">abrir</a>`
            : "";
          const icon =
            item.status === "processando"
              ? '<span class="spinner" aria-hidden="true"></span>'
              : "";
          return `<tr class="row-${item.status}">
            <td>${icon} ${item.arquivo}</td>
            <td><span class="badge ${badgeClass(st)}">${st}</span></td>
            <td>${item.instituicao || item.erro || item.mensagem || "-"}</td>
            <td>${item.duracao_s ? item.duracao_s + "s" : "-"}</td>
            <td>${link}</td>
          </tr>`;
        })
        .join("");
    }

    const logs = el(opts.logsId);
    if (logs && job.logs) {
      logs.textContent = job.logs.join("\n");
      logs.scrollTop = logs.scrollHeight;
    }

    const live = el(opts.liveRegionId);
    if (live) {
      live.textContent = job.mensagem || "";
    }

    const btnCancel = el(opts.cancelBtnId);
    if (btnCancel) {
      const ativo = job.status === "executando";
      btnCancel.disabled = !ativo;
      btnCancel.hidden = !ativo;
    }

    const btnForm = el(opts.submitBtnId);
    if (btnForm) btnForm.disabled = job.status === "executando";
  }

  function acompanharJob(jobId, opts) {
    const painel = el(opts.painelId);
    if (painel) painel.hidden = false;

    const source = new EventSource(`/api/jobs/${jobId}/stream`);

    source.onmessage = (ev) => {
      let job;
      try {
        job = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (job.erro) {
        source.close();
        return;
      }
      renderProgresso(job, opts);
      if (["concluido", "erro", "cancelado"].includes(job.status)) {
        source.close();
        if (window.ExtratoUI) {
          if (job.status === "concluido") {
            window.ExtratoUI.toast(job.mensagem || "Processamento concluído", "ok");
          } else if (job.status === "cancelado") {
            window.ExtratoUI.toast("Processamento cancelado", "warn");
          } else if (job.status === "erro") {
            window.ExtratoUI.toast(job.mensagem || "Erro no processamento", "err");
          }
        }
        if (opts.onComplete) opts.onComplete(job);
      }
    };

    source.onerror = () => {
      source.close();
      fetch(`/api/jobs/${jobId}`)
        .then((r) => r.json())
        .then((job) => {
          renderProgresso(job, opts);
          if (opts.onComplete) opts.onComplete(job);
        })
        .catch(() => {});
    };

    return source;
  }

  async function iniciarLote(form, opts) {
    const fd = new FormData(form);
    const condicao = fd.get("condicao") || "A";
    const pdfs = fd.getAll("pdfs");
    const resp = await fetch("/api/lote/iniciar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ condicao, pdfs }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || "Falha ao iniciar lote");
    }
    const { job_id } = await resp.json();
    return acompanharJob(job_id, opts);
  }

  async function iniciarUnitario(pdf, condicao, opts) {
    const resp = await fetch("/api/processar/iniciar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf, condicao }),
    });
    if (!resp.ok) throw new Error("Falha ao iniciar processamento");
    const { job_id } = await resp.json();
    return acompanharJob(job_id, opts);
  }

  window.ExtratoProgress = {
    iniciarLote,
    iniciarUnitario,
    acompanharJob,
    renderProgresso,
    fmtSegundos,
    ETAPAS,
  };
})();
