import { beforeEach, test, expect, vi } from "vitest";
import { api, setCsrfToken, ApiError } from "./client";
beforeEach(() => {
  vi.restoreAllMocks();
  setCsrfToken("csrf-from-django");
});
test("envía sesión, JSON y CSRF en acciones", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response('{"ok":true}', {
        headers: { "Content-Type": "application/json" },
      }),
    );
  await api("/reservas/1/acciones/", { method: "POST", body: "{}" });
  const [, options] = fetchMock.mock.calls[0];
  expect(options?.credentials).toBe("include");
  expect(new Headers(options?.headers).get("X-CSRFToken")).toBe(
    "csrf-from-django",
  );
});
test("401 notifica vencimiento y 403 conserva error legible", async () => {
  const listener = vi.fn();
  window.addEventListener("auth-expired", listener);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response('{"error":"Ingresá nuevamente"}', {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }),
  );
  await expect(api("/me/")).rejects.toBeInstanceOf(ApiError);
  expect(listener).toHaveBeenCalledOnce();
  vi.mocked(globalThis.fetch).mockResolvedValue(
    new Response('{"error":"No tenés permisos"}', {
      status: 403,
      headers: { "Content-Type": "application/json" },
    }),
  );
  await expect(api("/me/")).rejects.toMatchObject({
    status: 403,
    message: "No tenés permisos",
  });
  expect(listener).toHaveBeenCalledOnce();
  window.removeEventListener("auth-expired", listener);
});
