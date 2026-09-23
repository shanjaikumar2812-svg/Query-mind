window.QMCharts = (function () {
  const instances = {};

  function destroy(canvasId) {
    if (instances[canvasId]) {
      instances[canvasId].destroy();
      delete instances[canvasId];
    }
  }

  const palette = ["#2451f0", "#e2711d", "#16794f", "#7c5cff", "#0891b2", "#c0362c"];
  const gridColor = "rgba(18, 20, 28, 0.06)";
  const tickColor = "#666e80";
  const fontFamily = "'Inter', sans-serif";

  function isNumericValue(v) {
    if (typeof v === "number") return isFinite(v);
    if (typeof v === "string" && v.trim() !== "") return isFinite(Number(v));
    return false;
  }

  function pickValueColumn(columns, rows) {
    const sample = rows.slice(0, Math.min(rows.length, 10));
    for (let i = 1; i < columns.length; i++) {
      const col = columns[i];
      const numericHits = sample.filter((r) => isNumericValue(r[col])).length;
      if (numericHits >= Math.max(1, Math.ceil(sample.length * 0.6))) return col;
    }
    return columns[1];
  }

  function renderResultChart(canvasId, chartType, columns, rows) {
    destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas || !rows.length || columns.length < 2) return false;

    if (chartType !== "line" && chartType !== "bar") return false;

    const labelCol = columns[0];
    const valueCol = pickValueColumn(columns, rows);
    if (!valueCol) return false;

    const labels = rows.map((r) => String(r[labelCol]));
    const values = rows.map((r) => (isNumericValue(r[valueCol]) ? Number(r[valueCol]) : 0));

    if (!values.some((v) => v !== 0)) return false;

    const type = chartType === "line" ? "line" : "bar";

    instances[canvasId] = new Chart(canvas.getContext("2d"), {
      type,
      data: {
        labels,
        datasets: [{
          label: valueCol,
          data: values,
          backgroundColor: type === "bar" ? palette[0] : "rgba(36,81,240,.12)",
          borderColor: palette[0],
          borderWidth: 2,
          borderRadius: type === "bar" ? 5 : 0,
          maxBarThickness: 48,
          tension: 0.35,
          pointRadius: type === "line" ? 3 : 0,
          pointBackgroundColor: palette[0],
          fill: type === "line",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#12141c",
            titleFont: { family: fontFamily },
            bodyFont: { family: fontFamily },
            padding: 10,
            cornerRadius: 8,
          },
        },
        scales: {
          x: { ticks: { color: tickColor, font: { family: fontFamily, size: 11 } }, grid: { display: false } },
          y: { ticks: { color: tickColor, font: { family: fontFamily, size: 11 } }, grid: { color: gridColor }, beginAtZero: true },
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
    const forecastSeries = [...new Array(Math.max(historyDates.length - 1, 0)).fill(null), historyValues[historyValues.length - 1], ...forecastValues];

    instances[canvasId] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "History", data: historySeries, borderColor: palette[0], backgroundColor: "rgba(36,81,240,.10)", borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true },
          { label: "Forecast", data: forecastSeries, borderColor: palette[1], borderDash: [6, 4], backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.3 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { color: tickColor, font: { family: fontFamily, size: 11.5 }, boxWidth: 12, usePointStyle: true } },
          tooltip: { backgroundColor: "#12141c", padding: 10, cornerRadius: 8 },
        },
        scales: {
          x: { ticks: { color: tickColor, maxRotation: 0, autoSkip: true, font: { family: fontFamily, size: 10.5 } }, grid: { display: false } },
          y: { ticks: { color: tickColor, font: { family: fontFamily, size: 11 } }, grid: { color: gridColor } },
        },
      },
    });
    return true;
  }

  return { renderResultChart, renderForecastChart, destroy };
})();
