# Dirección visual de TuTurnoUy para React

Guía para la futura implementación del panel interno. Este documento no migra
pantallas ni modifica reglas de negocio. La integración técnica con Django y el
alcance de la primera etapa se documentan en `docs/frontend-react.md`. Esta guía
permanece como referencia visual oficial.

## Identidad

SaaS premium, moderno, sobrio, editorial y profesional. Influencia sutil de
barbería contemporánea, sin tematizar todo el panel. Priorizar claridad, confianza
y consistencia sobre decoración. La identidad de cada negocio queda reservada
para una futura experiencia pública.

No usar neón, colores eléctricos, glow, glassmorphism, fondos futuristas, blobs,
gradientes decorativos, bordes luminosos ni sombras fuertes. No implementar
React, librerías o endpoints a partir de supuestos sobre el bloque técnico.

## Tokens visuales definidos

| Token | Valor | Uso |
|---|---|---|
| `background` | `#F7F7F5` | Fondo general |
| `surface` | `#FFFFFF` | Superficies e inputs |
| `text` | `#111111` | Texto principal y CTA |
| `text-muted` | `#6B6B6B` | Texto secundario |
| `border` | `#E7E7E4` | Divisores y bordes finos |
| `surface-muted` | `#F0F0ED` | Fondos secundarios |
| `sidebar` | `#191919` | Navegación lateral |
| `on-dark` | `#FFFFFF` | Texto sobre navegación y CTA |
| `focus` | `#595959` | Indicador de foco neutro |

Tipografía elegida: **Inter**, una sola familia para el panel, con fallback
`ui-sans-serif, system-ui, sans-serif`. Pesos 400, 500, 600 y 700. La fuente se sirve localmente en el frontend mediante `@fontsource/inter`,
sin un servicio externo de fuentes.

- Escala de texto: 12 px para auxiliares, 14 px para controles y metadatos,
  16 px para cuerpo, 24–32 px para encabezados.
- Espaciado: 4, 8, 12, 16, 24, 32 y 48 px.
- Radios: 8 px en controles, 12 px en cards y diálogos; badges discretos.
- Bordes: 1 px. Sombra opcional mínima: `0 1px 2px rgba(17,17,17,0.03)`.
- Microinteracciones: transiciones de 120–160 ms en color y opacidad. Respetar
  reducción de movimiento; sin rebotes ni desplazamientos decorativos.
- Iconos: Lucide, monocromáticos, normalmente 18–20 px, con grosor consistente.

## Estados

| Estado | Texto / gráfico | Fondo de badge |
|---|---|---|
| Confirmada | `#687887` | `#EDF0F2` |
| Atendida | `#65704E` | `#F0F2EA` |
| Ausente | `#916B3B` | `#F5F0E8` |
| Cancelada por cliente | `#965D54` | `#F6EEEC` |
| Cancelada por local | `#80564D` | `#F1E9E7` |

Usar colores desaturados. El nombre del estado siempre debe acompañar al color.
Las dos cancelaciones conservan etiquetas distintas. No añadir estados ni
modificar sus transiciones. Solo Confirmada permite acciones operativas según
los permisos existentes; los estados finales no muestran acciones.

## Layout y navegación

- Desktop: sidebar izquierda de aproximadamente 256 px, topbar compacta y
  contenido central amplio, sin columnas de cards decorativas.
- Sidebar: marca TuTurnoUy, Agenda y Estadísticas exclusivamente para Owner.
  La estructura podrá alojar Equipo, Servicios, Profesionales, Sucursales y
  Configuración más adelante; no añadir pantallas, enlaces ficticios ni controles
  inactivos ahora.
- Topbar: contexto de página, nombre del usuario y salida/perfil sencillo.
- Tablet: sidebar colapsable. Mobile: drawer con apertura y cierre accesibles;
  no comprimir una sidebar fija. El contenido conserva todo el ancho disponible.

## Componentes previstos

Button, Badge, Card, Input, Select, Dialog, DropdownMenu, Sidebar, Topbar,
PageHeader, StatCard, EmptyState, ErrorState, LoadingSkeleton y ConfirmDialog.
La primera etapa implementa estos componentes en `frontend/src/components/ui/`
y `frontend/src/layouts/`, conservando esta guía como referencia.

Botón primario carbón con texto blanco; secundario blanco con borde suave;
destructivo rojo apagado. Inputs blancos con foco neutro visible. Cards con
borde suave, padding consistente y sombra mínima o sin sombra. Mantener
semántica, navegación por teclado y controles cómodos de tocar.

## Agenda

La pantalla principal de operación usa cards limpias, con esta jerarquía:
horario, cliente, servicio, profesional, sucursal, estado, contacto y notas.

