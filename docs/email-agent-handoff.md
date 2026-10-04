# Traspaso al agente de correo

Trabajá exclusivamente en `/home/carlos/proyectos/tuturnouy-email`, rama `feature/email-delivery`, creada desde `e9118c84e05d13ded5cb64e6417ccd20a10df114`. No hagas merge ni push.

Objetivo:

- Enviar códigos de verificación del invitado con correo texto y HTML.
- Implementar recuperación de contraseña del personal con respuesta indistinguible exista o no la cuenta.
- Configurar SMTP completamente por entorno y agregar Mailpit en `compose.email.yaml`.
- Ante fallos de envío, permanecer en el formulario con un error controlado; no crear una falsa pantalla de éxito.
- No exponer códigos ni tokens en pantalla o logs cuando `DJANGO_DEBUG=False`.
- Probar vencimiento, uso único, fallo de backend y no enumeración de cuentas.
- No implementar Google.

Leé `/home/carlos/proyectos/tuturnouy/docs/parallel-work.md` antes de editar. Ese documento es el contrato de propiedad. En particular, no modifiques `salons/urls.py`, `templates/salons/settings.html`, `static/css/app.css`, `README.md` ni los módulos `salons/team_*`.

Usá el proyecto Compose `tuturnouy_email`, web en `127.0.0.1:8012`, Mailpit en `127.0.0.1:8026` y su propio volumen PostgreSQL. Creá tu propio `.env` local en este worktree. Documentá implementación, variables y pruebas en `docs/email-delivery.md` y actualizá este archivo con los hashes de tus commits y resultados finales.

## Entrega final

- Commit funcional: `8189589db01f8274b492c4539fb3f0e91ac0d778` (`feat: agregar entrega de correo y recuperación de acceso`).
- No se crearon migraciones porque el bloque no cambia modelos.
- Pruebas específicas: 9 aprobadas sobre `test_tuturnouy_email`.
- Suite completa: 61 aprobadas sobre `test_tuturnouy_email`.
- `makemigrations --check --dry-run`: sin cambios.
- Migraciones aplicadas al entorno local aislado y `migrate --check` sin pendientes.
- Aplicación: HTTP 200 en `127.0.0.1:8012`.
- Mailpit: entrega SMTP real comprobada y UI/API disponible en `127.0.0.1:8026`.
- PostgreSQL persistente: volumen `tuturnouy_email_postgres_data`.
- Estado esperado: rama local con commits, sin merge y sin push.

La documentación detallada, variables, decisiones de seguridad, comandos e instrucciones de integración están en `docs/email-delivery.md`.
