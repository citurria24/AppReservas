# TuTurnoUy

Base funcional de una aplicación multi-peluquería de reservas. Es un monolito modular con Django 5.2 LTS, Templates, HTMX y PostgreSQL 17. No existe configuración alternativa con SQLite.

## Requisitos

- Docker Engine y Docker Compose v2.
- Puerto `8000` libre en localhost.

## Arranque

Todos los comandos se ejecutan desde `/home/carlos/proyectos/tuturnouy` y están escritos en una sola línea.

1. Crear la configuración local: `cp .env.example .env`
2. Construir los contenedores: `docker compose build`
3. Levantar PostgreSQL: `docker compose up -d db`
4. Aplicar migraciones: `docker compose run --rm web python manage.py migrate`
5. Cargar datos demo: `docker compose run --rm web python manage.py seed_demo`
6. Levantar la aplicación: `docker compose up -d web`
7. Abrir `http://localhost:8000/`.

Para detener los servicios: `docker compose down`

El volumen `tuturnouy_postgres_data` conserva PostgreSQL entre reinicios. Para borrar también los datos, solo cuando sea intencional: `docker compose down -v`

## Cuentas demo

Todas usan la contraseña `DemoTuTurno2026!`.

| Usuario | Peluquería | Rol | Sucursales visibles |
|---|---|---|---|
| `owner_norte` | Estilo Norte | Owner | Centro y Pocitos |
| `admin_norte` | Estilo Norte | Admin | Centro |
| `peluquero_norte` | Estilo Norte | Peluquero | Pocitos |
| `owner_sur` | Casa Sur | Owner | Cordón |

Las cuentas demo son operativas y no pueden entrar a Django Admin. Para administración técnica se puede crear un superusuario con `docker compose run --rm web python manage.py createsuperuser`.

## Probar el flujo cliente

No hace falta una cuenta local de cliente. El flujo aprobado usa Google o invitado con correo verificado; en esta etapa está disponible el flujo completo de invitado.

- Estilo Norte: `http://localhost:8000/reservar/estilo-norte/`
- Casa Sur: `http://localhost:8000/reservar/casa-sur/`

Ingresá nombre, apellido, correo y teléfono. Con `DJANGO_DEBUG=True`, la siguiente pantalla muestra el código de seis dígitos para facilitar la prueba local; también se imprime en `docker compose logs web`. Luego elegí sucursal, servicio, profesional y fecha. Los datos demo tienen jornadas de lunes a sábado de 09:00 a 18:00, con descanso de 13:00 a 14:00.

Después de verificar el correo, el enlace **Mis reservas** muestra únicamente los turnos asociados a ese correo dentro de la peluquería visitada. Desde allí se puede consultar el detalle y cancelar una reserva cuando todavía está dentro del plazo permitido. La sesión verificada dura 24 horas y no se comparte entre peluquerías.

Google OAuth todavía requiere registrar la aplicación y aportar sus credenciales. En un entorno real también debe configurarse un backend SMTP o transaccional en lugar del backend de consola.

## Agenda interna

Los usuarios operativos acceden a `http://localhost:8000/agenda/` desde el enlace **Agenda** de la cabecera. Owner ve todas las reservas de su peluquería, admin solo las sucursales asignadas y peluquero únicamente sus propios turnos. Owner/admin pueden cancelar desde el local y los usuarios autorizados pueden marcar una reserva como atendida. `seed_demo` crea una reserva futura por peluquería para probar esta pantalla.

Owner y admin pueden entrar en **Configurar políticas → Gestionar jornadas y ausencias** para agregar o quitar jornadas semanales, descansos y ausencias. Los formularios y acciones quedan restringidos a las sucursales autorizadas del usuario.

## Catálogo operativo

El owner puede administrar desde **Configurar políticas** las sucursales, los servicios y los profesionales sin ingresar a Django Admin. Puede activar o desactivar registros conservando su historial, definir la duración de cada servicio por sucursal y asignar profesionales a sus sucursales y servicios. Estas pantallas validan el aislamiento por peluquería; la vinculación de un profesional continúa siendo independiente del rol operativo de un usuario.

## Cancelaciones

Owner y admin pueden configurar la anticipación mínima desde **Configurar políticas** dentro del detalle de la peluquería. Cada reserva conserva el valor vigente al ser creada. La confirmación muestra un enlace protegido por un token no predecible; el mismo enlace se envía por correo y permite cancelar hasta el plazo configurado. Si el plazo venció, se muestra el teléfono de la sucursal.

Desde esa misma configuración se registran excepciones al límite de cinco reservas activas por cliente, fecha y peluquería. Cada excepción permite una reserva adicional, es de un solo uso y conserva correo, fecha, motivo, usuario autorizante y reserva asociada.

## Recompensas

El owner puede activar un programa desde **Configurar recompensas**, elegir meta de servicios atendidos, período mensual o anual y porcentaje de descuento. Al alcanzar la meta, el beneficio se aplica automáticamente a la siguiente reserva del mismo correo verificado. El canje queda asociado a esa reserva y no puede repetirse dentro del mismo período.

Los datos demo activan en Estilo Norte una recompensa de 15% después de dos servicios mensuales. Para probarla, iniciá el flujo de invitado con `cliente.recompensa@example.test`; los dos servicios atendidos necesarios ya están cargados.

## Migraciones y datos

- Crear migraciones tras cambiar modelos: `docker compose run --rm web python manage.py makemigrations`
- Aplicar migraciones: `docker compose run --rm web python manage.py migrate`
- Recargar datos demo de forma idempotente: `docker compose run --rm web python manage.py seed_demo`

## Pruebas

Ejecutar las pruebas reales sobre PostgreSQL: `docker compose run --rm web python manage.py test`

Las pruebas comprueban explícitamente el motor PostgreSQL, aislamiento entre peluquerías, respuesta 404 ante acceso cruzado, autorización por sucursal, administración segura del catálogo, un solo owner, independencia entre rol y profesional, duración única por sucursal, verificación del invitado, aislamiento del portal del cliente por correo y peluquería, creación completa de una reserva, jornadas y descansos, rechazo de IDs de otro tenant y prevención de solapamientos en PostgreSQL.

## Arquitectura

- `accounts`: usuario personalizado creado desde la primera migración.
- `salons`: dominio de peluquerías, membresías, sucursales, profesionales, servicios y autorización multi-tenant.
- `templates` y `static`: panel responsive en español, con navegación progresivamente mejorada por HTMX.
- `docs/requisitos.md`: alcance futuro registrado sin adelantar su implementación.

La aplicación solo publica `127.0.0.1:8000`. PostgreSQL permanece dentro de la red de Compose y no expone puertos al host. La configuración sensible vive en `.env`, que no se versiona.
