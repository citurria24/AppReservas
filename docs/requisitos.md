# Requisitos de TuTurnoUy

## Alcance de esta primera entrega

La base funcional es un monolito modular construido con Django, Django Templates y HTMX. Incluye PostgreSQL como única base de datos, usuario personalizado, autenticación local, panel privado responsive, aislamiento por peluquería, autorización por sucursal y un primer flujo público de reservas para invitados.

Reglas implementadas:

- Cada peluquería tiene exactamente como máximo un owner en la base de datos y puede tener varios administradores y peluqueros.
- Ser profesional es una condición independiente del rol de la membresía. Un profesional puede estar vinculado o no a un usuario.
- Cada servicio define una sola duración por sucursal. Esa duración es común a todos los profesionales que lo prestan allí.
- Los owners ven todas las sucursales activas de su peluquería. Los demás miembros solo ven las sucursales asignadas explícitamente.
- Las consultas del panel parten siempre de la membresía activa del usuario. Las relaciones entre objetos de distintas peluquerías son rechazadas.
- Django Admin queda reservado para la administración técnica de la plataforma; las cuentas operativas demo no tienen acceso de staff.
- Cada peluquería tiene un enlace público para iniciar una reserva.
- El invitado informa nombre, apellido, correo y contacto, y verifica un código de seis dígitos antes de reservar.
- La reserva permite seleccionar sucursal, servicio, profesional, fecha, hora y notas opcionales.
- La disponibilidad se calcula con la duración por sucursal, jornadas, descansos, ausencias y reservas existentes; no ofrece turnos que atraviesen un descanso o el cierre.
- Las reservas se crean dentro de una transacción y PostgreSQL impide solapamientos para un mismo profesional mediante una restricción de exclusión.
- La duración y una anticipación de cancelación inicial de 24 horas quedan conservadas en cada reserva.

## Alcance posterior registrado, no implementado

- Acceso con Google. El acceso como invitado con correo verificado ya está implementado; falta conectar un proveedor real de correo fuera del modo de desarrollo.
- Configuración de la anticipación mínima para cancelar por owner o admin. La reserva ya conserva el valor, inicialmente fijado en 24 horas.
- Después de tres cancelaciones computables, bloqueo para nuevas reservas durante 24 horas, mostrando el vencimiento y el teléfono del local. Las cancelaciones realizadas por el local no cuentan.
- El período dentro del cual se contarán esas tres cancelaciones está pendiente de confirmación. **No se considera un requisito aprobado y no debe asumirse todavía.**
- Máximo de cinco reservas activas por cliente para una misma fecha dentro de una peluquería, sumando todas sus sucursales. Las excepciones realizadas por un admin deben quedar registradas.
- Recompensas opcionales configuradas por el owner: cantidad de servicios atendidos, período mensual o anual y porcentaje de descuento, con canje único.

## Decisiones pendientes para la siguiente etapa

- Confirmar el período de conteo de las cancelaciones computables.
- Definir proveedor y flujo de correo para verificación de invitados.
- Precisar estados de una reserva y reglas de reprogramación.
- Definir jornadas, pausas y ausencias, incluida su zona horaria y recurrencia.
- Acordar trazabilidad y motivo obligatorio para las excepciones de administradores.
