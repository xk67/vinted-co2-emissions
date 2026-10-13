const form = document.getElementById("calc-form");
const cityInput = document.getElementById("city");
const cityIdInput = document.getElementById("city-id");
const suggestions = document.getElementById("suggestions");
const submitButton = document.getElementById("submit");
const messageEl = document.getElementById("message");
const progressWrap = document.getElementById("progress-wrap");
const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");
const results = document.getElementById("results");
const resultsTitle = document.getElementById("results-title");

const statOrders = document.getElementById("stat-orders");
const statDistance = document.getElementById("stat-distance");
const statCo2 = document.getElementById("stat-co2");
const equivalentsEl = document.getElementById("equivalents");
const toggleAssumptions = document.getElementById("toggle-assumptions");
const ordersBody = document.getElementById("orders-body");

const POLL_INTERVAL_MS = 1000;
const SEARCH_DEBOUNCE_MS = 150;

let pollTimer = null;
let searchTimer = null;

function setMessage(text) {
  messageEl.textContent = text || "";
}

function showProgress(message, current, total) {
  progressWrap.classList.remove("hidden");
  const percent = total > 0 ? Math.round((current / total) * 100) : 0;
  progressBar.style.width = `${percent}%`;
  progressText.textContent = total > 0 ? `${message} (${percent}%)` : message;
}

function hideProgress() {
  progressWrap.classList.add("hidden");
  progressBar.style.width = "0%";
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) return "–";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/* ---- assumptions toggle ---- */

function toggleAssumptionsView() {
  const shown = equivalentsEl.classList.toggle("show-base");
  toggleAssumptions.setAttribute("aria-expanded", String(shown));
  toggleAssumptions.textContent = shown ? "Hide assumptions" : "Adjust assumptions";
}

toggleAssumptions.addEventListener("click", toggleAssumptionsView);

/* ---- city autocomplete ---- */
function closeSuggestions() {
  suggestions.classList.add("hidden");
  suggestions.replaceChildren();
  cityInput.setAttribute("aria-expanded", "false");
}

function chooseCity(entry) {
  const label = entry.state ? `${entry.name}, ${entry.state}` : entry.name;
  cityInput.value = label;
  cityIdInput.value = entry.id;
  submitButton.disabled = false;
  closeSuggestions();
  setMessage("");
}

function renderSuggestions(entries) {
  suggestions.replaceChildren();
  if (!entries.length) {
    closeSuggestions();
    return;
  }
  for (const entry of entries) {
    const item = document.createElement("li");
    item.className = "suggestion";
    item.setAttribute("role", "option");

    const name = document.createElement("span");
    name.className = "suggestion-name";
    name.textContent = entry.name;
    item.appendChild(name);

    if (entry.state) {
      const state = document.createElement("span");
      state.className = "suggestion-state";
      state.textContent = entry.state;
      item.appendChild(state);
    }

    item.addEventListener("mousedown", (event) => {
      event.preventDefault();
      chooseCity(entry);
    });
    suggestions.appendChild(item);
  }
  suggestions.classList.remove("hidden");
  cityInput.setAttribute("aria-expanded", "true");
}

