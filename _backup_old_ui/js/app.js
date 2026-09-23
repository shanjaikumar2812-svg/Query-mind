/* Page-level wiring for the upload and workspace pages. */
window.QM = (function () {
  const { $, el, escapeHtml, formatNumber, toast } = QMUtils;

  /* ---------------- Upload page ---------------- */
  function initUploadPage() {
    const dropzone = $("#dropzone");
    const fileInput = $("#file-input");
    const progressWrap = $("#upload-progress");
    const progressBar = $("#upload-progress-bar");
    const errorBox = $("#upload-error");
    if (!dropzone) return;

    dropzone.addEventListener("click", () => fileInput.click());

    ["dragover", "dragenter"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
      })
    );
    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files[0]) handleUpload(fileInput.files[0]);
    });

    function handleUpload(file) {
      errorBox.classList.add("hidden");
      progressWrap.classList.remove("hidden");
      progressBar.style.width = "0%";

      QMApi.uploadFile(file, (pct) => (progressBar.style.width = pct + "%"))
        .then((data) => {
          progressBar.style.width = "100%";
          toast("Upload complete!", "success");
          window.location.href = data.redirect;
        })
        .catch((err) => {
          progressWrap.classList.add("hidden");
          errorBox.textContent = err.message;
          errorBox.classList.remove("hidden");
        });
    }
  }

  /* ---------------- Dashboard hero search ---------------- */
  function initDashboardHero() {
    const askBtn = $("#hero-ask");
    const input = $("#hero-query");
    if (!askBtn || !input) return;

    const go = () => {
      const question = input.value.trim();
      const targetId = askBtn.getAttribute("data-latest-dataset-id");
      if (!targetId) {
        toast("Upload a CSV first, then ask away.", "error");
        return;
      }
      const url = `/workspace/${targetId}${question ? `?q=${encodeURIComponent(question)}` : ""}`;
      window.location.href = url;
    };

    askBtn.addEventListener("click", go);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
  }

  /* ---------------- Workspace page ---------------- */
  let currentDatasetId = null;
  let currentColumns = [];
  let lastHistoryId = null;

  function initWorkspacePage(datasetId) {
    currentDatasetId = datasetId;
    loadProfile();
    loadHistory();
    bindQueryForm();
    bindForecast();

    const params = new URLSearchParams(window.location.search);
    const prefill = params.get("q");
    if (prefill) {
      const input = $("#question-input");
      if (input) {
        input.value = prefill;
        $("#query-form").dispatchEvent(new Event("submit", { cancelable: true }));
      }
    }
  }

  function loadProfile() {
    QMApi.getProfile(currentDatasetId)
      .then((profile) => {
        currentColumns = profile.columns.map((c) => c.name);
        $("#stat-rows").textContent = formatNumber(profile.row_count);
        $("#stat-cols").textContent = formatNumber(profile.column_count);
        const avgMissing =
          profile.columns.reduce((sum, c) => sum + c.missing_pct, 0) / (profile.columns.length || 1);
        $("#stat-missing").textContent = avgMissing.toFixed(1) + "%";

        const list = $("#column-list");
        list.innerHTML = "";
        profile.columns.forEach((c) => {
          const row = el("div", "column-row");
          row.innerHTML = `<span>${escapeHtml(c.name)}</span><span>${escapeHtml(c.dtype)}</span>`;
          list.appendChild(row);
        });

        const dateSelect = $("#forecast-date-col");
        const valueSelect = $("#forecast-value-col");
        dateSelect.innerHTML = "";
        valueSelect.innerHTML = "";
        profile.columns.forEach((c) => {
          dateSelect.appendChild(new Option(c.name, c.name));
          if (c.dtype.includes("int") || c.dtype.includes("float")) {
            valueSelect.appendChild(new Option(c.name, c.name));
          }
        });
      })
      .catch((err) => toast(err.message, "error"));
  }

  function loadHistory() {
    QMApi.getHistory(currentDatasetId)
      .then((data) => {
        const listEl = $("#history-list");
        listEl.innerHTML = "";
        data.history.forEach((h) => {
          const item = el("li", "", h.natural_query);
          item.addEventListener("click", () => {
            $("#question-input").value = h.natural_query;
          });
          listEl.appendChild(item);
        });
      })
      .catch(() => {});
  }

  function bindQueryForm() {
    const form = $("#query-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const question = $("#question-input").value.trim();
      if (!question) return;

      const askBtn = $("#ask-btn");
      askBtn.disabled = true;
      $(".btn-label", askBtn).classList.add("hidden");
      $(".btn-spinner", askBtn).classList.remove("hidden");
      $("#query-error").classList.add("hidden");
      $("#query-result").classList.add("hidden");

      QMApi.askQuestion(currentDatasetId, question)
        .then(renderQueryResult)
        .catch((err) => {
          $("#query-error").textContent = err.message;
          $("#query-error").classList.remove("hidden");
        })
        .finally(() => {
          askBtn.disabled = false;
          $(".btn-label", askBtn).classList.remove("hidden");
          $(".btn-spinner", askBtn).classList.add("hidden");
          loadHistory();
        });
    });

    $("#toggle-sql-btn").addEventListener("click", () => {
      $("#sql-block").classList.toggle("hidden");
      const showing = !$("#sql-block").classList.contains("hidden");
      $("#toggle-sql-btn").textContent = showing ? "Hide SQL" : "Show SQL";
    });
  }

  function renderQueryResult(data) {
    lastHistoryId = data.history_id;

    $("#result-summary").textContent = data.summary || `${data.row_count} row(s) returned.`;
    $("#sql-block").textContent = data.sql || "";
    $("#query-result").classList.remove("hidden");

    const exportButtons = $("#export-buttons");
    exportButtons.classList.remove("hidden");
    $("#export-csv").href = `/export/csv/${lastHistoryId}`;
    $("#export-excel").href = `/export/excel/${lastHistoryId}`;
    $("#export-pdf").href = `/export/pdf/${lastHistoryId}`;

    const table = $("#result-table");
    table.innerHTML = "";
    if (data.columns.length) {
      const thead = el("thead");
      const headRow = el("tr");
      data.columns.forEach((c) => headRow.appendChild(el("th", "", c)));
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = el("tbody");
      data.results.slice(0, 200).forEach((row) => {
        const tr = el("tr");
        data.columns.forEach((c) => tr.appendChild(el("td", "", row[c])));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
    }

    const rendered = QMCharts.renderResultChart("result-chart", data.chart_type, data.columns, data.results);
    $("#chart-card").classList.toggle("hidden", !rendered);
  }

  function bindForecast() {
    const btn = $("#forecast-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const dateCol = $("#forecast-date-col").value;
      const valueCol = $("#forecast-value-col").value;
      if (!dateCol || !valueCol) {
        toast("Select both a date and a value column.", "error");
        return;
      }
      QMApi.getForecast(currentDatasetId, dateCol, valueCol, 12)
        .then((data) => {
          $("#forecast-chart-card").classList.remove("hidden");
          QMCharts.renderForecastChart(
            "forecast-chart",
            data.history_dates,
            data.history_values,
            data.forecast_dates,
            data.forecast_values
          );
          toast(`Forecast generated (${data.method}).`, "success");
        })
        .catch((err) => toast(err.message, "error"));
    });
  }

  return { initUploadPage, initWorkspacePage, initDashboardHero };
})();
