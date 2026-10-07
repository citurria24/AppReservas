import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi, beforeEach, expect, test } from "vitest";
import { AgendaPage } from "./AgendaPage";
import { StatisticsPage } from "./StatisticsPage";
import { Sidebar } from "../layouts/AppLayout";
import { api, ApiError } from "../api/client";
import type { AgendaData, Me, StatisticsData } from "../types/api";
vi.mock("../api/client", () => ({
  api: vi.fn(),
  setCsrfToken: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
    }
  },
}));
const owner: Me = {
  id: 1,
  username: "owner",
  display_name: "Carlos",
  role: "owner",
  salon: { id: 1, name: "Estilo Norte", slug: "norte", role: "owner" },
  salons: [{ id: 1, name: "Estilo Norte", slug: "norte", role: "owner" }],
  branches: [{ id: 1, name: "Centro", salon: "norte" }],
  permissions: { bulk_complete: true, statistics: true },
  csrf_token: "token",
  login_url: "/cuenta/ingresar/",
  logout_url: "/cuenta/salir/",
  today: "2026-10-05",
};
const agenda: AgendaData = {
  date: "2026-10-05",
  branches: owner.branches,
  can_bulk_complete: true,
  summary: { total: 1, attended: 0, absent: 0, confirmed: 1 },
  reservations: [
    {
      id: 1,
      date: "2026-10-05",
      starts_at: "2026-10-05T09:00:00-03:00",
      ends_at: "2026-10-05T09:30:00-03:00",
      start_time: "09:00",
      end_time: "09:30",
      salon: { name: "Estilo Norte", slug: "norte" },
      branch: owner.branches[0],
      professional: { id: 1, name: "Diego" },
      service: { id: 1, name: "Corte" },
      client: "Carlos Iturria",
      phone: "098 123 456",
      email: "carlos@example.test",
      notes: "Primera visita",
      status: "confirmed",
      status_label: "Confirmada",
      allowed_actions: [
        "mark_attended",
        "mark_absent",
        "reschedule",
        "cancel_local",
      ],
      reschedule_url: "/agenda/reservas/1/reprogramar/",
    },
  ],
};
const statistics: StatisticsData = {
  salon: { name: "Estilo Norte", slug: "norte" },
  month: 10,
  year: 2026,
  branch: null,
  branches: owner.branches,
  summary: {
    total: 4,
    attended: 2,
    absent: 1,
    cancelled_client: 1,
    cancelled_salon: 0,
    attendance_rate: 2 / 3,
    cancellation_rate: 0.25,
    unique_clients: 3,
    discounts: 1,
  },
  by_branch: [],
  by_professional: [],
  by_service: [],
  distribution: [
    { status: "completed", label: "Atendidas", count: 2 },
    { status: "no_show", label: "Ausentes", count: 1 },
    { status: "cancelled_client", label: "Canceladas por cliente", count: 1 },
  ],
  export_url: "/peluquerias/norte/estadisticas/excel/",
};
let client: QueryClient;
beforeEach(() => {
  vi.resetAllMocks();
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["me"], owner);
});
function renderPage(page: "agenda" | "statistics") {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[page === "agenda" ? "/agenda" : "/estadisticas/norte"]}
      >
        <Routes>
          <Route path="/agenda" element={<AgendaPage />} />
          <Route path="/estadisticas/:slug" element={<StatisticsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function mockAgenda(data = agenda) {
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/me/" ? owner : (data as never),
  );
}

