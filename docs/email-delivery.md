# Entrega de correo

## Alcance implementado

- Los códigos de verificación de invitados se envían con versiones texto y HTML.
- Las confirmaciones de reserva se envían con versiones texto y HTML e incluyen el enlace de consulta y cancelación.
- El personal puede solicitar la recuperación de contraseña desde la pantalla de ingreso.
- Los enlaces de recuperación usan los tokens nativos de Django: vencen según `PASSWORD_RESET_TIMEOUT` y dejan de ser válidos después de cambiar la contraseña.
- La solicitud de recuperación devuelve la misma respuesta HTTP exista o no una cuenta activa. También intenta una entrega para correos desconocidos, con un mensaje neutro sin token, para que un fallo del transporte no permita distinguir cuentas por la respuesta web.
- Un fallo de entrega deja el formulario visible con un error controlado. El código no se persiste y una reserva cuya confirmación no pudo enviarse se revierte dentro de la misma transacción.
- Los códigos solo se muestran en la interfaz cuando `DJANGO_DEBUG=True`. Con `DJANGO_DEBUG=False` no se guardan en la sesión de depuración ni se renderizan.
- La configuración productiva rechaza backends de consola o archivos con `DJANGO_DEBUG=False`, para evitar que códigos y tokens terminen en logs o archivos locales.
- Google OAuth no forma parte de este bloque.

No fue necesario modificar modelos ni crear migraciones.

## Variables de entorno

| Variable | Uso | Valor local |
|---|---|---|
| `DJANGO_EMAIL_BACKEND` | Backend de Django | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | Servidor SMTP | `mailpit` |
| `EMAIL_PORT` | Puerto SMTP | `1025` |
| `EMAIL_HOST_USER` | Usuario SMTP, si corresponde | vacío |
| `EMAIL_HOST_PASSWORD` | Contraseña SMTP, si corresponde | vacío |
| `EMAIL_USE_TLS` | Activar STARTTLS | `False` |
| `EMAIL_USE_SSL` | Activar TLS implícito | `False` |
| `EMAIL_TIMEOUT` | Tiempo máximo de conexión en segundos | `10` |
| `DEFAULT_FROM_EMAIL` | Remitente | `reservas@tuturnouy.local` |
| `PASSWORD_RESET_TIMEOUT` | Validez del enlace en segundos | `3600` |

`EMAIL_USE_TLS` y `EMAIL_USE_SSL` no pueden activarse simultáneamente. Las credenciales reales deben quedar solamente en el entorno y nunca en Git.

## Entorno local aislado

El archivo `compose.email.yaml` debe combinarse con `compose.yaml` y utilizar siempre el proyecto `tuturnouy_email`:

- Aplicación: http://localhost:8012/
- Mailpit: http://localhost:8026/
- SMTP: `mailpit:1025`, accesible solamente dentro de la red Compose.
- PostgreSQL: volumen `tuturnouy_email_postgres_data`.

Arranque: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml up -d --build`

Migraciones: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py migrate`

Datos demo: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py seed_demo`

Pruebas específicas: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py test accounts.tests.test_password_reset salons.tests.test_email_delivery`

Suite completa: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py test`

Verificación de migraciones: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml run --rm web python manage.py makemigrations --check --dry-run`

Detener: `docker compose -p tuturnouy_email -f compose.yaml -f compose.email.yaml down`

## Pruebas realizadas

- 9 pruebas específicas aprobadas sobre el PostgreSQL aislado.
- 61 pruebas de la suite completa aprobadas sobre el PostgreSQL aislado.
- `makemigrations --check --dry-run`: sin cambios detectados.
- Migraciones aplicadas y `migrate --check`: sin pendientes.
- Aplicación respondiendo HTTP 200 en `127.0.0.1:8012`.
- Mailpit recibió mediante SMTP real un mensaje con partes texto y HTML; su API respondió en `127.0.0.1:8026`.
- `check --deploy` con `DJANGO_DEBUG=False` no encontró errores; conserva cinco advertencias globales ya pendientes para el despliegue: HSTS, redirección HTTPS, clave local de desarrollo y cookies seguras de sesión/CSRF.

Las pruebas cubren vencimiento y uso único de códigos y tokens, ausencia del código en pantalla con `DEBUG=False`, fallos del backend, rollback de reservas y respuestas web que no enumeran cuentas.

## Integración

El commit funcional es `8189589db01f8274b492c4539fb3f0e91ac0d778`. Antes de integrar se debe revisar `git diff e9118c8..feature/email-delivery`, integrar después de gestión del equipo y ejecutar la suite completa en un tercer proyecto Compose con PostgreSQL propio. Esta rama no contiene migraciones, por lo que no agrega una hoja al grafo de migraciones.
