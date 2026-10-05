# Requisitos de TuTurnoUy

## Alcance de esta primera entrega

La base funcional es un monolito modular construido con Django, Django Templates y HTMX. Incluye PostgreSQL como única base de datos, usuario personalizado, autenticación local, panel privado responsive, aislamiento por peluquería, autorización por sucursal y un primer flujo público de reservas para invitados.

Reglas implementadas:

- Cada peluquería tiene como máximo un owner en la base de datos y puede tener varios administradores y peluqueros.
- Ser profesional es una condición independiente del rol de la membresía. Un profesional puede estar vinculado o no a un usuario.
- Cada servicio define una sola duración por sucursal. Esa duración es común a todos los profesionales que lo prestan allí.
- Los owners ven todas las sucursales activas de su peluquería. Los demás miembros solo ven las sucursales asignadas explícitamente.
- El owner gestiona sucursales, servicios, duraciones por sucursal y asignaciones de profesionales desde el panel operativo. Puede desactivar registros sin borrar su historial y no puede consultar ni modificar objetos de otra peluquería.
- Las consultas del panel parten siempre de la membresía activa del usuario. Las relaciones entre objetos de distintas peluquerías son rechazadas.
- Django Admin queda reservado para la administración técnica de la plataforma; las cuentas operativas demo no tienen acceso de staff.
- Cada peluquería tiene un enlace público para iniciar una reserva.
- El invitado informa nombre, apellido, correo y contacto, y verifica un código de seis dígitos antes de reservar.
- La sesión verificada permite consultar **Mis reservas** durante 24 horas. El listado se limita al correo verificado y a la peluquería actual, con acceso al detalle y a la cancelación permitida.
- La reserva permite seleccionar sucursal, servicio, profesional, fecha, hora y notas opcionales.
- La disponibilidad se calcula con la duración por sucursal, jornadas, descansos, ausencias y reservas existentes; no ofrece turnos que atraviesen un descanso o el cierre.
- Owner y admin gestionan jornadas, descansos y ausencias desde el panel operativo, limitados a sus sucursales autorizadas.
- Las reservas se crean dentro de una transacción y PostgreSQL impide solapamientos para un mismo profesional mediante una restricción de exclusión.
- Owner y admin configuran la anticipación mínima para cancelar; el valor vigente queda conservado en cada nueva reserva. El invitado recibe un enlace con token no predecible y puede cancelar hasta ese límite.
- La agenda interna filtra por fecha y sucursal respetando el alcance de owner, admin y peluquero. Las reservas comienzan Confirmadas; permiten pasar a Atendida o Ausente. Ausente significa que el cliente no asistió. Atendida, Ausente y las cancelaciones son finales. El backend rechaza transiciones inválidas y la interfaz muestra solo acciones autorizadas.
- Owner puede cambiar estados de toda su peluquería; admin solo de sus sucursales autorizadas; peluquero solo de su Professional vinculado y sus sucursales asignadas. Cancelación por local y reprogramación continúan limitadas a owner/admin sobre Confirmadas.
- Cada cambio de estado guarda reserva, estado anterior/nuevo y timestamp en ReservationStatusChange. Los cambios internos requieren usuario responsable; las cancelaciones del cliente por token se registran sin usuario interno. El historial se conserva sin edición desde el flujo operativo y con acceso de solo lectura en Django Admin.
- Las Confirmadas bloquean disponibilidad y superposición en PostgreSQL y cuentan para el límite diario de reservas activas. Los estados finales liberan el intervalo. Solo Atendida suma servicios para recompensas.
- Tres cancelaciones del cliente dentro de una ventana móvil de 30 días bloquean nuevas reservas durante 24 horas, usando cancelled_at. Se muestra vencimiento y teléfono del local; las cancelaciones del local se excluyen y el bloqueo se aísla por correo y peluquería.
- Una reserva confirmada puede reprogramarse sin cambiar sucursal, servicio ni profesional. El cliente puede hacerlo con su token dentro del plazo de cancelación; owner y admin pueden hacerlo desde la agenda según su alcance. Cada cambio conserva horario anterior, horario nuevo, origen y usuario responsable, y se revierte si falla el correo de confirmación.
- Un cliente puede tener hasta cinco reservas activas para una misma fecha dentro de una peluquería, sumando sucursales. Owner y admin pueden registrar excepciones de un solo uso con correo, fecha, motivo, autor y reserva que la consumió.
- El owner puede activar recompensas mensuales o anuales, definir servicios atendidos requeridos y porcentaje de descuento. El beneficio se aplica a la siguiente reserva elegible, queda registrado en ella y solo puede canjearse una vez por período.

- Los cinco estados definitivos son Confirmada, Atendida, Ausente, Cancelada por cliente y Cancelada por local. Solo Confirmada permite cambios operativos, cancelación o reprogramación. La migración 0009 convierte `in_progress` a `confirmed`, conserva el historial y registra cada conversión sin usuario por tratarse de una migración automática. No se reconstruye el estado retirado al revertir el esquema.
- Owner y Admin pueden marcar masivamente como Atendidas las Confirmadas ya finalizadas de la fecha y sucursal seleccionadas, restringidas a sus sucursales administradas. La finalización usa inicio más duración almacenada y debe ser anterior a la hora actual. Peluquero no puede ejecutar la acción.
- Antes del lote se muestra la cantidad y se exige confirmación firmada, ligada al usuario y válida por 15 minutos. Se revisan nuevamente permisos y elegibilidad; no se agregan reservas fuera de la vista previa. La operación es transaccional y crea una entrada de auditoría por reserva, informa cuántas cambió y refresca la agenda manteniendo filtros. Una confirmación repetida no duplica auditoría.
- Estadísticas y exportación XLSX son exclusivas de Owner. Tanto navegación como backend mantienen aislamiento por peluquería. Los filtros incluyen mes, año y sucursal o todas las sucursales, también las inactivas para reportar historial.
- Las métricas se calculan por inicio del turno en America/Montevideo y estado actual: total, atendidas, ausentes, ambas cancelaciones, clientes únicos por correo normalizado, reservas con descuento aplicado y agrupaciones por sucursal, profesional y servicio. Asistencia = atendidas / (atendidas + ausentes); cancelación = ambas cancelaciones / total; denominadores vacíos producen cero. El conteo de beneficios aplicados usa el porcentaje guardado, cualquiera sea el estado, sin alterar RewardProgram ni RewardRedemption.
- El Excel se genera bajo demanda en memoria con openpyxl, sin almacenamiento permanente, con cinco hojas: Resumen, Reservas, Profesionales, Servicios y Sucursales. Respeta los filtros, aplica formatos, encabezados, autofiltros y filas congeladas, y no expone IDs técnicos. PostgreSQL es la fuente de verdad. No se implementan ingresos, facturación ni otras métricas económicas.

## Alcance posterior registrado, no implementado

- Acceso con Google. El acceso como invitado con correo verificado ya está implementado; falta conectar un proveedor real de correo fuera del modo de desarrollo.

## Decisiones pendientes para la siguiente etapa

- Definir proveedor y flujo de correo para verificación de invitados.
- Definir si las jornadas, pausas o ausencias necesitarán reglas de recurrencia adicionales a la configuración semanal actual.
- Acordar trazabilidad y motivo obligatorio para las excepciones de administradores.
