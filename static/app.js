const durationEl = document.querySelector("#duration");
const privacyEl = document.querySelector("#privacy");
const generateBtn = document.querySelector("#generate");
const shortsBtn = document.querySelector("#shorts");
const connectBtn = document.querySelector("#connect");
const declineBtn = document.querySelector("#decline");
const approveBtn = document.querySelector("#approve");
const errorEl = document.querySelector("#error");
const statusEl = document.querySelector("#status");
const cardEl = document.querySelector("#card");
const resultEl = document.querySelector("#result");
const historyEl = document.querySelector("#history");
const shortsPanel = document.querySelector("#shorts-panel");
const shortsList = document.querySelector("#shorts-list");
const healthEl = document.querySelector("#health");

let current = null;
let pollTimer = null;
let shortsTimer = null;

function setError(message) {
  errorEl.textContent = message || "";
}

function setStatus(message) {
  statusEl.textContent = message || "";
}

async function request(url, options) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : "The request failed.";
    throw new Error(typeof detail === "string" ? detail : "The request failed.");
  }
  return body;
}

function showCard(job) {
  current = job;
  if (!job || job.status !== "proposed") {
    cardEl.hidden = true;
    return;
  }
  cardEl.hidden = false;
  document.querySelector("#purpose").textContent = job.purpose;
  document.querySelector("#card-title").textContent = job.title;
  document.querySelector("#scene").textContent = job.scene_summary;
  document.querySelector("#sound").textContent = `Sound: ${job.sound_label}`;
  declineBtn.disabled = false;
  approveBtn.disabled = false;
}

function showResult(job) {
  if (!job || job.status === "proposed" || job.status === "declined") {
    resultEl.hidden = true;
    resultEl.innerHTML = "";
    return;
  }
  const lines = [];
  if (job.youtube_url) {
    lines.push(`<p><a href="${job.youtube_url}">Open the video on YouTube</a></p>`);
  }
  if (job.video_path) {
    lines.push(`<p>Video file: ${escapeHtml(job.video_path)}</p>`);
  }
  if (job.metadata_path) {
    lines.push(`<p>Title and description: ${escapeHtml(job.metadata_path)}</p>`);
  }
  if (job.note) lines.push(`<p>${escapeHtml(job.note)}</p>`);
  if (job.error) lines.push(`<p>${escapeHtml(job.error)}</p>`);
  if (job.status === "done" && job.video_path) {
    lines.push("<p>YouTube received this file. If processing was abandoned, upload the same file again.</p>");
  }
  if (job.video_path && job.status !== "uploading" && !(job.note || "").startsWith("Preview mode")) {
    lines.push(`<p><button id="retry" type="button" data-job-id="${job.id}">Upload again</button></p>`);
  }
  resultEl.dataset.jobId = job.id;
  resultEl.hidden = lines.length === 0;
  resultEl.innerHTML = lines.join("");
  const retry = document.querySelector("#retry");
  if (retry) retry.addEventListener("click", retryUpload);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function latestShortBatch(jobs) {
  const shorts = jobs.filter((job) => job.format === "short" && job.batch_id);
  if (!shorts.length) return [];
  const newest = shorts
    .slice()
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))[0];
  return shorts
    .filter((job) => job.batch_id === newest.batch_id)
    .sort((a, b) => (a.batch_index || 0) - (b.batch_index || 0));
}

function renderShorts(jobs) {
  shortsPanel.hidden = jobs.length === 0;
  shortsList.innerHTML = "";
  jobs.forEach((job, index) => {
    const item = document.createElement("li");
    const link = job.youtube_url ? ` · <a href="${job.youtube_url}">YouTube</a>` : "";
    const problem = job.error ? ` · ${escapeHtml(job.error)}` : "";
    item.innerHTML = `${escapeHtml(job.title)} · ${escapeHtml(job.step || job.status)}${link}${problem}`;
    item.dataset.index = String(index + 1);
    shortsList.appendChild(item);
  });
}

function watchShorts(ids) {
  if (shortsTimer) clearInterval(shortsTimer);
  const tick = async () => {
    try {
      const jobs = [];
      for (const id of ids) jobs.push(await request(`/api/jobs/${id}`));
      jobs.sort((a, b) => (a.batch_index || 0) - (b.batch_index || 0));
      renderShorts(jobs);
      const busy = jobs.some((job) => ["queued", "rendering", "uploading"].includes(job.status));
      const finished = jobs.filter((job) => ["done", "ready", "failed"].includes(job.status)).length;
      setStatus(busy ? `Shorts ${finished} of ${jobs.length} finished…` : "");
      if (!busy) {
        clearInterval(shortsTimer);
        shortsTimer = null;
        shortsBtn.disabled = false;
      }
    } catch (error) {
      setError(error.message);
    }
  };
  shortsBtn.disabled = true;
  tick();
  shortsTimer = setInterval(tick, 1500);
}

async function createShorts() {
  setError("");
  shortsBtn.disabled = true;
  setStatus("Asking for 10 calm and focus Shorts…");
  try {
    const body = await request("/api/shorts", {
      method: "POST",
      body: JSON.stringify({ privacy: privacyEl.value }),
    });
    renderShorts(body.jobs);
    setStatus("Shorts 0 of 10 finished…");
    watchShorts(body.jobs.map((job) => job.id));
    await refreshHistory();
  } catch (error) {
    setError(error.message);
    setStatus("");
    shortsBtn.disabled = false;
  }
}

