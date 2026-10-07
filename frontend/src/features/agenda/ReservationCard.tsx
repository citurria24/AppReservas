import { Phone, Mail } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  DropdownMenu,
} from "../../components/ui/primitives";
import type { Action, Reservation } from "../../types/api";
import { labels } from "../../utils/format";
export function ReservationCard({
  reservation: r,
  onAction,
}: {
  reservation: Reservation;
  onAction: (r: Reservation, action: Action) => void;
}) {
  const secondary = r.allowed_actions
    .filter((action) => action !== "mark_attended")
    .map((action) => ({
      label: labels[action],
      href: action === "reschedule" ? r.reschedule_url || undefined : undefined,
      onSelect: action !== "reschedule" ? () => onAction(r, action) : undefined,
      danger: action === "cancel_local",
    }));
  return (
    <Card className="reservation-card">
      <div className="reservation-time">
        <strong>{r.start_time}</strong>
        <span>{r.end_time}</span>
      </div>
      <div className="reservation-detail">
        <div className="reservation-heading">
          <div>
            <h2>{r.client}</h2>
            <p>{r.service.name}</p>
          </div>
        </div>
        <p className="reservation-meta">
          <span>{r.professional.name}</span>
          <span aria-hidden>·</span>
          <span>{r.branch.name}</span>
          <span className="reservation-salon">· {r.salon.name}</span>
        </p>
        <div className="reservation-contact">
          <span>
            <Phone size={15} />
            {r.phone}
          </span>
          <span>
            <Mail size={15} />
            {r.email}
          </span>
        </div>
        {r.notes && <p className="reservation-notes">{r.notes}</p>}
      </div>
      <div className="reservation-status">
        <Badge status={r.status}>{r.status_label}</Badge>
      </div>
      {r.allowed_actions.length > 0 && (
        <div className="reservation-actions">
          {r.allowed_actions.includes("mark_attended") && (
            <Button
              variant="secondary"
              onClick={() => onAction(r, "mark_attended")}
            >
              Marcar atendida
            </Button>
          )}
          {secondary.length > 0 && (
            <DropdownMenu
              actions={secondary}
              label={`Acciones de ${r.client}`}
            />
          )}
        </div>
      )}
    </Card>
  );
}
