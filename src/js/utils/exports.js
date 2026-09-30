export function csvCell(value) {
  let text = String(value ?? "");
  // Quoting alone does not stop spreadsheets from treating text as a formula.
  if (typeof value === "string" && /^[\s\uFEFF]*[=+@-]/u.test(text)) text = "'" + text;
  return `"${text.replaceAll('"', '""')}"`;
}

export function csvRows(rows) {
  return rows.map((row) => row.map(csvCell).join(";")).join("\r\n");
}

export function parseBackup(source) {
  const data = JSON.parse(source.replace(/^\uFEFF/, ""));
  const keys = ["products", "suppliers", "sales", "purchases", "movements"];
  if (!data || typeof data !== "object" || keys.some((key) => !Array.isArray(data[key]))) {
    throw new Error("El archivo no contiene un respaldo completo.");
  }
  return data;
}
