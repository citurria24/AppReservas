# Trabajo paralelo: equipo y correo

## Base y worktrees

Ambas ramas fueron creadas desde el commit probado `e9118c84e05d13ded5cb64e6417ccd20a10df114` (`e9118c8`). En esa base se ejecutaron 52 pruebas sobre PostgreSQL, `makemigrations --check --dry-run` y `migrate --check`, todos correctamente.

| Bloque | Rama | Worktree | Responsable |
|---|---|---|---|
| Gestión del equipo | `feature/team-management` | `/home/carlos/proyectos/tuturnouy` | Agente principal |
| Entrega de correo | `feature/email-delivery` | `/home/carlos/proyectos/tuturnouy-email` | Segundo agente |

No se deben hacer merges ni pushes desde las ramas de trabajo. Cada agente entrega commits locales y resultados de pruebas para una integración posterior.

## Propiedad de archivos

La propiedad es exclusiva durante el trabajo paralelo. Si un cambio requiere un archivo asignado al otro agente, se documenta como dependencia y no se modifica.

### Gestión del equipo

- `salons/team_forms.py`
- `salons/team_views.py`
- `salons/team_urls.py`
- `salons/urls.py`
- `salons/tests/test_team_management.py`
- `templates/salons/team_*.html`
- `templates/salons/settings.html`
- `static/css/app.css`
- `compose.team.yaml`
- `README.md`
- `docs/parallel-work.md`
- Migraciones de `salons` únicamente si resultan imprescindibles para este bloque.

### Entrega de correo

- `accounts/forms.py`
- `accounts/views.py`
- `accounts/urls.py`
- `accounts/tokens.py` y otros módulos nuevos dentro de `accounts/`
- `accounts/tests/`
- `config/settings.py`
- `config/urls.py`
- `salons/email_delivery.py` y otros módulos nuevos dedicados exclusivamente al correo
- `salons/views.py`, solamente para sustituir los puntos actuales de envío de verificación y confirmación
- `salons/tests/test_email_delivery.py`
- `templates/emails/`
- `templates/registration/password_reset*.html`
- `templates/registration/login.html`
- `.env.example`
- `compose.email.yaml`
- `docs/email-delivery.md`
- `requirements.txt`, solo si el correo requiere una dependencia nueva
- Migraciones de `accounts` o `salons` creadas por este bloque.

### Archivos compartidos con responsable único

| Archivo | Responsable único | Contrato |
|---|---|---|
| `salons/urls.py` | Gestión del equipo | Correo no agrega rutas aquí; las rutas de contraseña se incluyen desde `config/urls.py` o `accounts/urls.py`. |
| `salons/views.py` | Entrega de correo | Equipo implementa todas sus vistas en `salons/team_views.py`. |
| `config/settings.py` | Entrega de correo | Equipo no agrega aplicaciones ni configuración global. |
| `config/urls.py` | Entrega de correo | Equipo incluye sus rutas desde `salons/urls.py`. |
| `static/css/app.css` | Gestión del equipo | Correo reutiliza estilos existentes y entrega cualquier necesidad adicional como nota. |
| `README.md` | Gestión del equipo | Correo documenta detalles en `docs/email-delivery.md`; se consolidará luego. |
| `.env.example` | Entrega de correo | Debe conservar todas las variables existentes y agregar las de SMTP sin secretos. |
| Migraciones | Quien cambie el modelo correspondiente | No renumerar migraciones del otro bloque; revisar dependencias y ejecutar `makemigrations --merge` solo durante integración si Django detecta ramas paralelas. |

## Contratos compartidos

