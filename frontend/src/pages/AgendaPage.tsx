import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, ApiError } from "../api/client";
import { useMe } from "../hooks/useMe";
import type {
  Action,
  AgendaData,
  BulkPreview,
  Reservation,
} from "../types/api";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  LoadingSkeleton,
  PageHeader,
  Select,
  StatCard,
} from "../components/ui/primitives";
import { ReservationCard } from "../features/agenda/ReservationCard";
import { labels } from "../utils/format";
const filtersSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Seleccioná una fecha."),
  branch: z.string().regex(/^\d*$/),
});
type Filters = z.infer<typeof filtersSchema>;
export function AgendaPage() {
  const { data: me } = useMe();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const date = params.get("date") || me?.today || "";
  const branch = params.get("branch") || "";
  const form = useForm<Filters>({
    resolver: zodResolver(filtersSchema),
    values: { date, branch },
  });
  const query = useQuery({
    queryKey: ["agenda", date, branch],
    queryFn: () =>
      api<AgendaData>(`/agenda/?${new URLSearchParams({ date, branch })}`),
    enabled: Boolean(me),
  });
  const [feedback, setFeedback] = useState("");
  const [selected, setSelected] = useState<{
    reservation: Reservation;
    action: Action;
  } | null>(null);
  const [preview, setPreview] = useState<BulkPreview | null>(null);
  const refresh = async (data: { message: string }) => {
    setFeedback(data.message);
    setSelected(null);
    setPreview(null);
    await client.invalidateQueries({ queryKey: ["agenda"] });
    await client.invalidateQueries({ queryKey: ["statistics"] });
  };
  const action = useMutation({
    mutationFn: ({
      reservation,
      action,
    }: {
      reservation: Reservation;
      action: Action;
    }) =>
      api<{ message: string }>(`/reservas/${reservation.id}/acciones/`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }),
    onSuccess: refresh,
  });
  const bulkPreview = useMutation({
    mutationFn: () =>
      api<BulkPreview>("/agenda/marcado-masivo/preview/", {
        method: "POST",
        body: JSON.stringify({ date, branch }),
      }),
    onSuccess: (data) => {
      if (data.count) setPreview(data);
      else
        setFeedback(
          "No hay reservas finalizadas pendientes de marcar como atendidas.",
        );
    },
  });
  const bulk = useMutation({
    mutationFn: (token: string) =>
      api<{ message: string }>("/agenda/marcado-masivo/ejecutar/", {
        method: "POST",
        body: JSON.stringify({ token }),
      }),
    onSuccess: refresh,
  });
  return (
    <>
      <PageHeader
        title="Agenda"
        subtitle={
          /^\d{4}-\d{2}-\d{2}$/.test(date) &&
          !Number.isNaN(Date.parse(`${date}T12:00:00-03:00`))
            ? new Intl.DateTimeFormat("es-UY", {
                weekday: "long",
                day: "numeric",
                month: "long",
                timeZone: "America/Montevideo",
              }).format(new Date(`${date}T12:00:00-03:00`))
            : undefined
        }
        description="Los turnos del día, en un solo lugar."
      />
      <form
        className="filter-bar"
        onSubmit={form.handleSubmit((values) => {
          setFeedback("");
          setParams(values);
        })}
      >
        <label>
          Fecha
          <Input type="date" {...form.register("date")} />
          {form.formState.errors.date && (
            <span className="error-text">
              {form.formState.errors.date.message}
            </span>
          )}
        </label>
        <label>
          Sucursal
          <Select {...form.register("branch")}>
            <option value="">Todas las autorizadas</option>
            {(query.data?.branches || me?.branches || []).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
                {me && me.salons.length > 1 ? ` · ${b.salon}` : ""}
              </option>
            ))}
          </Select>
        </label>
        <Button type="submit">Ver agenda</Button>
      </form>
      {feedback && (
        <p role="status" className="feedback">
          {feedback}
        </p>
      )}
      {bulkPreview.error && (
        <p className="error-text" role="alert">
          {bulkPreview.error.message}
        </p>
      )}
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
              ["Total de turnos", query.data.summary.total],
              ["Atendidas", query.data.summary.attended],
              ["Ausentes", query.data.summary.absent],
              ["Confirmadas", query.data.summary.confirmed],
            ].map(([label, value]) => (
              <StatCard key={label} label={String(label)} value={value} />
            ))}
          </div>
          <div className="section-heading agenda-list-toolbar">
            <h2>
              {query.data.reservations.length} reserva
              {query.data.reservations.length === 1 ? "" : "s"}
            </h2>
            {query.data.can_bulk_complete && (
              <Button
                variant="secondary"
                disabled={bulkPreview.isPending}
                onClick={() => {
                  bulk.reset();
                  bulkPreview.reset();
                  void bulkPreview.mutate();
                }}
              >
                {bulkPreview.isPending
                  ? "Consultando…"
                  : "Marcar atendidas las finalizadas"}
              </Button>
            )}
          </div>
          {query.data.reservations.length ? (
            <div className="reservation-list">
              {query.data.reservations.map((r) => (
                <ReservationCard
                  key={r.id}
                  reservation={r}
                  onAction={(reservation, selectedAction) => {
                    action.reset();
                    setSelected({ reservation, action: selectedAction });
                  }}
                />
              ))}
            </div>
          ) : (
            <EmptyState />
          )}
        </>
      )}
      <ConfirmDialog
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected ? labels[selected.action] : "Actualizar reserva"}
        description={
          selected
            ? `${selected.reservation.client} · ${selected.reservation.start_time}. ¿Deseás continuar?`
            : ""
        }
        onConfirm={() => {
          if (selected) action.mutate(selected);
        }}
        pending={action.isPending}
        error={action.error?.message}
      />
      <ConfirmDialog
        open={Boolean(preview)}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
        title="Marcar atendidas las finalizadas"
        description={`Se marcarán ${preview?.count || 0} reservas como atendidas. ¿Deseás continuar?`}
        onConfirm={() => {
          if (preview) bulk.mutate(preview.token);
        }}
        pending={bulk.isPending}
        error={bulk.error?.message}
      />
    </>
  );
}
