const STORAGE_KEY = "almacen-accessibility-v1";

const controls = {
  contrast: "#high-contrast",
  largeText: "#large-text",
  reducedMotion: "#reduced-motion",
};

const classes = {
  dark: "dark-mode",
  contrast: "high-contrast",
  largeText: "large-text",
  reducedMotion: "reduced-motion",
};

let preferences = loadPreferences();
let voices = [];
let currentUtterance = null;

export function initializeAccessibility() {
  applyPreferences();
  syncControls();

  document.querySelector("#open-accessibility").addEventListener("click", openModal);
  document.querySelectorAll("[data-close-accessibility]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });
  document.querySelector("#reset-accessibility").addEventListener("click", resetPreferences);
  document.querySelector("#theme-toggle").addEventListener("click", toggleDarkMode);
  initializeReader();

  for (const [preference, selector] of Object.entries(controls)) {
    document.querySelector(selector).addEventListener("change", (event) => {
      preferences[preference] = event.target.checked;
      saveAndApply();
    });
  }
}

function openModal() {
  syncControls();
  document.querySelector("#accessibility-modal").showModal();
}

function closeModal() {
  document.querySelector("#accessibility-modal").close();
}

function loadPreferences() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved);
  } catch {
    // Se usan preferencias seguras cuando el almacenamiento no está disponible.
  }

  return {
    dark: window.matchMedia("(prefers-color-scheme: dark)").matches,
    contrast: false,
    largeText: false,
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  };
}

function saveAndApply() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  applyPreferences();
}

function applyPreferences() {
  const root = document.documentElement;
  for (const [preference, className] of Object.entries(classes)) {
    root.classList.toggle(className, Boolean(preferences[preference]));
  }
  syncThemeButton();
}

function syncControls() {
  for (const [preference, selector] of Object.entries(controls)) {
    document.querySelector(selector).checked = Boolean(preferences[preference]);
  }
}

function resetPreferences() {
  preferences = {
    dark: preferences.dark,
    contrast: false,
    largeText: false,
    reducedMotion: false,
  };
  saveAndApply();
  syncControls();
}

function toggleDarkMode() {
  preferences.dark = !preferences.dark;
  saveAndApply();
  animateThemeButton();
}

function animateThemeButton() {
  const button = document.querySelector("#theme-toggle");
  button.classList.remove("is-changing");
  void button.offsetWidth;
  button.classList.add("is-changing");
  button.addEventListener("animationend", () => button.classList.remove("is-changing"), { once: true });
}

function syncThemeButton() {
  const button = document.querySelector("#theme-toggle");
  if (!button) return;
  button.setAttribute("aria-pressed", String(Boolean(preferences.dark)));
  button.querySelector(".theme-toggle-icon").textContent = preferences.dark ? "☀️" : "🌙";
  button.querySelector("strong").textContent = preferences.dark ? "Modo claro" : "Modo oscuro";
  button.querySelector("small").textContent = preferences.dark
    ? "Cambiar a fondo claro"
    : "Vista más cómoda de noche";
}

function initializeReader() {
  const supported = "speechSynthesis" in window;
  const reader = document.querySelector(".reader-settings");

  if (!supported) {
    reader.innerHTML = '<p class="reader-unavailable">El lector de texto no está disponible en este navegador.</p>';
    return;
  }

  loadVoices();
  window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
  document.querySelector("#reader-play").addEventListener("click", readCurrentView);
  document.querySelector("#reader-pause").addEventListener("click", togglePause);
  document.querySelector("#reader-stop").addEventListener("click", stopReading);
  document.querySelector("#reader-rate").addEventListener("input", updateRateLabel);
}

function loadVoices() {
  voices = window.speechSynthesis.getVoices();
  const select = document.querySelector("#reader-voice");
  if (!select) return;

  const spanishVoices = voices.filter((voice) => voice.lang.toLowerCase().startsWith("es"));
  const available = spanishVoices.length ? spanishVoices : voices;
  select.innerHTML = available
    .map((voice) => `<option value="${voices.indexOf(voice)}">${voice.name} (${voice.lang})</option>`)
    .join("");
}

function readCurrentView() {
  const activeView = document.querySelector(".view.active");
  const text = getReadableText(activeView);
  if (!text) {
    setReaderStatus("No hay texto para leer");
    return;
  }

  stopReading();
  currentUtterance = new SpeechSynthesisUtterance(text);
  const selectedVoice = voices[Number(document.querySelector("#reader-voice").value)];
  if (selectedVoice) currentUtterance.voice = selectedVoice;
  currentUtterance.lang = selectedVoice?.lang || "es-CL";
  currentUtterance.rate = Number(document.querySelector("#reader-rate").value);
  currentUtterance.onstart = () => {
    activeView.classList.add("is-reading");
    setReaderStatus("Leyendo");
  };
  currentUtterance.onend = finishReading;
  currentUtterance.onerror = finishReading;
  window.speechSynthesis.speak(currentUtterance);
}

function getReadableText(container) {
  const copy = container.cloneNode(true);
  copy.querySelectorAll("button, input, select, .icon-button").forEach((node) => node.remove());
  return copy.innerText.replace(/\s+/g, " ").trim();
}

function togglePause() {
  if (!window.speechSynthesis.speaking) return;
  const button = document.querySelector("#reader-pause");
  if (window.speechSynthesis.paused) {
    window.speechSynthesis.resume();
    button.textContent = "Pausar";
    setReaderStatus("Leyendo");
  } else {
    window.speechSynthesis.pause();
    button.textContent = "Continuar";
    setReaderStatus("En pausa");
  }
}

function stopReading() {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  finishReading();
}

function finishReading() {
  document.querySelectorAll(".is-reading").forEach((view) => view.classList.remove("is-reading"));
  const pause = document.querySelector("#reader-pause");
  if (pause) pause.textContent = "Pausar";
  setReaderStatus("Listo");
  currentUtterance = null;
}

function updateRateLabel(event) {
  document.querySelector("#reader-rate-value").textContent = `${event.target.value}×`;
}

function setReaderStatus(message) {
  const status = document.querySelector("#reader-status");
  if (status) status.textContent = message;
}