Para Confirmadas, mostrar una acción principal cuando aporte valor y las
secundarias en un DropdownMenu: Marcar atendida, Marcar ausente, Reprogramar y
Cancelar desde el local, únicamente cuando los permisos existentes lo permitan.
No repetir cuatro botones permanentes por card. Conservar la confirmación del
marcado masivo y su alcance actual.

El resumen diario es opcional. Si el bloque técnico lo incluye, mostrar total,
atendidos, ausentes y próximos con StatCards sobrias, reutilizando datos
autorizados, sin introducir nuevas reglas de negocio.

En mobile, cards verticales y controles cómodos; el menú contextual no debe
salirse del viewport.

## Estadísticas

Orden: filtros, métricas principales, gráficos y desgloses. Las métricas
destacadas son reservas, atendidas, ausentes y asistencia, en una fila en desktop
y una grilla adaptada en pantallas pequeñas. Conservar las demás métricas,
fórmulas, filtros y exportación existentes.

El donut muestra el total al centro y una leyenda con estado, cantidad y
porcentaje. Usa Atendidas, Ausentes, ambas cancelaciones y Confirmadas cuando
corresponda; omite segmentos en cero. Debe reutilizar los datos del reporte
filtrado, sin una fuente paralela.

Los gráficos por profesional o servicio, si entran en el alcance técnico, usarán
barras discretas. Sin 3D, gradientes, animaciones exageradas ni paletas saturadas.

Tablas compactas con encabezados claros y separadores suaves. En mobile,
presentar los desgloses como bloques o cards con etiquetas legibles, sin
comprimir una tabla desktop hasta volverla ilegible.

## Fondo atmosférico local

Agenda y Estadísticas comparten una capa de fondo en el layout interno,
mediante `.content-canvas`. El archivo utilizado es
`frontend/src/assets/barbershop-background.webp`; Vite resuelve la referencia
local desde `src/styles.css` y empaqueta el recurso, sin URLs externas.

El pseudo-elemento `::before` presenta la fotografía con `background-size:
cover`, `background-position: left center` en desktop/tablet y `35% center` en
móvil. `grayscale(1)` conserva el blanco y negro incluso si una futura imagen
tiene color. Las capas quedan ancladas al viewport del canvas, sin estirar la
fotografía según la longitud del listado; la topbar sólida queda por encima.

`::after` superpone un único color marfil, `#F7F7F5`, con un gradiente solo de
opacidad. En desktop/tablet el overlay va de **62%** arriba a **64%** a los
320 px del viewport: presencia de imagen **38%** en la parte superior y **36%**
en el resto. En móvil (hasta 700 px), va de **80%** a **82%**: presencia de
**20%** arriba y **18%** en el resto. La fotografía conserva opacidad propia
`1`; su presencia se controla exclusivamente con el overlay.

Se compararon 18%, 22% y 24%, y las posiciones `center center`, `35% center`
y `left center`. Tras esa comparación, se aumentó la presencia a 36% para el canvas y 38% arriba
para responder al ajuste de una atmósfera más oscura, con encuadre izquierdo
para reconocer la silla y el contexto de barbería desde el primer vistazo.
El texto descriptivo del header usa carbón para conservar contraste. Los huecos
entre filtros, métricas y gráfico permanecen abiertos; filtros, cards, métricas
secundarias y fórmulas, tablas y gráficos mantienen sus superficies opacas.
No se aplican gradientes de color ni blur.

La capa ocupa únicamente el canvas de contenido, debajo de sus elementos,
sin capturar eventos. Sidebar, topbar, cards, inputs, menús y modales conservan
sus superficies sólidas. La paleta del donut no se modifica.

Para reemplazar la fotografía, sustituir el archivo local manteniendo la ruta
anterior. Si se cambia el nombre o formato, actualizar solo el `background-image`
de `.content-canvas::before`. La intensidad se ajusta mediante
`--canvas-overlay-opacity`: un valor mayor hace la imagen menos visible. El
header utiliza ese valor menos 0.02. El encuadre se ajusta con
`--canvas-background-position`, con una variante específica para móvil.
Comprobar legibilidad en los cinco anchos de referencia después de reemplazarla.

## Validación visual de la implementación

Revisar cada pantalla en desktop, tablet y mobile: alineación, padding,
jerarquía, tipografía, contraste, densidad y consistencia. Comprobar estados
vacíos, errores, carga, menús y diálogos con teclado. No considerar una pantalla
terminada solo por compilar o aprobar los tests de backend.

No implementar todavía la futura web pública, personalización por negocio ni
páginas fuera del alcance técnico. No hacer commit, push, merge ni deploy sin
una instrucción posterior que lo autorice.
