import { apiRequest as request } from "./utils/api.js";

let currentUser = null;

export async function initializeAuth() {
  const status = await request("/api/auth/status");
  if (status.authenticated) {
    currentUser = status.user;
    hideAuth();
    return currentUser;
  }
  return waitForAuthentication(status.needsSetup);
}

export function getCurrentUser() { return currentUser; }

export async function logout() {
  await request("/api/auth/logout", { method: "POST" });
  location.reload();
}

export async function changePassword(currentPassword, newPassword) {
  return request("/api/auth/password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ currentPassword, newPassword }) });
}

function waitForAuthentication(needsSetup) {
  const screen = document.querySelector("#auth-screen");
  screen.classList.toggle("setup", needsSetup);
  document.querySelector("#auth-title").textContent = needsSetup ? "Configura tu cuenta" : "Iniciar sesión";
  document.querySelector("#auth-message").textContent = needsSetup ? "Crea el primer administrador del sistema." : "Ingresa para continuar.";
  document.querySelector("#auth-submit").textContent = needsSetup ? "Crear administrador" : "Entrar";
  document.querySelector("#auth-name").required = needsSetup;

  return new Promise((resolve) => {
    document.querySelector("#auth-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.querySelector("#auth-submit");
      if (button.disabled) return;
      button.disabled = true;
      const error = document.querySelector("#auth-error");
      error.textContent = "";
      try {
        const data = await request(needsSetup ? "/api/auth/setup" : "/api/auth/login", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: document.querySelector("#auth-name").value.trim(), username: document.querySelector("#auth-username").value.trim(), password: document.querySelector("#auth-password").value }),
        });
        currentUser = data.user;
        document.querySelector("#auth-password").value = "";
        hideAuth();
        resolve(currentUser);
      } catch (failure) { error.textContent = failure.message; }
      finally { button.disabled = false; }
    }, { once: false });
  });
}

function hideAuth() { document.querySelector("#auth-screen").classList.add("hidden"); }

