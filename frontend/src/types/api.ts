export type Status =
  | "confirmed"
  | "completed"
  | "no_show"
  | "cancelled_client"
  | "cancelled_salon";
export type Action =
  "mark_attended" | "mark_absent" | "cancel_local" | "reschedule";
export interface Branch {
  id: number;
  name: string;
  salon: string;
}
export interface Salon {
  id: number;
  name: string;
  slug: string;
  role: "owner" | "admin" | "hairdresser";
}
export interface Me {
  id: number;
  username: string;
  display_name: string;
  role: Salon["role"] | null;
  salon: Salon | null;
  salons: Salon[];
  branches: Branch[];
  permissions: { bulk_complete: boolean; statistics: boolean };
  csrf_token: string;
  login_url: string;
  logout_url: string;
  today: string;
}
export interface Reservation {
  id: number;
  date: string;
  starts_at: string;
  ends_at: string;
  start_time: string;
  end_time: string;
  salon: { name: string; slug: string };
  branch: Branch;
  professional: { id: number; name: string };
  service: { id: number; name: string };
  client: string;
  email: string;
  phone: string;
  notes: string;
  status: Status;
  status_label: string;
  allowed_actions: Action[];
  reschedule_url: string | null;
}
export interface AgendaData {
  date: string;
  branches: Branch[];
  reservations: Reservation[];
  can_bulk_complete: boolean;
  summary: {
    total: number;
    attended: number;
    absent: number;
    confirmed: number;
  };
}
export interface BulkPreview {
  date: string;
  branch: number | null;
  count: number;
  token: string;
}
export interface Group {
  name: string;
  total: number;
  attended: number;
  absent: number;
  cancelled: number;
}
export interface StatisticsData {
  salon: { name: string; slug: string };
  month: number;
  year: number;
  branch: number | null;
  branches: Branch[];
  summary: {
    total: number;
    attended: number;
    absent: number;
    cancelled_client: number;
    cancelled_salon: number;
    attendance_rate: number;
    cancellation_rate: number;
    unique_clients: number;
    discounts: number;
  };
  by_branch: Group[];
  by_professional: Group[];
  by_service: Group[];
  distribution: { status: Status; label: string; count: number }[];
  export_url: string;
}
