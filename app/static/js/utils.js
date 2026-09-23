/* DOM helpers, formatting, toasts, and modal wiring shared across pages. */
window.QMUtils = (function () {
  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function $$(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value === null || value === undefined ? "" : String(value);
    return div.innerHTML;
  }

  function formatNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return "—";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let size = Number(bytes);
    let i = 0;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i += 1;
    }
    return (i === 0 ? size : size.toFixed(1)) + " " + units[i];
  }

  function show(node) { if (node) node.classList.remove("hidden"); }
  function hide(node) { if (node) node.classList.add("hidden"); }

  function toast(message, type) {
    const root = $("#qm-toast-root");
    if (!root) return;
    const node = el("div", `qm-toast ${type || ""}`, message);
    root.appendChild(node);
    setTimeout(() => node.remove(), 4000);
  }

  function copyText(text, okMessage) {
    const done = () => toast(okMessage || "Copied to clipboard.", "success");
    const fail = () => toast("Could not copy to clipboard.", "error");

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(fail);
      return;
    }
    // Fallback for plain-http localhost, where the async clipboard API is blocked.
    try {
      const area = el("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      done();
    } catch (err) {
      fail();
    }
  }

  /* ---------------- Modals (vanilla replacement for Bootstrap) ---------------- */
  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("hidden");
  }

  function closeModal(modal) {
    if (modal) modal.classList.add("hidden");
  }

  function initModals() {
    document.addEventListener("click", (e) => {
      const opener = e.target.closest("[data-qm-modal-open]");
      if (opener) {
        e.preventDefault();
        openModal(opener.getAttribute("data-qm-modal-open"));
        return;
      }

      const closer = e.target.closest("[data-qm-modal-close]");
      if (closer) {
        e.preventDefault();
        closeModal(closer.closest(".qm-modal-backdrop"));
        return;
      }

      if (e.target.classList && e.target.classList.contains("qm-modal-backdrop")) {
        closeModal(e.target);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $$(".qm-modal-backdrop").forEach((m) => closeModal(m));
      }
    });
  }

  function debounce(fn, wait) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    initModals();
    const year = $("#qm-year");
    if (year) year.textContent = new Date().getFullYear();
  });

  return {
    $, $$, el, escapeHtml, formatNumber, formatBytes,
    show, hide, toast, copyText, openModal, closeModal, debounce,
  };
})();
