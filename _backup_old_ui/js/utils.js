/* DOM helpers, formatting, and toast notifications shared across pages. */
window.QMUtils = (function () {
  function $(selector, root) {
    return (root || document).querySelector(selector);
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

  function toast(message, type) {
    const root = $("#qm-toast-root");
    if (!root) return;
    const node = el("div", `qm-toast ${type || ""}`, message);
    root.appendChild(node);
    setTimeout(() => node.remove(), 4000);
  }

  function debounce(fn, wait) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  return { $, el, escapeHtml, formatNumber, toast, debounce };
})();
