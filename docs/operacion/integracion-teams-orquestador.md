> **Estado de cierre (2026-10-13):** el despliegue controlado retiro la accion y la referencia de prueba de Teams de la definicion publicada. Esta guia queda como configuracion para una futura integracion versionada.

﻿# Integración opcional de Microsoft Teams en el orquestador

## Estado actual

La acción de Teams observada en la definición publicada de
`auto-tasacion-orquestar-lote` fue una prueba manual. No forma parte de la
arquitectura definitiva ni del generador
`power-platform/scripts/deploy-mass-flows.ps1`.

La siguiente publicación controlada de ese flujo, una vez liberada la ventana
operativa, sustituirá la definición completa y retirará esa acción y su
referencia de conexión de Teams. No debe reincorporarse mediante una edición
manual aislada del flujo.

## Configuración observada de la prueba

| Aspecto | Valor observado | Uso futuro |
|---|---|---|
| Conector | Microsoft Teams | Crear una referencia de conexión explícita dentro de `autoTasacionCore`. |
| Operación | `PostMessageToConversation` | Usar una acción de publicación equivalente y versionarla en el generador. |
| Identidad que publica | `Flow bot` | Es un bot del flujo, no la cuenta de OneDrive ni una cuenta personal. |
| Ubicación | `Group chat` | La prueba fue un chat grupal; no fue un canal de un equipo. |
| Destinatario | Chat grupal de prueba | El identificador opaco del chat no se versiona. Configurarlo por entorno al habilitar la integración. |
| Mensaje de prueba | `Hola Mundo` | Sustituirlo por una plantilla de estado aprobada. |

La referencia técnica publicada durante la prueba era `shared_teams`. Esa
referencia no está declarada por el generador ni debe tratarse como una
dependencia de la migración OneDrive.

## Cómo reincorporarlo correctamente

1. Definir el evento que se notificará, por ejemplo, resultado terminal del
   lote o fallo técnico. No publicar por cada PDF.
2. Crear una referencia de conexión de Microsoft Teams dentro de
   `autoTasacionCore` con una identidad de servicio aprobada.
3. Guardar el destino del chat como configuración por entorno. No incluir IDs
   de chats, tokens ni destinatarios personales en Git.
4. Añadir al generador la referencia `shared_teams` y la acción en el punto
   elegido del orquestador.
5. Añadir una prueba de definición que compruebe la dependencia, el evento y
   que el flujo continúa funcionando si Teams falla o no está configurado.
6. Exportar una nueva solución Core y validar el flujo publicado antes de
   habilitar notificaciones reales.

## Condición para retirar la prueba actual

La retirada se realizará como parte del próximo despliegue de
`auto-tasacion-orquestar-lote`, no mediante una edición manual. Antes de ello
la carpeta `Controles` debe estar libre de JSON pendientes y debe existir una
ventana operativa confirmada, para no disparar un lote heredado con una nueva
definición.
