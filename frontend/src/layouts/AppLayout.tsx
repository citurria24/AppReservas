import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  CalendarDays,
  ChartNoAxesCombined,
  Menu,
  LogOut,
  UsersRound,
  Scissors,
  UserRound,
  MapPin,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useMe } from "../hooks/useMe";
import { ApiError } from "../api/client";
import {
  Dialog,
  ErrorState,
  LoadingSkeleton,
} from "../components/ui/primitives";
import type { Me } from "../types/api";

export function Sidebar({ me, close }: { me: Me; close?: () => void }) {
  return (
    <div className="sidebar-content">
      <NavLink to="/agenda" className="brand" onClick={close}>
        TuTurno<span>Uy</span>
        <small>GESTIÓN DE TURNOS</small>
      </NavLink>
      <nav aria-label="Navegación principal">
        <NavLink to="/agenda" onClick={close}>
          <CalendarDays size={19} />
          Agenda
        </NavLink>
        {me.salons
          .filter((s) => s.role === "owner")
          .map((s) => (
            <NavLink
              key={s.slug}
              to={`/estadisticas/${s.slug}`}
              onClick={close}
            >
              <ChartNoAxesCombined size={19} />
              Estadísticas{me.salons.length > 1 ? ` · ${s.name}` : ""}
            </NavLink>
          ))}
        <div className="sidebar-future" aria-label="Próximas secciones">
          {[
            { label: "Equipo", icon: UsersRound },
            { label: "Servicios", icon: Scissors },
            { label: "Profesionales", icon: UserRound },
            { label: "Sucursales", icon: MapPin },
          ].map(({ label, icon: Icon }) => (
            <span key={label}>
              <Icon size={18} aria-hidden />
              {label}
            </span>
          ))}
        </div>
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-user">
          <span className="user-avatar" aria-hidden>
            {me.display_name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{me.display_name}</strong>
            <span>
              {me.role === "owner"
                ? "Owner"
                : me.role === "admin"
                  ? "Admin"
                  : me.role === "hairdresser"
                    ? "Peluquero"
                    : "Usuario"}
            </span>
          </div>
        </div>
        <form action={me.logout_url} method="post">
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={me.csrf_token}
          />
          <button className="sidebar-logout">
            <LogOut size={18} aria-hidden />
            Salir
          </button>
        </form>
        <a href="/agenda/">Panel anterior</a>
      </div>
    </div>
  );
}
export function Topbar({ me, openMenu }: { me: Me; openMenu: () => void }) {
  const location = useLocation();
  return (
    <header className="topbar">
      <button
        className="icon-button navigation-toggle"
        onClick={openMenu}
        aria-label="Abrir navegación"
      >
        <Menu size={20} />
      </button>
      <div className="topbar-context">
        <span>
          {location.pathname.includes("estadisticas")
            ? "Estadísticas"
            : "Agenda"}
        </span>
        <span className="topbar-salon">
          {me.salons.find(
            (s) => location.pathname === `/estadisticas/${s.slug}`,
          )?.name ||
            me.salon?.name ||
            "Panel interno"}
        </span>
      </div>
      <div className="user-controls">
        <span>{me.display_name}</span>
        <span className="topbar-avatar" aria-hidden>
          {me.display_name.slice(0, 1).toUpperCase()}
        </span>
      </div>
    </header>
  );
}
export function AppLayout() {
  const me = useMe();
  const [menu, setMenu] = useState(false);
  const [expired, setExpired] = useState(false);
  const queryClient = useQueryClient();
  useEffect(() => {
    const expire = () => {
      setExpired(true);
      queryClient.clear();
    };
    window.addEventListener("auth-expired", expire);
    return () => window.removeEventListener("auth-expired", expire);
  }, [queryClient]);
  if (expired || (me.error instanceof ApiError && me.error.status === 401))
    return (
      <main className="login-state">
        <ErrorState message="La sesión venció. Ingresá nuevamente." />
        <a
          className="button button-primary"
          href={`/cuenta/ingresar/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}
        >
          Ingresar
        </a>
      </main>
    );
  if (me.isPending)
    return (
      <main className="login-state">
        <LoadingSkeleton />
      </main>
    );
  if (me.isError)
    return (
      <main className="login-state">
        <ErrorState retry={() => void me.refetch()} />
      </main>
    );
  return (
    <div className="app-shell">
      <aside className="desktop-sidebar">
        <Sidebar me={me.data} />
      </aside>
      <div className="app-body">
        <Topbar me={me.data} openMenu={() => setMenu(true)} />
        <div className="content-canvas">
          <main id="main-content" className="page-content">
            <Outlet />
          </main>
        </div>
      </div>
      <Dialog
        open={menu}
        onOpenChange={setMenu}
        title="Navegación"
        description="Secciones del panel interno"
      >
        <Sidebar me={me.data} close={() => setMenu(false)} />
      </Dialog>
      <a className="skip-link" href="#main-content">
        Ir al contenido
      </a>
    </div>
  );
}
