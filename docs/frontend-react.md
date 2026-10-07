# Frontend React: primera etapa

TuTurnoUy conserva su backend monolítico Django y PostgreSQL. React migra
únicamente Agenda y Estadísticas del panel interno. Las rutas Django Templates
con HTMX siguen disponibles; no se migraron login, recuperación, reprogramación,
catálogo, equipo, recompensas ni el portal público.

## Arquitectura

`frontend/` usa React 19, Vite 8, TypeScript, Tailwind CSS 4, React Router,
TanStack Query, React Hook Form con Zod, Lucide y Recharts. Radix Dialog y
DropdownMenu aportan accesibilidad a los componentes UI propios; no se añade un
framework completo de componentes. Inter se sirve localmente mediante
`@fontsource/inter`, en pesos 400, 500, 600 y 700 y subconjunto latino.

Las versiones exactas y transitivas quedan en `frontend/package-lock.json`.
Node 24 está incluido en el Dockerfile frontend; no es obligatorio instalar Node
en el host. La referencia visual es `docs/direccion-visual-react.md`: fondo
cálido, sidebar carbón, CTA negro, bordes finos y colores de estados desaturados.

- `src/api/`: cliente HTTP y manejo de errores.
- `src/types/`: contratos JSON.
- `src/hooks/`: sesión actual y consultas compartidas.
- `src/components/ui/`: componentes reutilizables.
- `src/features/agenda/`: cards de reservas.
- `src/features/statistics/`: donut y desgloses responsive.
- `src/pages/`: filtros, consultas y coordinación de las acciones.
- `src/layouts/`: sidebar, topbar y sesión vencida.
- `src/routes/`: rutas SPA bajo `/app`, cargadas por separado.
- `src/utils/`: etiquetas y formatos.

Tailwind define los tokens mediante `@theme`; los componentes usan estilos
compartidos que consumen esos tokens. El layout tiene sidebar en desktop y
navegación mediante drawer accesible en tablet/mobile. Los desgloses se presentan
como tablas en desktop y bloques etiquetados en mobile.

## Sesión, cookies y CSRF

No hay JWT, otro login ni otro modelo de usuario. El navegador usa la sesión
Django existente; los puertos localhost comparten cookies del mismo hostname.
No mezclar `localhost` con `127.0.0.1` durante una sesión.

El cliente `src/api/client.ts` usa `credentials: include`. `GET /api/me/` entrega
un token CSRF enmascarado y hace que Django emita la cookie CSRF. Toda acción
JSON envía `X-CSRFToken`; no hay endpoints exentos de CSRF.

Vite funciona como proxy para `/api`, `/cuenta`, `/agenda`, `/peluquerias`,
`/reservar`, `/static` y el dashboard raíz. Conserva el Host del navegador.
Esto permite login, logout, reprogramación y Excel en el mismo origen que React,
sin CORS ni redirecciones absolutas hardcodeadas.

`compose.react.yaml` configura orígenes CSRF de desarrollo específicos para
localhost:5173 y 127.0.0.1:5173. La configuración base permanece sin esos orígenes.
No usar comodines ni desactivar CSRF para resolver problemas del proxy.

- 401: limpia datos de consultas y muestra ingreso usando el login Django con
  `next=/app/...`. No se redirige una respuesta JSON a un formulario HTML.
- 403: muestra la denegación de permisos, sin tratarla como logout.
- 404: los IDs o peluquerías fuera del alcance no revelan información.
- CSRF inválido: devuelve JSON en `/api/`; otras vistas conservan el manejo Django.

## API