test("agenda muestra loading mientras espera datos", () => {
  vi.mocked(api).mockImplementation(() => new Promise(() => {}));
  renderPage("agenda");
  expect(
    screen.getByRole("status", { name: "Cargando datos" }),
  ).toBeInTheDocument();
});
test("agenda vacía", async () => {
  mockAgenda({ ...agenda, reservations: [] });
  renderPage("agenda");
  expect(
    await screen.findByText("No hay reservas para los filtros seleccionados."),
  ).toBeInTheDocument();
});
test("reserva muestra información y badge", async () => {
  mockAgenda();
  renderPage("agenda");
  expect(await screen.findByText("Carlos Iturria")).toBeInTheDocument();
  expect(screen.getByText("Confirmada")).toBeInTheDocument();
  expect(screen.getByText("Diego")).toBeInTheDocument();
  expect(screen.getByText("Primera visita")).toBeInTheDocument();
  expect(screen.getByText("carlos@example.test")).toBeInTheDocument();
});
test("acciones secundarias y reprogramación usan el enlace Django", async () => {
  mockAgenda();
  renderPage("agenda");
  await screen.findByText("Carlos Iturria");
  await userEvent.click(
    screen.getByRole("button", { name: "Acciones de Carlos Iturria" }),
  );
  expect(
    await screen.findByRole("menuitem", { name: "Marcar ausente" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Reprogramar" })).toHaveAttribute(
    "href",
    "/agenda/reservas/1/reprogramar/",
  );
});
test("marcar atendida requiere confirmación y refresca la agenda", async () => {
  mockAgenda();
  vi.mocked(api).mockImplementation(async (path) =>
    path.includes("/acciones/")
      ? ({ message: "Reserva actualizada." } as never)
      : (agenda as never),
  );
  renderPage("agenda");
  await userEvent.click(
    await screen.findByRole("button", { name: "Marcar atendida" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  expect(await screen.findByText("Reserva actualizada.")).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith(
    "/reservas/1/acciones/",
    expect.objectContaining({
      method: "POST",
      body: '{"action":"mark_attended"}',
    }),
  );
});
test("no muestra acciones en una reserva final sin allowed_actions", async () => {
  mockAgenda({
    ...agenda,
    can_bulk_complete: false,
    reservations: [
      {
        ...agenda.reservations[0],
        status: "completed",
        status_label: "Atendida",
        allowed_actions: [],
      },
    ],
  });
  renderPage("agenda");
  await screen.findByText("Atendida");
  expect(
    screen.queryByRole("button", { name: "Marcar atendida" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Acciones de Carlos Iturria"),
  ).not.toBeInTheDocument();
});
test("marcado masivo solo visible con permiso del backend", async () => {
  mockAgenda({ ...agenda, can_bulk_complete: false });
  renderPage("agenda");
  await screen.findByText("Carlos Iturria");
  expect(
    screen.queryByText("Marcar atendidas las finalizadas"),
  ).not.toBeInTheDocument();
});
test("marcado masivo solicita preview y utiliza el token en confirmación", async () => {
  mockAgenda();
  vi.mocked(api).mockImplementation(async (path) =>
    path.includes("/preview/")
      ? ({
          count: 1,
          token: "signed",
          date: "2026-10-05",
          branch: null,
        } as never)
      : path.includes("/ejecutar/")
        ? ({ message: "Se marcaron 1 reservas como atendidas." } as never)
        : (agenda as never),
  );
  renderPage("agenda");
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Marcar atendidas las finalizadas",
    }),
  );
  expect(
    await screen.findByText(
      "Se marcarán 1 reservas como atendidas. ¿Deseás continuar?",
    ),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/agenda/marcado-masivo/ejecutar/",
      expect.objectContaining({ body: '{"token":"signed"}' }),
    ),
  );
});
test("sidebar muestra Estadísticas solo al Owner", () => {
  const admin = {
    ...owner,
    salons: [{ ...owner.salons[0], role: "admin" as const }],
  };
  const { unmount } = render(
    <MemoryRouter>
      <Sidebar me={admin} />
    </MemoryRouter>,
  );
  expect(screen.queryByText("Estadísticas")).not.toBeInTheDocument();
  unmount();
  render(
    <MemoryRouter>
      <Sidebar me={owner} />
    </MemoryRouter>,
  );
  expect(screen.getByText("Estadísticas")).toBeInTheDocument();
});
test("estadísticas muestra métricas, donut, leyenda y Excel filtrado", async () => {
  vi.mocked(api).mockResolvedValue(statistics);
  renderPage("statistics");
  expect(
    await screen.findByText("Distribución de reservas"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("list", { name: "Distribución de reservas" }),
  ).toBeInTheDocument();
  expect(screen.getByText("2 · 50%")).toBeInTheDocument();
  expect(screen.getByText("66,7%")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Descargar Excel" })).toHaveAttribute(
    "href",
    "/peluquerias/norte/estadisticas/excel/?year=2026&month=10&branch=",
  );
});
test("estadísticas muestra loading", () => {
  vi.mocked(api).mockImplementation(() => new Promise(() => {}));
  renderPage("statistics");
  expect(
    screen.getByRole("status", { name: "Cargando datos" }),
  ).toBeInTheDocument();
});
test("estadísticas muestra error y reintento", async () => {
  vi.mocked(api).mockRejectedValue(new ApiError(500, "Error"));
  renderPage("statistics");
  expect(
    await screen.findByText("No pudimos cargar los datos. Intentá nuevamente."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Intentar nuevamente" }),
  ).toBeInTheDocument();
});
test("estadísticas deniega URL manipulada a Admin", () => {
  client.setQueryData(["me"], {
    ...owner,
    salons: [{ ...owner.salons[0], role: "admin" }],
  });
  renderPage("statistics");
  expect(
    screen.getByText("No tenés permisos para acceder a esta sección."),
  ).toBeInTheDocument();
});
