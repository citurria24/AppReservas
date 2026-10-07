export const percent = (ratio: number) =>
  new Intl.NumberFormat("es-UY", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(ratio);
export const localDate = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Montevideo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export const labels = {
  mark_attended: "Marcar atendida",
  mark_absent: "Marcar ausente",
  cancel_local: "Cancelar desde el local",
  reschedule: "Reprogramar",
};
export const stateColors = {
  confirmed: "#687887",
  completed: "#65704E",
  no_show: "#916B3B",
  cancelled_client: "#965D54",
  cancelled_salon: "#80564D",
};
