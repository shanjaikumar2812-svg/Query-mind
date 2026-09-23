/* Chart.js rendering, themed to match the Apple-style UI. */
window.QMCharts = (function () {
  const instances = {};

  function destroy(canvasId) {
    if (instances[canvasId]) {
      instances[canvasId].destroy();
      delete instances[canvasId];
    }
  }

  // Apple system-grey ramp with the signature blue as the accent.
  const palette = ["#0071e3", "#3a3a3c", "#636366", "#8e8e93", "#aeaeb2", "#c7c7cc"];
  const gridColor = "rgba(0, 0, 0, 0.06)";
  const tickColor = "#86868b";
  const fontFamily = "'Inter', -apple-system, sans-serif";
  const monoFamily = "'JetBrains Mono', 'SF Mono', Menlo, monospace";

  function isNumericValue(v) {
    if (typeof v === "number") return isFinite(v);
    if (typeof v === "string" && v.trim() !== "") return isFinite(Number(v));
    return false;
  }

  /* Pick the first column that looks reliably numeric across the sample. */
  function pickValueColumn(columns, rows) {
    const sample = rows.slice(0, Math.min(rows.length, 10));
    for (let i = 1; i < columns.length; i++) {
      const col = columns[i];
      const numericHits = sample.filter((r) => isNumericValue(r[col])).length;
      if (numericHits >= Math.max(1, Math.ceil(sample.length * 0.6))) return col;
    }
    return columns.length > 1 ? columns[1] : null;
  }

  /* True when the result set can actually be drawn as a chart. */
  function isChartable(columns, rows) {
    if (!rows || !rows.length || !columns || columns.length < 2) return false;
    const valueCol = pickValueColumn(columns, rows);
    if (!valueCol) return false;
    const values = rows.map((r) => (isNumericValue(r[valueCol]) ? Number(r[valueCol]) : 0));
    return values.some((v) => v !== 0);
  }

  const baseTooltip = {
    backgroundColor: "#1d1d1f",
    titleFont: { family: fontFamily, size: 12 },
    bodyFont: { family: monoFamily, size: 11.5 },
    padding: 10,
    cornerRadius: 8,
    displayColors: false,
  };

  /**
   * Render a result set.
   * @param {string} canvasId
   * @param {string} chartType  "bar" | "line" | "doughnut" (anything else → not drawn)
   * @param {string[]} columns
   * @param {object[]} rows
   * @returns {boolean} whether a chart was drawn
   */
  function renderResultChart(canvasId, chartType, columns, rows) {
    destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas || !isChartable(columns, rows)) return false;

    const type = ["bar", "line", "doughnut"].includes(chartType) ? chartType : "bar";

    const labelCol = columns[0];
    const valueCol = pickValueColumn(columns, rows);

    // Donuts get noisy past a dozen slices; bar/line can take more.
    const limit = type === "doughnut" ? 12 : 40;
    const slice = rows.slice(0, limit);

    const labels = slice.map((r) => String(r[labelCol]));
    const values = slice.map((r) => (isNumericValue(r[valueCol]) ? Number(r[valueCol]) : 0));

    if (type === "doughnut") {
      instances[canvasId] = new Chart(canvas.getContext("2d"), {
        type: "doughnut",
        data: {
          labels,
          datasets: [{
            label: valueCol,
            data: values,
            backgroundColor: labels.map((_, i) => palette[i % palette.length]),
            borderColor: "#ffffff",
            borderWidth: 2,
            hoverOffset: 6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: {
              position: "right",
              labels: {
                color: tickColor,
                font: { family: fontFamily, size: 11.5 },
                boxWidth: 10,
                usePointStyle: true,
                pointStyle: "circle",
              },
            },
            tooltip: baseTooltip,
          },
        },
      });
      return true;
    }

    // Highlight the largest bar in the signature blue, mute the rest.
    const maxValue = Math.max.apply(null, values);
    const barColors = values.map((v) => (v === maxValue ? palette[0] : "#c7c7cc"));

    instances[canvasId] = new Chart(canvas.getContext("2d"), {
      type,
      data: {
        labels,
        datasets: [{
          label: valueCol,
          data: values,
          backgroundColor: type === "bar" ? barColors : "rgba(0, 113, 227, 0.10)",
          hoverBackgroundColor: type === "bar" ? palette[0] : undefined,
          borderColor: palette[0],
          borderWidth: type === "bar" ? 0 : 2,
          borderRadius: type === "bar" ? 8 : 0,
          maxBarThickness: 56,
          tension: 0.35,
          pointRadius: type === "line" ? 3 : 0,
          pointBackgroundColor: palette[0],
          pointBorderColor: "#ffffff",
          pointBorderWidth: 1.5,
          fill: type === "line",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: baseTooltip,
        },
        scales: {
          x: {
            ticks: {
              color: tickColor,
              font: { family: fontFamily, size: 11 },
              maxRotation: 0,
              autoSkip: true,
              callback: function (value) {
                const label = this.getLabelForValue(value);
                return label.length > 14 ? label.slice(0, 13) + "…" : label;
              },
            },
            grid: { display: false },
            border: { color: gridColor },
          },
          y: {
            ticks: { color: tickColor, font: { family: monoFamily, size: 10.5 } },
            grid: { color: gridColor, drawTicks: false },
            border: { display: false },
            beginAtZero: true,
          },
        },
      },
    });
    return true;
  }

  function renderForecastChart(canvasId, historyDates, historyValues, forecastDates, forecastValues) {
    destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return false;

    const labels = [...historyDates, ...forecastDates];
    const historySeries = [...historyValues, ...new Array(forecastDates.length).fill(null)];
    const forecastSeries = [
      ...new Array(Math.max(historyDates.length - 1, 0)).fill(null),
      historyValues[historyValues.length - 1],
      ...forecastValues,
    ];

    instances[canvasId] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "History",
            data: historySeries,
            borderColor: palette[0],
            backgroundColor: "rgba(0, 113, 227, 0.10)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: true,
          },
          {
            label: "Forecast",
            data: forecastSeries,
            borderColor: palette[1],
            borderDash: [5, 4],
            backgroundColor: "transparent",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: tickColor,
              font: { family: fontFamily, size: 11 },
              boxWidth: 10,
              usePointStyle: true,
              pointStyle: "circle",
            },
          },
          tooltip: baseTooltip,
        },
        scales: {
          x: {
            ticks: { color: tickColor, maxRotation: 0, autoSkip: true, font: { family: monoFamily, size: 9.5 } },
            grid: { display: false },
            border: { color: gridColor },
          },
          y: {
            ticks: { color: tickColor, font: { family: monoFamily, size: 9.5 } },
            grid: { color: gridColor, drawTicks: false },
            border: { display: false },
          },
        },
      },
    });
    return true;
  }

  return { renderResultChart, renderForecastChart, isChartable, destroy };
})();
