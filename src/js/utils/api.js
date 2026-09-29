export async function apiRequest(url, options = {}) {
  let response;
  try {
    response = await fetch(url, { cache: "no-store", ...options });
  } catch {
    throw new Error("No se pudo conectar. Comprueba que el servidor esté iniciado.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error || `No se pudo completar la operación (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  if (!data) throw new Error("El servidor no devolvió una respuesta válida.");
  return data;
}
