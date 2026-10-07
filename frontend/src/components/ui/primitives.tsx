import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  SelectHTMLAttributes,
  ReactNode,
} from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { MoreHorizontal, X, CalendarDays, AlertCircle } from "lucide-react";
import type { Status } from "../../types/api";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props} />
  );
}
export function Card({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card ${className}`} {...props} />;
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="control" {...props} />;
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="control" {...props} />;
}
export function Badge({
  status,
  children,
}: {
  status: Status;
  children: ReactNode;
}) {
  return <span className={`badge badge-${status}`}>{children}</span>;
}
export function PageHeader({
  title,
  description,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {description && <p className="muted">{description}</p>}
      </div>
      {children}
    </header>
  );
}
export function StatCard({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <Card className="stat-card">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}
export function EmptyState({
  message = "No hay reservas para los filtros seleccionados.",
}: {
  message?: string;
}) {
  return (
    <Card className="state-box">
      <CalendarDays size={24} aria-hidden />
      <h2>{message}</h2>
    </Card>
  );
}
export function ErrorState({
  forbidden = false,
  message,
  retry,
}: {
  forbidden?: boolean;
  message?: string;
  retry?: () => void;
}) {
  return (
    <Card className="state-box" role="alert">
      <AlertCircle size={24} aria-hidden />
      <h2>
        {forbidden
          ? "No tenés permisos para acceder a esta sección."
          : message || "No pudimos cargar los datos. Intentá nuevamente."}
      </h2>
      {retry && (
        <Button variant="secondary" onClick={retry}>
          Intentar nuevamente
        </Button>
      )}
    </Card>
  );
}
export function LoadingSkeleton() {
  return (
    <div role="status" aria-label="Cargando datos" className="loading">
      <span className="sr-only">Cargando datos</span>
      {[1, 2, 3].map((i) => (
        <div key={i} className="skeleton" />
      ))}
    </div>
  );
}
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="dialog-content">
          <DialogPrimitive.Title>{title}</DialogPrimitive.Title>
          <DialogPrimitive.Description>
            {description}
          </DialogPrimitive.Description>
          {children}
          <DialogPrimitive.Close className="dialog-close" aria-label="Cerrar">
            <X size={20} />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  pending,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  onConfirm: () => void;
  pending: boolean;
  error?: string;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!pending) onOpenChange(value);
      }}
      title={title}
      description={description}
    >
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <Button
          variant="secondary"
          disabled={pending}
          onClick={() => onOpenChange(false)}
        >
          Volver
        </Button>
        <Button disabled={pending} onClick={onConfirm}>
          {pending ? "Procesando…" : "Confirmar"}
        </Button>
      </div>
    </Dialog>
  );
}
export interface MenuAction {
  label: string;
  href?: string;
  onSelect?: () => void;
  danger?: boolean;
}
export function DropdownMenu({
  actions,
  label,
}: {
  actions: MenuAction[];
  label: string;
}) {
  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <button className="icon-button" aria-label={label}>
          <MoreHorizontal size={20} />
        </button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className="dropdown" align="end" sideOffset={6}>
          {actions.map((action) => (
            <Menu.Item
              key={action.label}
              className={`dropdown-item ${action.danger ? "error-text" : ""}`}
              onSelect={action.onSelect}
              asChild={Boolean(action.href)}
            >
              {action.href ? (
                <a href={action.href}>{action.label}</a>
              ) : (
                action.label
              )}
            </Menu.Item>
          ))}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}
