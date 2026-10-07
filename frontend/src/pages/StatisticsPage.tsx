import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Download } from "lucide-react";
import { api, ApiError } from "../api/client";
import { useMe } from "../hooks/useMe";
import type { StatisticsData } from "../types/api";
import {
  Button,
  ErrorState,
  Input,
  LoadingSkeleton,
  PageHeader,
  Select,
  StatCard,
} from "../components/ui/primitives";
import { DistributionChart } from "../features/statistics/DistributionChart";
import { Breakdown } from "../features/statistics/Breakdown";
import { percent } from "../utils/format";
const schema = z.object({
  month: z
    .string()
    .refine((v) => Number(v) >= 1 && Number(v) <= 12, "Seleccioná un mes."),
  year: z
    .string()
    .regex(/^\d{4}$/, "Ingresá un año válido.")
    .refine(
      (v) => Number(v) >= 1900 && Number(v) <= 9998,
      "Año fuera de rango.",
    ),
  branch: z.string().regex(/^\d*$/),
});
const months = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];
export function StatisticsPage() {
  const { slug = "" } = useParams();
  const { data: me } = useMe();
  const [params, setParams] = useSearchParams();
  const year = params.get("year") || me?.today.slice(0, 4) || "";
  const month = params.get("month") || String(Number(me?.today.slice(5, 7)));
  const branch = params.get("branch") || "";
  const isOwner = me?.salons.some((s) => s.slug === slug && s.role === "owner");
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: { year, month, branch },
  });
  const filters = new URLSearchParams({ year, month, branch });
  const query = useQuery({
    queryKey: ["statistics", slug, year, month, branch],
    queryFn: () =>
      api<StatisticsData>(
        `/peluquerias/${encodeURIComponent(slug)}/estadisticas/?${filters}`,
      ),
    enabled: Boolean(isOwner),
  });
  if (!isOwner) return <ErrorState forbidden />;
  return (
    <>
      <PageHeader
        title="Estadísticas"
        description="Una mirada a la actividad de tu peluquería."
      />
      <form
        className="filter-bar"
        onSubmit={form.handleSubmit((values) => setParams(values))}
      >
        <label>
          Mes
          <Select {...form.register("month")}>
            {months.map((m, i) => (
              <option key={m} value={i + 1}>
                {m}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Año
          <Input
            type="number"
            min="1900"
            max="9998"
            {...form.register("year")}
          />
          {form.formState.errors.year && (
            <span className="error-text">
              {form.formState.errors.year.message}
            </span>
          )}
        </label>
        <label>
          Sucursal
          <Select {...form.register("branch")}>
            <option value="">Todas las sucursales</option>
            {(
              query.data?.branches ||
              me?.branches.filter((b) => b.salon === slug) ||
              []
            ).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </label>
        <Button>Consultar</Button>
      </form>
      {query.isPending ? (
        <LoadingSkeleton />
      ) : query.isError ? (
        <ErrorState
          forbidden={
            query.error instanceof ApiError && query.error.status === 403
          }
          retry={() => void query.refetch()}
        />
      ) : (
        <>
          <div className="stat-grid">
            {[
              ["Reservas", query.data.summary.total],
              ["Atendidas", query.data.summary.attended],
              ["Ausentes", query.data.summary.absent],
              ["Asistencia", percent(query.data.summary.attendance_rate)],
            ].map(([label, value]) => (
              <StatCard key={label} label={String(label)} value={value} />
            ))}
          </div>
          <div className="secondary-summary">
            <div className="secondary-metrics">
              {[
                ["Canceladas por cliente", query.data.summary.cancelled_client],
                ["Canceladas por local", query.data.summary.cancelled_salon],
                ["Cancelación", percent(query.data.summary.cancellation_rate)],
                ["Clientes únicos", query.data.summary.unique_clients],
                ["Con descuento / recompensa", query.data.summary.discounts],
              ].map(([label, value]) => (
                <div key={label}>
                  <span className="muted">{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <p className="metric-note muted">
              Asistencia: atendidas / (atendidas + ausentes). Cancelación: ambas
              cancelaciones / total. Los beneficios cuentan reservas con
              descuento aplicado, cualquiera sea su estado.
            </p>
          </div>
          <div className="export-action">
            <a
              className="button button-secondary"
              href={`${query.data.export_url}?${filters}`}
            >
              <Download size={17} />
              Descargar Excel
            </a>
          </div>
          <DistributionChart
            distribution={query.data.distribution}
            total={query.data.summary.total}
          />
          <Breakdown
            title="Reservas por sucursal"
            rows={query.data.by_branch}
          />
          <Breakdown
            title="Reservas por profesional"
            rows={query.data.by_professional}
          />
          <Breakdown
            title="Reservas por servicio"
            rows={query.data.by_service}
          />
        </>
      )}
    </>
  );
}