function renderHistory(jobs) {
  historyEl.innerHTML = "";
  for (const job of jobs) {
    const item = document.createElement("li");
    const link = job.youtube_url ? ` · <a href="${job.youtube_url}">YouTube</a>` : "";
    const again = job.video_path && job.status !== "uploading" && !(job.note || "").startsWith("Preview mode")
      ? ` <button type="button" class="text-button" data-job-id="${job.id}">Upload again</button>`
      : "";
    item.innerHTML = `${escapeHtml(job.title)} · ${escapeHtml(job.status)}${link}${again}`;
    const button = item.querySelector("button");
    if (button) button.addEventListener("click", retryUpload);
    historyEl.appendChild(item);
  }
}

async function refreshHealth() {
  const health = await request("/api/health");
  const pills = [
    ["Gemini key", health.gemini_key_present],
    ["Preview", health.preview],
    ["ffmpeg", health.ffmpeg],
    ["YouTube client", health.youtube_client_secret],
    ["YouTube connected", health.youtube_connected],
  ];
  healthEl.innerHTML = pills
    .map(([label, on]) => `<span class="pill${on ? " ok" : ""}">${label}: ${on ? "yes" : "no"}</span>`)
    .join("");
  if (health.connect_error) setError(health.connect_error);
  return health;
}

async function refreshHistory() {
  renderHistory(await request("/api/jobs"));
}

function watch(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const job = await request(`/api/jobs/${jobId}`);
      const busy = job.status === "rendering" || job.status === "uploading";
      setStatus(busy ? `Working on ${job.step || job.status}…` : "");
      showResult(job);
      if (!busy) {
        clearInterval(pollTimer);
        pollTimer = null;
        approveBtn.disabled = false;
        declineBtn.disabled = false;
        await refreshHistory();
      }
    } catch (error) {
      setError(error.message);
    }
  }, 1500);
}

async function generate() {
  setError("");
  generateBtn.disabled = true;
  setStatus("Asking for an idea…");
  try {
    const job = await request("/api/ideas", { method: "POST" });
    showCard(job);
    showResult(null);
    setStatus("");
    await refreshHistory();
  } catch (error) {
    setError(error.message);
    setStatus("");
  } finally {
    generateBtn.disabled = false;
  }
}

async function decline() {
  if (!current) return;
  setError("");
  declineBtn.disabled = true;
  approveBtn.disabled = true;
  setStatus("Asking for a different idea…");
  try {
    const job = await request(`/api/jobs/${current.id}/decline`, { method: "POST" });
    showCard(job);
    setStatus("");
    await refreshHistory();
  } catch (error) {
    setError(error.message);
    setStatus("");
    declineBtn.disabled = false;
    approveBtn.disabled = false;
  }
}

async function approve() {
  if (!current) return;
  setError("");
  approveBtn.disabled = true;
  declineBtn.disabled = true;
  setStatus("Starting the video…");
  try {
    const job = await request(`/api/jobs/${current.id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        duration_hours: Number(durationEl.value),
        privacy: privacyEl.value,
      }),
    });
    cardEl.hidden = true;
    showResult(job);
    watch(job.id);
  } catch (error) {
    setError(error.message);
    setStatus("");
    approveBtn.disabled = false;
    declineBtn.disabled = false;
  }
}

async function retryUpload(event) {
  const jobId = event?.currentTarget?.dataset?.jobId || resultEl.dataset.jobId;
  if (!jobId) return;
  setError("");
  try {
    const job = await request(`/api/jobs/${jobId}/upload`, { method: "POST" });
    showResult(job);
    watch(job.id);
  } catch (error) {
    setError(error.message);
  }
}

async function connect() {
  setError("");
  connectBtn.disabled = true;
  setStatus("Opening Google sign-in…");
  try {
    await request("/api/youtube/connect", { method: "POST" });
    const timer = setInterval(async () => {
      const health = await refreshHealth();
      if (health.youtube_connected) {
        clearInterval(timer);
        setStatus("YouTube is connected.");
        connectBtn.disabled = false;
      } else if (!health.connect_running) {
        clearInterval(timer);
        setStatus("");
        connectBtn.disabled = false;
      }
    }, 1500);
  } catch (error) {
    setError(error.message);
    setStatus("");
    connectBtn.disabled = false;
  }
}

generateBtn.addEventListener("click", generate);
shortsBtn.addEventListener("click", createShorts);
declineBtn.addEventListener("click", decline);
approveBtn.addEventListener("click", approve);
connectBtn.addEventListener("click", connect);

refreshHealth().catch((error) => setError(error.message));
request("/api/jobs?limit=40")
  .then((jobs) => {
    renderHistory(jobs);
    const finished = jobs.find((job) => job.video_path && job.status !== "proposed" && job.status !== "declined");
    if (finished) showResult(finished);
    const batch = latestShortBatch(jobs);
    if (batch.length) {
      renderShorts(batch);
      const busy = batch.some((job) => ["queued", "rendering", "uploading"].includes(job.status));
      if (busy) watchShorts(batch.map((job) => job.id));
    }
  })
  .catch((error) => setError(error.message));
request("/api/jobs/current")
  .then((job) => showCard(job))
  .catch((error) => setError(error.message));