- `accounts.User` continúa siendo el usuario autenticable y su correo sigue siendo único.
- Gestión del equipo usa `get_user_model()` y no modifica `accounts/models.py`.
- El owner solo puede crear membresías `admin` o `hairdresser`; este bloque no transfiere ownership.
- El owner existente no aparece como destino editable, revocable ni desactivable.
- Toda sucursal y profesional recibidos por formulario deben pertenecer a la peluquería de la URL.
- Vincular un profesional consiste en asignar `Professional.user`; no convierte automáticamente al usuario en profesional ni altera su rol.
- Desactivar una membresía debe surtir efecto en la siguiente petición aunque el usuario conserve una sesión autenticada.
- El correo implementa recuperación de contraseña sin revelar si el correo existe y no cambia los permisos de membresía.
- Los envíos de correo deben tener versiones texto y HTML. Un fallo de entrega no puede avanzar al estado de éxito.
- Códigos y tokens solo pueden exponerse mediante mecanismos explícitos de desarrollo; nunca en pantalla ni logs con `DJANGO_DEBUG=False`.
- Google OAuth queda fuera de ambos bloques.

## Entornos Compose aislados

Docker Compose 2.40.3 admite `!override`. Los nombres de proyecto separan contenedores, redes, bases de prueba y volúmenes PostgreSQL.

### Equipo

- Proyecto: `tuturnouy_team`
- Web: `127.0.0.1:8011`
- Volumen: `tuturnouy_team_postgres_data`
- Arranque: `docker compose -p tuturnouy_team -f compose.yaml -f compose.team.yaml up -d --build`
- Migraciones: `docker compose -p tuturnouy_team -f compose.yaml -f compose.team.yaml run --rm web python manage.py migrate`
- Datos demo: `docker compose -p tuturnouy_team -f compose.yaml -f compose.team.yaml run --rm web python manage.py seed_demo`
- Pruebas: `docker compose -p tuturnouy_team -f compose.yaml -f compose.team.yaml run --rm web python manage.py test`
- Detener: `docker compose -p tuturnouy_team -f compose.yaml -f compose.team.yaml down`

### Correo

- Proyecto: `tuturnouy_email`
- Web: `127.0.0.1:8012`
- SMTP local: puerto interno `1025`, sin publicar al host salvo necesidad explícita
- Interfaz del servidor de correo: `127.0.0.1:8026`
- Volumen: `tuturnouy_email_postgres_data`
- El segundo agente debe crear `compose.email.yaml` con reemplazo del puerto web, servidor local de correo y variables SMTP.
- Arranque: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml up -d --build`
- Migraciones: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py migrate`
- Datos demo: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py seed_demo`
- Pruebas: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py test`
- Detener: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml down`

Cada worktree usa su propio `.env` ignorado por Git. Aunque los nombres lógicos de base coincidan, los servidores y volúmenes son distintos. Las pruebas de Django se crean dentro del PostgreSQL del proyecto correspondiente; nunca se ejecutan ambos bloques contra el proyecto Compose por defecto.

## Integración posterior

1. Confirmar que ambos worktrees estén limpios, salvo archivos locales ignorados, y registrar sus hashes de commit.
2. Revisar `git diff e9118c8..feature/team-management` y `git diff e9118c8..feature/email-delivery` antes de integrar.
3. Verificar que cada rama respetó la propiedad exclusiva de archivos.
4. Inspeccionar por separado las migraciones nuevas. Si hay dos hojas para la misma aplicación, integrar ambas ramas y ejecutar `python manage.py makemigrations --merge` en una rama de integración.
5. Integrar con `git merge --no-ff feature/team-management` y luego `git merge --no-ff feature/email-delivery`, resolviendo únicamente los puntos previstos por este documento.
6. Construir una imagen nueva y ejecutar todas las migraciones sobre un tercer proyecto Compose de integración con volumen propio.
7. Ejecutar la suite completa, las pruebas específicas de equipo y correo, y `makemigrations --check --dry-run`.
8. Probar manualmente creación/revocación de miembros, verificación de invitado, recuperación de contraseña y fallos SMTP.
9. Recién después decidir el merge a `develop` y posteriormente a `main`. Los pushes siguen siendo manuales.
