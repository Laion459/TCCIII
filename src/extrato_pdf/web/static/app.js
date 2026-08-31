/**
 * UI shell: toasts, tabs, drawer, tema, menu mobile.
 */
(function () {
  const STORAGE_THEME = "extrato-pdf-theme";
  const MQ_MOBILE = "(max-width: 960px)";

  function el(id) {
    return document.getElementById(id);
  }

  function isMobile() {
    return window.matchMedia(MQ_MOBILE).matches;
  }

  function temaAtual() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function toast(mensagem, tipo = "info", duracao = 4200) {
    const host = el("toast-host");
    if (!host) return;
    const node = document.createElement("div");
    node.className = `toast toast-${tipo}`;
    node.setAttribute("role", "status");
    node.textContent = mensagem;
    host.appendChild(node);
    requestAnimationFrame(() => node.classList.add("visible"));
    setTimeout(() => {
      node.classList.remove("visible");
      setTimeout(() => node.remove(), 220);
    }, duracao);
  }

  function initTabs(root = document) {
    root.querySelectorAll("[data-tabs]").forEach((container) => {
      const buttons = container.querySelectorAll("[data-tab]");
      const panels = container.querySelectorAll("[data-panel]");
      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          const alvo = btn.getAttribute("data-tab");
          buttons.forEach((b) => b.classList.toggle("ativo", b === btn));
          panels.forEach((p) => {
            p.hidden = p.getAttribute("data-panel") !== alvo;
          });
        });
      });
    });
  }

  function initDrawers(root = document) {
    root.querySelectorAll("[data-drawer-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-drawer-open");
        const drawer = el(id);
        if (drawer) {
          drawer.hidden = false;
          requestAnimationFrame(() => drawer.classList.add("open"));
        }
      });
    });
    root.querySelectorAll("[data-drawer-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const drawer = btn.closest(".drawer");
        if (drawer) {
          drawer.classList.remove("open");
          setTimeout(() => {
            drawer.hidden = true;
          }, 200);
        }
      });
    });
  }

  function atualizarBotoesTema(tema) {
    const escuro = tema === "dark";
    document.querySelectorAll(".theme-switch").forEach((btn) => {
      const icon = btn.querySelector(".theme-switch-icon");
      const label = btn.querySelector(".theme-switch-label");
      if (icon) icon.textContent = escuro ? "☀" : "☾";
      if (label) label.textContent = escuro ? "Modo claro" : "Modo escuro";
      btn.setAttribute("aria-pressed", escuro ? "true" : "false");
    });
  }

  function aplicarTema(tema) {
    const normalizado = tema === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", normalizado);
    document.body.setAttribute("data-theme", normalizado);
    try {
      localStorage.setItem(STORAGE_THEME, normalizado);
    } catch (e) {
      /* ignore */
    }
    atualizarBotoesTema(normalizado);
  }

  function alternarTema() {
    aplicarTema(temaAtual() === "dark" ? "light" : "dark");
  }

  function initTheme() {
    let salvo = null;
    try {
      salvo = localStorage.getItem(STORAGE_THEME);
    } catch (e) {
      /* ignore */
    }
    const preferido =
      salvo === "light" || salvo === "dark"
        ? salvo
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
    aplicarTema(preferido);

    document.querySelectorAll(".theme-switch").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        alternarTema();
      });
    });
  }

  function sidebarAberta() {
    const sidebar = el("sidebar");
    return Boolean(sidebar && sidebar.classList.contains("open"));
  }

  function fecharSidebar() {
    const sidebar = el("sidebar");
    const overlay = el("sidebar-overlay");
    const toggle = el("menu-toggle");
    if (sidebar) sidebar.classList.remove("open");
    if (overlay) {
      overlay.classList.remove("is-visible");
      overlay.setAttribute("aria-hidden", "true");
    }
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("nav-open");
  }

  function abrirSidebar() {
    if (!isMobile()) return;
    const sidebar = el("sidebar");
    const overlay = el("sidebar-overlay");
    const toggle = el("menu-toggle");
    if (sidebar) sidebar.classList.add("open");
    if (overlay) {
      overlay.classList.add("is-visible");
      overlay.setAttribute("aria-hidden", "false");
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("nav-open");
  }

  function initMobileNav() {
    const toggle = el("menu-toggle");
    const close = el("sidebar-close");
    const overlay = el("sidebar-overlay");

    if (toggle) {
      toggle.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (sidebarAberta()) fecharSidebar();
        else abrirSidebar();
      });
    }

    if (close) {
      close.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fecharSidebar();
      });
    }

    if (overlay) {
      overlay.addEventListener("click", (e) => {
        e.preventDefault();
        fecharSidebar();
      });
    }

    document.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (isMobile()) fecharSidebar();
      });
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && sidebarAberta()) fecharSidebar();
    });

    window.addEventListener("resize", () => {
      if (!isMobile() && sidebarAberta()) fecharSidebar();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initDrawers();
    initTheme();
    initMobileNav();
  });

  window.ExtratoUI = {
    toast,
    initTabs,
    initDrawers,
    aplicarTema,
    alternarTema,
    fecharSidebar,
    abrirSidebar,
  };
})();
