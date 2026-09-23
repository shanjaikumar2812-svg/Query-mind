/* Thin fetch wrappers around the QueryMind Flask API. */
window.QMApi = (function () {
  async function _json(response) {
    let data;
    try {
      data = await response.json();
    } catch (err) {
      data = {};
    }
    if (!response.ok) {
      const message = data && data.error ? data.error : `Request failed (${response.status})`;
      const error = new Error(message);
      error.payload = data;
      throw error;
    }
    return data;
  }

  function uploadFile(file, onProgress) {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/upload");
      xhr.upload.onprogress = (e) => {
        if (onProgress && e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (err) { /* ignore */ }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.error || "Upload failed."));
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload."));
      xhr.send(formData);
    });
  }

  function askQuestion(datasetId, question) {
    return fetch("/query/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, question }),
    }).then(_json);
  }

  function getHistory(datasetId) {
    return fetch(`/query/history/${datasetId}`).then(_json);
  }

  function getProfile(datasetId) {
    return fetch(`/analytics/profile/${datasetId}`).then(_json);
  }

  function getForecast(datasetId, dateColumn, valueColumn, horizon) {
    return fetch("/analytics/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        date_column: dateColumn,
        value_column: valueColumn,
        horizon: horizon,
      }),
    }).then(_json);
  }

  function deleteDataset(datasetId) {
    return fetch(`/api/datasets/${datasetId}`, { method: "DELETE" }).then(_json);
  }

  return { uploadFile, askQuestion, getHistory, getProfile, getForecast, deleteDataset };
})();
