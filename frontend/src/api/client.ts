export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
let csrfToken = "";
export function setCsrfToken(token: string) {
  csrfToken = token;
}
const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(options.method || "GET")) {
    const cookie = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    headers.set(
      "X-CSRFToken",
      csrfToken || (cookie ? decodeURIComponent(cookie) : ""),
    );
  }
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  const data = response.headers
    .get("content-type")
    ?.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("auth-expired"));
    throw new ApiError(
      response.status,
      data?.error || "No pudimos completar la solicitud. Intentá nuevamente.",
    );
  }
  if (data === null)
    throw new ApiError(502, "La respuesta del servidor no es válida.");
  return data as T;
}