Todas las rutas usan sesión Django. GET devuelve JSON; las acciones aceptan
objetos JSON. Errores usan `{"error": "mensaje"}` y el código HTTP correspondiente.

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/me/` | Usuario, membresías, peluquería actual, sucursales, permisos y CSRF |
| GET | `/api/agenda/?date=AAAA-MM-DD&branch=<id>` | Agenda autorizada, resumen y acciones por reserva |
| POST | `/api/reservas/<id>/acciones/` | `{"action":"mark_attended"}`, `mark_absent` o `cancel_local` |
| POST | `/api/agenda/marcado-masivo/preview/` | `{"date":"AAAA-MM-DD","branch":"<id o vacío>"}` |
| POST | `/api/agenda/marcado-masivo/ejecutar/` | `{"token":"<confirmación firmada>"}` |
| GET | `/api/peluquerias/<slug>/estadisticas/?month=<mes>&year=<año>&branch=<id>` | Resumen, agrupaciones y distribución mensual |

`/api/me/` selecciona por defecto la primera membresía activa y acepta
`?salon=<slug autorizado>` para consultar otro contexto. Devuelve también las
membresías y sucursales autorizadas para que la navegación respete usuarios con
más de una peluquería. Esta selección no cambia permisos ni agrega un modelo
nuevo de tenant o una preferencia persistente.

La agenda mantiene el alcance de la agenda Django: todas las reservas que el
usuario puede ver, filtradas por fecha y sucursal. `allowed_actions` sale de
`reservation_actions`, nunca de reglas reconstruidas en React. Incluye
`reschedule_url` únicamente cuando la acción está autorizada.

Las acciones reutilizan `reservation_status.py`, el lote reutiliza
`bulk_completion.py` y las estadísticas reutilizan `owner_report` /
`statistics.py`. Auditoría, bloqueos de filas y transacciones permanecen en esos
servicios existentes. Owner administra su peluquería, Admin sus sucursales y
Peluquero sus propias reservas. Solo Owner accede a Estadísticas y Excel.

El resumen diario cuenta total, atendidas, ausentes y confirmadas de las mismas
reservas devueltas. No se agrega una definición nueva de "próximas".
La distribución mensual se deriva del resumen actual, incluye Confirmadas cuando
existen y omite segmentos en cero. Las fórmulas de métricas no cambian.

Reprogramación abre `/agenda/reservas/<id>/reprogramar/` en Django. Excel enlaza
el endpoint existente `/peluquerias/<slug>/estadisticas/excel/` con los filtros
seleccionados; React no genera ni almacena XLSX.

## Entorno Docker local

Desde la raíz del repositorio, con `.env` ya configurado:

```bash
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml build web frontend
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml up -d db mailpit
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm web python manage.py migrate
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml up -d web frontend
```

El overlay React conserva el Compose base y el overlay de correo. El volumen
PostgreSQL sigue siendo `tuturnouy_email_postgres_data`, definido por
`compose.email.yaml`. Las dependencias Node y el build generado tienen volúmenes separados para evitar
archivos de salida con permisos de root en el host; el
servicio frontend ejecuta `npm ci` al iniciar para mantenerlo alineado con el lock.

| Servicio | URL |
|---|---|
| Agenda React | `http://localhost:5173/app/agenda` |
| Estadísticas React, demo norte | `http://localhost:5173/app/estadisticas/estilo-norte` |
| Login Django vía proxy, vuelve a React | `http://localhost:5173/cuenta/ingresar/?next=/app/agenda` |
| Django / panel actual | `http://localhost:8012/agenda/` |
| Mailpit | `http://localhost:8026/` |

Usar una cuenta operativa existente. Para una base **demo nueva** se puede
cargar `seed_demo` con los mismos archivos Compose. No recargar datos demo en una
base con actividad real para probar React. Las cuentas demo y su contraseña
están descritas en README.

Para detener este entorno, sin borrar volúmenes:

```bash
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml stop
```

## Desarrollo con Node en el host

Con Django y Mailpit levantados por Docker y Node 24 instalado:

```bash
cd frontend
npm ci
npm run dev
```

Vite toma por defecto el proxy `http://localhost:8012`. Se puede configurar
`frontend/.env.local` a partir de `frontend/.env.example`. `VITE_API_BASE_URL`
controla la base relativa `/api`; `DJANGO_PROXY_TARGET` define el destino del
proxy, y no se expone al código cliente. Vite usa puerto estricto 5173.

## Verificación

```bash
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm web python manage.py migrate --check
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm web python manage.py test
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm frontend npm run test
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm frontend npm run build
docker compose -f compose.yaml -f compose.email.yaml -f compose.react.yaml run --rm frontend npm run lint
git diff --check
```

En el host, equivalentes frontend: `npm --prefix frontend run test`,
`npm --prefix frontend run build` y `npm --prefix frontend run lint`.

Los tests API cubren sesión, roles, sucursales, IDs cruzados, acciones y auditoría,
marcado masivo, filtros mensuales, Excel, revocación de membresías y CSRF real.
Vitest/Testing Library cubren loading, empty, errores, cards, badges, acciones,
preview/confirmación masiva, navegación Owner, métricas y donut.

Esta etapa no cambia modelos ni requiere migraciones nuevas. La aplicación
React se sirve mediante Vite exclusivamente para desarrollo local. El build
estático se valida, pero aún no está integrado en un servidor de producción.

## Reversibilidad y siguiente etapa

Se puede seguir usando las URLs Django sin React o iniciar Compose sin el
overlay React. No se eliminaron templates, HTMX ni servicios existentes. No se
migra ninguna otra pantalla ni se implementan JWT, Google Login o despliegue.
La integración productiva de assets/routing será un bloque posterior.