async function searchCities(query) {
  if (!query) {
    closeSuggestions();
    return;
  }
  try {
    const response = await fetch(`/api/cities?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    renderSuggestions(data.cities || []);
  } catch (error) {
    closeSuggestions();
  }
}

cityInput.addEventListener("input", () => {
  cityIdInput.value = "";
  submitButton.disabled = true;
  clearTimeout(searchTimer);
  const query = cityInput.value.trim();
  searchTimer = setTimeout(() => searchCities(query), SEARCH_DEBOUNCE_MS);
});

cityInput.addEventListener("blur", () => {
  setTimeout(closeSuggestions, 150);
});

/* ---- results ---- */

function formatEquivalentValue(value) {
  if (value === null || value === undefined || !isFinite(value)) return "–";
  const digits = Math.abs(value) >= 100 ? 0 : 1;
  return formatNumber(value, digits);
}

function renderEquivalents(list, totalCo2) {
  equivalentsEl.replaceChildren();
  for (const item of list) {
    const card = document.createElement("div");
    card.className = "stat equivalent";

    const valueRow = document.createElement("span");
    valueRow.className = "stat-value-row";

    const value = document.createElement("span");
    value.className = "stat-value";
    value.textContent = formatEquivalentValue(item.value);
    valueRow.appendChild(value);

    if (item.unit) {
      const unit = document.createElement("span");
      unit.className = "stat-unit";
      unit.textContent = item.unit;
      valueRow.appendChild(unit);
    }
    card.appendChild(valueRow);

    const label = document.createElement("span");
    label.className = "stat-label";
    label.textContent = item.label;
    card.appendChild(label);

    const base = document.createElement("label");
    base.className = "equivalent-base";

    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.step = "any";
    input.value = item.factor_kg_per_unit;
    base.appendChild(input);

    const suffix = document.createElement("span");
    suffix.textContent = "kg CO₂ per unit";
    base.appendChild(suffix);

    input.addEventListener("input", () => {
      const factor = parseFloat(input.value);
      value.textContent = formatEquivalentValue(
        factor > 0 ? totalCo2 / factor : null
      );
    });

    card.appendChild(base);
    if (item.source) card.title = `Source: ${item.source}`;
    equivalentsEl.appendChild(card);
  }
}

function renderResults(payload) {
  const totals = payload.totals;
  statOrders.textContent = `${totals.routed_order_count} / ${totals.order_count}`;
  statDistance.textContent = formatNumber(totals.total_distance_km, 1);
  statCo2.textContent = formatNumber(totals.total_co2_kg, 1);
  resultsTitle.textContent = `Orders to ${payload.fixed_location.display_name}`;

  renderEquivalents(payload.equivalents || [], totals.total_co2_kg);

  ordersBody.replaceChildren();
  for (const order of payload.orders) {
    const row = document.createElement("tr");

    const title = document.createElement("td");
    title.textContent = order.title || "–";
    row.appendChild(title);

    const city = document.createElement("td");
    city.textContent = order.seller_city || "unknown";
    row.appendChild(city);

    const km = document.createElement("td");
    km.className = "num";
    km.textContent = order.route_km === null ? "no route" : formatNumber(order.route_km, 1);
    if (order.route_km === null) km.classList.add("muted");
    row.appendChild(km);

    const co2 = document.createElement("td");
    co2.className = "num";
    co2.textContent = order.co2_kg === null ? "–" : formatNumber(order.co2_kg, 1);
    if (order.co2_kg === null) co2.classList.add("muted");
    row.appendChild(co2);

    ordersBody.appendChild(row);
  }

  results.classList.remove("hidden");
}

async function pollStatus(jobId) {
  try {
    const response = await fetch(`/api/status/${jobId}`);
    const data = await response.json();

    if (data.status === "running") {
      showProgress(data.progress.message, data.progress.current, data.progress.total);
      pollTimer = setTimeout(() => pollStatus(jobId), POLL_INTERVAL_MS);
      return;
    }

    hideProgress();
    submitButton.disabled = false;

    if (data.status === "done") {
      setMessage("Done.");
      renderResults(data);
    } else {
      setMessage(`Error: ${data.error}`);
    }
  } catch (error) {
    hideProgress();
    submitButton.disabled = false;
    setMessage(`Error: ${error.message}`);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const cityId = cityIdInput.value;
  if (!cityId) {
    setMessage("Please choose a city from the list.");
    return;
  }

  clearTimeout(pollTimer);
  submitButton.disabled = true;
  results.classList.add("hidden");
  ordersBody.replaceChildren();
  setMessage("Starting…");
  showProgress("Starting…", 0, 0);

  try {
    const response = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city_id: cityId }),
    });
    const data = await response.json();

    if (!response.ok) {
      hideProgress();
      submitButton.disabled = false;
      setMessage(`Error: ${data.error || response.statusText}`);
      return;
    }

    pollStatus(data.job_id);
  } catch (error) {
    hideProgress();
    submitButton.disabled = false;
    setMessage(`Error: ${error.message}`);
  }
});
