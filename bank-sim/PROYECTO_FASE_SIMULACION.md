# Documentación de Avance: Simulador E2E y Robot de Validación Bancaria

## 1. Visión General
Se ha implementado un entorno de simulación completo "End-to-End" (E2E) dentro de Microsoft Excel. Este sistema permite desarrollar y probar la lógica de automatización de validación de tasaciones contra el sistema bancario (IBM 3270) sin necesidad de estar conectado a la red real del banco.

## 2. Instrucciones para Replicar el Flujo E2E

Sigue estos pasos para ejecutar la simulación desde cero:

1.  **Preparación de los Datos:**
    *   Tener la hoja `Tasaciones` con números de préstamo en la columna **Z** (26) y titulares esperados en la columna **AA** (27).
    *   Tener la hoja `SIM_BANCO` con la base de datos de prueba (Préstamo, DNI, Código, Titular, Estado).
2.  **Carga de Módulos (Carpeta `back-sim`):**
    *   Importar los archivos al Editor de VBA (`Alt+F11`).
    *   **CRÍTICO:** El archivo `clsPCOMM.cls` debe estar en la carpeta **Módulos de Clase** y el objeto debe llamarse exactamente `clsPCOMM`.
3.  **Ejecución del Robot:**
    *   Ubicar el módulo `ModRobot`.
    *   Ejecutar la macro `IniciarProcesamientoAutomatico`.
4.  **Flujo Visual:**
    *   El robot activará la hoja `SIM_TERMINAL`.
    *   Cada **5 segundos** verás un paso del proceso:
        *   Navegación al Menú.
        *   Ingreso a la transacción `QSP`.
        *   Tipeo del préstamo registro por registro.
        *   Lectura de la respuesta del banco.
5.  **Verificación de Resultados:**
    *   Al terminar, el robot crea/activa la hoja `REPORTE_FINAL`.
    *   **Verde (VALIDADO OK):** El nombre coincide o está contenido en la respuesta del banco.
    *   **Rojo (DISCREPANCIA / NO ENCONTRADO):** Casos para revisión manual.

## 3. Arquitectura del Sistema
La solución se basa en un diseño desacoplado (Mock Object) que permite cambiar entre el entorno de simulación y el de producción con una sola línea de código (`simulated:=True/False`).

### Componentes Core:
*   **`clsPCOMM` (Clase):** Imita los métodos de IBM PCOMM (`SetText`, `GetText`, `SendKeys`).
*   **`ModTerminal`:** Crea la vista 80x24 de terminal mainframe en Excel.
*   **`ModScreens`:** Backend que procesa comandos y consulta la hoja `SIM_BANCO`.
*   **`ModRobot`:** Orquestador principal del bucle de tasaciones.

## 4. Resultados de la Iteración Actual
*   **Validación Exitosa:** Coincidencias exactas (Maria Flores).
*   **Validación Inteligente:** Coincidencia parcial (Luis Quispe).
*   **Detección de Errores:** Alerta por nombres distintos o préstamos inexistentes.

## 5. Prosimos Pasos
1.  **Integración Real:** Probar con sesiones reales de PCOMM.
2.  **Robustez:** Manejo de pantallas de error del sistema o sesiones caídas.
3.  **Sincronización:** Conectar el reporte final con el Google Sheet de tasaciones.

---
**Estado:** 🟢 Funcional y Documentado
**Fecha:** 23/09/2026
