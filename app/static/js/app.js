/* Page-level wiring for the upload, dashboard, and workspace pages. */
window.QM = (function () {
  const { $, $$, el, formatNumber, formatBytes, show, hide, toast, copyText } = QMUtils;

  /* ==========================================================
     Upload / landing page
     ========================================================== */
  function initUploadPage() {
    const dropzone = $("#dropzone");
    const fileInput = $("#file-input");
    if (!dropzone || !fileInput) return;

    const idle = $("#dropzone-idle");
    const busy = $("#dropzone-busy");
    const done = $("#dropzone-done");
    const busyTitle = $("#dropzone-busy-title");
    const busySub = $("#dropzone-busy-sub");
    const progressBar = $("#upload-progress-bar");
    const errorBox = $("#upload-error");

    let inFlight = false;

    function setBusy(title, sub) {
      hide(idle);
      hide(done);
      hide(errorBox);
      busy.classList.remove("hidden");
      busy.classList.add("flex");
      busyTitle.textContent = title;
      busySub.textContent = sub;
      progressBar.style.width = "0%";
    }

    function setDone(message) {
      hide(busy);
      busy.classList.remove("flex");
      done.classList.remove("hidden");
      done.classList.add("flex");
      if (message) $("#dropzone-done").querySelector("p").textContent = message;
    }

    function setIdle(errorMessage) {
      hide(busy);
      busy.classList.remove("flex");
      hide(done);
      done.classList.remove("flex");
      show(idle);
      if (errorMessage) {
        errorBox.textContent = errorMessage;
        show(errorBox);
      }
      inFlight = false;
    }

    dropzone.addEventListener("click", () => {
      if (!inFlight) fileInput.click();
    });

    ["dragover", "dragenter"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove("dragover");
      })
    );

    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer && e.dataTransfer.files[0];
      if (file) handleUpload(file);
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files[0]) handleUpload(fileInput.files[0]);
    });

    function handleUpload(file) {
      if (inFlight) return;
      inFlight = true;
      setBusy("Ingesting dataset…", `${file.name} · ${formatBytes(file.size)}`);

      QMApi.uploadFile(file, (pct) => { progressBar.style.width = pct + "%"; })
        .then((data) => {
          progressBar.style.width = "100%";
          setDone("Opening your query workspace…");
          toast("Upload complete.", "success");
          window.location.href = data.redirect;
        })
        .catch((err) => {
          setIdle(err.message);
          toast(err.message, "error");
        });
    }

    // Curated sandbox chips
    $$("#sample-chips [data-sample-key]").forEach((chip) => {
      chip.addEventListener("click", () => {
        if (inFlight) return;
        inFlight = true;
        const label = chip.getAttribute("data-sample-label");
        setBusy(`Loading ${label}…`, "Mounting sample dataset");
        progressBar.style.width = "65%";

        QMApi.loadSample(chip.getAttribute("data-sample-key"))
          .then((data) => {
            progressBar.style.width = "100%";
            setDone("Opening your query workspace…");
            toast(`${label} loaded.`, "success");
            window.location.href = data.redirect;
          })
          .catch((err) => {
            setIdle(err.message);
            toast(err.message, "error");
          });
      });
    });
  }

  /* ==========================================================
     Dashboard page
     ========================================================== */
  function initDashboardPage() {
    const askBtn = $("#hero-ask");
    const input = $("#hero-query");

    if (askBtn && input) {
      const go = () => {
        const question = input.value.trim();
        const targetId = askBtn.getAttribute("data-latest-dataset-id");
        if (!targetId) {
          toast("Upload a CSV first, then ask away.", "error");
          return;
        }
        window.location.href = `/workspace/${targetId}${question ? `?q=${encodeURIComponent(question)}` : ""}`;
      };

      askBtn.addEventListener("click", go);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") go();
      });
    }

    $$("[data-delete-dataset]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const id = btn.getAttribute("data-delete-dataset");
        if (!window.confirm("Remove this dataset? This cannot be undone.")) return;

        QMApi.deleteDataset(id)
          .then(() => {
            const card = document.querySelector(`[data-dataset-card="${id}"]`);
            if (card) card.remove();
            toast("Dataset removed.", "success");
          })
          .catch((err) => toast(err.message, "error"));
      });
    });
  }

  /* ==========================================================
     Workspace page
     ========================================================== */
  let currentDatasetId = null;
  let lastHistoryId = null;
  let lastResult = null;       // cached so chart-type toggles don't re-query
  let activeChartType = "bar";

  function initWorkspacePage(datasetId) {
    currentDatasetId = datasetId;

    loadProfile();
    loadHistory();
    bindQueryForm();
    bindTabs();
    bindChartToggle();
    bindCopyButtons();
    bindForecast();
    bindShare();

    // ?q=... arrives from the dashboard hero bar — run it immediately.
    const prefill = new URLSearchParams(window.location.search).get("q");
    if (prefill) {
      const input = $("#question-input");
      if (input) {
        input.value = prefill;
        $("#query-form").dispatchEvent(new Event("submit", { cancelable: true }));
      }
    }
  }

  /* ---------------- Profile: health, schema, forecast controls ---------------- */
  function loadProfile() {
    QMApi.getProfile(currentDatasetId)
      .then((profile) => {
        renderHealth(profile);
        renderSchema(profile);
        renderForecastControls(profile);
        renderSuggestions(profile);
      })
      .catch((err) => toast(err.message, "error"));
  }

  function renderHealth(profile) {
    const columns = profile.columns || [];
    const avgMissing = columns.length
      ? columns.reduce((sum, c) => sum + (c.missing_pct || 0), 0) / columns.length
      : 0;

    $("#stat-rows").textContent = formatNumber(profile.row_count);
    $("#stat-cols").textContent = formatNumber(profile.column_count);
    $("#stat-missing").textContent = avgMissing.toFixed(1) + "%";
    $("#stat-duplicates").textContent = formatNumber(profile.duplicate_count || 0);

    const ribbonMissing = $("#ribbon-missing");
    if (ribbonMissing) ribbonMissing.textContent = avgMissing.toFixed(1) + "%";

    // Quality score is supplied by the backend; fall back to a missing-value proxy.
    const quality = profile.quality_score !== undefined
      ? profile.quality_score
      : Math.max(0, 100 - avgMissing);

    $("#quality-bar").style.width = `${quality}%`;
    $("#quality-label").textContent = `${Math.round(quality)}%`;

    const badge = $("#health-badge");
    badge.textContent = `${Math.round(quality)}% Healthy`;
    badge.className = quality >= 90
      ? "text-[10px] font-medium font-mono text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded-full"
      : quality >= 70
        ? "text-[10px] font-medium font-mono text-amber-600 bg-amber-500/10 px-2 py-0.5 rounded-full"
        : "text-[10px] font-medium font-mono text-red-600 bg-red-500/10 px-2 py-0.5 rounded-full";
  }

  /* Map pandas dtypes onto friendly badges. */
  function dtypeBadge(dtype) {
    const d = String(dtype).toLowerCase();
    if (d.includes("int")) return { label: "INT", cls: "text-apple-tint bg-blue-50" };
    if (d.includes("float")) return { label: "FLOAT", cls: "text-purple-700 bg-purple-50" };
    if (d.includes("datetime") || d.includes("date")) return { label: "DATE", cls: "text-amber-700 bg-amber-50" };
    if (d.includes("bool")) return { label: "BOOL", cls: "text-emerald-700 bg-emerald-50" };
    return { label: "TEXT", cls: "text-apple-subtle bg-black/[0.04]" };
  }

  function renderSchema(profile) {
    const columns = profile.columns || [];
    $("#schema-count").textContent = `${columns.length} field${columns.length === 1 ? "" : "s"}`;

    const list = $("#column-list");
    list.innerHTML = "";

    columns.forEach((c) => {
      const badge = dtypeBadge(c.dtype);
      const row = el("div", "py-2 flex items-center justify-between gap-2 text-xs hover:bg-[#f5f5f7]/60 px-1 rounded-lg transition-colors");

      const name = el("span", "font-mono text-apple-ink text-[12px] font-medium truncate", c.name);
      name.title = `${c.name} · ${c.dtype} · ${c.missing_pct}% missing · ${c.unique_count} unique`;

      const tag = el("span", `px-1.5 py-0.5 text-[9px] font-mono font-medium rounded shrink-0 ${badge.cls}`, badge.label);

      row.appendChild(name);
      row.appendChild(tag);

      // Clicking a column drops its name into the question box.
      row.style.cursor = "pointer";
      row.addEventListener("click", () => {
        const input = $("#question-input");
        input.value = (input.value ? input.value.trim() + " " : "") + c.name;
        input.focus();
      });

      list.appendChild(row);
    });
  }

  function renderForecastControls(profile) {
    const columns = profile.columns || [];
    const dateCols = columns.filter((c) => {
      const d = String(c.dtype).toLowerCase();
      return d.includes("datetime") || d.includes("date") || /date|month|year|time|period/i.test(c.name);
    });
    const numericCols = columns.filter((c) => {
      const d = String(c.dtype).toLowerCase();
      return d.includes("int") || d.includes("float");
    });

    const controls = $("#forecast-controls");
    const empty = $("#forecast-empty");

    if (!dateCols.length || !numericCols.length) {
      hide(controls);
      show(empty);
      return;
    }

    hide(empty);
    show(controls);

    const dateSelect = $("#forecast-date-col");
    const valueSelect = $("#forecast-value-col");
    dateSelect.innerHTML = "";
    valueSelect.innerHTML = "";
    dateCols.forEach((c) => dateSelect.appendChild(new Option(c.name, c.name)));
    numericCols.forEach((c) => valueSelect.appendChild(new Option(c.name, c.name)));
  }

  /* Build suggested questions from the dataset's own columns. */
  function renderSuggestions(profile) {
    const wrap = $("#suggested-pills");
    if (!wrap) return;

    const columns = profile.columns || [];
    const numeric = columns.filter((c) => /int|float/i.test(c.dtype));
    const categorical = columns.filter((c) => !/int|float|datetime/i.test(c.dtype) && c.unique_count > 1 && c.unique_count <= 60);

    const ideas = [];
    if (categorical.length && numeric.length) {
      ideas.push(`Top 5 ${categorical[0].name} by ${numeric[0].name}`);
      ideas.push(`Average ${numeric[0].name} by ${categorical[0].name}`);
    }
    if (numeric.length >= 2) {
      ideas.push(`Compare ${numeric[0].name} and ${numeric[1].name}`);
    } else if (numeric.length === 1) {
      ideas.push(`What is the highest ${numeric[0].name}?`);
    }
    if (!ideas.length) ideas.push("Show me the first 10 rows");

    wrap.innerHTML = "";
    ideas.slice(0, 3).forEach((text) => {
      const pill = el(
        "button",
        "px-3 py-1 rounded-full bg-white border border-black/[0.08] hover:border-black/[0.2] hover:bg-[#f9f9fb] text-apple-ink transition-all shadow-[0_1px_2px_rgba(0,0,0,0.02)]",
        text
      );
      pill.type = "button";
      pill.addEventListener("click", () => {
        $("#question-input").value = text;
        $("#query-form").dispatchEvent(new Event("submit", { cancelable: true }));
      });
      wrap.appendChild(pill);
    });
  }

  /* ---------------- History ---------------- */
  function loadHistory() {
    QMApi.getHistory(currentDatasetId)
      .then((data) => {
        const listEl = $("#history-list");
        listEl.innerHTML = "";

        if (!data.history.length) {
          listEl.appendChild(el("li", "py-6 text-center text-[12px] text-apple-muted", "No questions yet."));
          return;
        }

        data.history.forEach((h) => {
          const item = el("li", "py-2 px-1 text-[12px] text-apple-subtle hover:text-apple-ink hover:bg-[#f5f5f7]/60 rounded-lg cursor-pointer transition-colors flex items-start gap-2");
          const icon = el("i", "bi bi-arrow-return-right text-[10px] text-apple-muted mt-0.5 shrink-0");
          const text = el("span", "truncate", h.natural_query);
          text.title = h.natural_query;
          item.appendChild(icon);
          item.appendChild(text);
          item.addEventListener("click", () => {
            $("#question-input").value = h.natural_query;
            $("#question-input").focus();
          });
          listEl.appendChild(item);
        });
      })
      .catch(() => { /* history is non-critical */ });
  }

  /* ---------------- Query submission ---------------- */
  function bindQueryForm() {
    const form = $("#query-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const question = $("#question-input").value.trim();
      if (!question) return;

      const askBtn = $("#ask-btn");
      const label = $(".btn-label", askBtn);
      const spinner = $(".btn-spinner", askBtn);

      askBtn.disabled = true;
      hide(label);
      show(spinner);
      hide($("#query-error"));

      QMApi.askQuestion(currentDatasetId, question)
        .then(renderQueryResult)
        .catch((err) => {
          const box = $("#query-error");
          box.textContent = err.message;
          show(box);
          hide($("#query-result"));
        })
        .finally(() => {
          askBtn.disabled = false;
          show(label);
          hide(spinner);
          loadHistory();
        });
    });
  }

  function renderQueryResult(data) {
    lastHistoryId = data.history_id;
    lastResult = data;

    show($("#query-result"));

    // --- AI Insight ---
    $("#result-summary").textContent = data.summary || `${formatNumber(data.row_count)} row(s) returned.`;
    $("#result-meta").textContent = `${formatNumber(data.row_count)} rows · ${data.intent || "query"}${data.retries ? ` · ${data.retries} retry` : ""}`;

    // --- SQL ---
    $("#sql-block").textContent = data.sql || "";
    $("#table-meta").textContent = `${formatNumber(data.row_count)} row(s) · showing up to 200`;

    // --- Exports ---
    $("#export-csv").href = `/export/csv/${lastHistoryId}`;
    $("#export-excel").href = `/export/excel/${lastHistoryId}`;
    $("#export-pdf").href = `/export/pdf/${lastHistoryId}`;
    const headerCsv = $("#header-export-csv");
    if (headerCsv) headerCsv.href = `/export/csv/${lastHistoryId}`;

    // --- Data table ---
    renderTable(data.columns, data.results);

    // --- Chart ---
    activeChartType = ["bar", "line", "doughnut"].includes(data.chart_type) ? data.chart_type : "bar";
    syncChartToggle();
    drawChart();

    switchTab("insight");
  }

  function renderTable(columns, rows) {
    const table = $("#result-table");
    table.innerHTML = "";
    if (!columns || !columns.length) return;

    const thead = el("thead");
    const headRow = el("tr");
    columns.forEach((c) => headRow.appendChild(el("th", "", c)));
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = el("tbody");
    rows.slice(0, 200).forEach((row) => {
      const tr = el("tr");
      columns.forEach((c) => {
        const value = row[c];
        const td = el("td", "", value === null || value === undefined ? "—" : String(value));
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }

  function drawChart() {
    if (!lastResult) return;

    const drawn = QMCharts.renderResultChart(
      "result-chart",
      activeChartType,
      lastResult.columns,
      lastResult.results
    );

    const chartCard = $("#chart-card");
    const chartEmpty = $("#chart-empty");

    if (drawn) {
      show(chartCard);
      hide(chartEmpty);
      const valueLabel = lastResult.columns.length > 1 ? lastResult.columns[1] : "";
      $("#chart-title").textContent = valueLabel
        ? `${lastResult.columns[0]} by ${valueLabel}`
        : "Result visualization";
      $("#chart-subtitle").textContent = `${formatNumber(lastResult.row_count)} row(s) in this result set`;
    } else {
      hide(chartCard);
      show(chartEmpty);
    }
  }

  function syncChartToggle() {
    $$("#chart-type-toggle .qm-chart-btn").forEach((btn) => {
      const isActive = btn.getAttribute("data-chart") === activeChartType;
      btn.className = isActive
        ? "qm-chart-btn px-2.5 py-1 rounded-md bg-white text-apple-ink shadow-sm font-semibold"
        : "qm-chart-btn px-2.5 py-1 rounded-md hover:text-apple-ink transition-colors";
    });
  }

  function bindChartToggle() {
    $$("#chart-type-toggle .qm-chart-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeChartType = btn.getAttribute("data-chart");
        syncChartToggle();
        drawChart();
      });
    });
  }

  /* ---------------- Tabs ---------------- */
  function switchTab(name) {
    $$(".qm-tab").forEach((btn) => {
      const isActive = btn.getAttribute("data-tab") === name;
      btn.className = isActive
        ? "qm-tab px-3 py-1 rounded-md bg-white text-apple-ink shadow-sm font-semibold"
        : "qm-tab px-3 py-1 rounded-md text-apple-subtle hover:text-apple-ink transition-colors";
    });
    $$(".qm-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.getAttribute("data-panel") !== name);
    });
  }

  function bindTabs() {
    $$(".qm-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
    });
  }

  /* ---------------- Copy buttons ---------------- */
  function bindCopyButtons() {
    const copySql = $("#copy-sql-btn");
    if (copySql) {
      copySql.addEventListener("click", () => {
        copyText($("#sql-block").textContent || "", "SQL copied.");
      });
    }

    const copyResult = $("#copy-result-btn");
    if (copyResult) {
      copyResult.addEventListener("click", () => {
        if (!lastResult) return;
        // Tab-separated so it pastes cleanly into a spreadsheet.
        const header = lastResult.columns.join("\t");
        const body = lastResult.results
          .slice(0, 200)
          .map((row) => lastResult.columns.map((c) => row[c]).join("\t"))
          .join("\n");
        copyText(`${header}\n${body}`, "Result copied.");
      });
    }
  }

  function bindShare() {
    const btn = $("#share-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      copyText(window.location.href, "Workspace link copied.");
    });
  }

  /* ---------------- Forecasting ---------------- */
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

      const label = $(".btn-label", btn);
      const spinner = $(".qm-spinner", btn);
      btn.disabled = true;
      hide(label);
      show(spinner);

      QMApi.getForecast(currentDatasetId, dateCol, valueCol, 12)
        .then((data) => {
          show($("#forecast-chart-card"));
          QMCharts.renderForecastChart(
            "forecast-chart",
            data.history_dates,
            data.history_values,
            data.forecast_dates,
            data.forecast_values
          );
          $("#forecast-method").textContent = `method: ${data.method}`;
          toast(`Forecast generated (${data.method}).`, "success");
        })
        .catch((err) => toast(err.message, "error"))
        .finally(() => {
          btn.disabled = false;
          show(label);
          hide(spinner);
        });
    });
  }

  return { initUploadPage, initDashboardPage, initWorkspacePage };
})();
