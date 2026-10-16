# Checklist de implementación: __DISPLAY_NAME__

**Proceso:** `__PROCESS_KEY__`
**Creado:** __CREATED_UTC__

## 1. Contrato y límites

- [ ] Se definió la llave de correlación y su origen.
- [ ] Se definieron entrada, salida, estados terminales e idempotencia.
- [ ] Se identificaron datos que no pueden salir a alertas o registros.
- [ ] El dueño del proceso aprobó el modo seguro y, si aplica, el modo con escritura.

## 2. Preparación manual por plataforma

### Servicio y secretos

- [ ] El servicio tiene identidad, región, variables no sensibles y secreto montado desde el gestor de secretos.
- [ ] La versión de secreto usada por el consumidor coincide con la versión montada por el servicio.
- [ ] Existe una revisión o versión anterior conocida para reversa.

### Almacenamiento y Power Platform

- [ ] Se crearon y validaron las carpetas o contenedores de entrada, control y salida.
- [ ] La solución contiene las referencias de conexión necesarias.
- [ ] La aplicación recibe y muestra la llave de correlación.
- [ ] Los flujos guardados tienen sus desencadenadores, permisos y concurrencia revisados.

### Teams

- [ ] Se creó o eligió el chat o canal corporativo.
- [ ] Se agregó una acción temporal con Flow bot y se exportó solo el identificador opaco a una configuración local ignorada por Git.
- [ ] Los mensajes contienen exclusivamente información operacional permitida.

### Equipo de escritorio

- [ ] Se instalaron dependencias con el mismo Python o runtime que usa PAD.
- [ ] Se prepararon rutas locales, permisos, ubicaciones de confianza y archivo de configuración local.
- [ ] El Desktop Flow recibe la llave de correlación, espera la operación externa y captura su código de salida técnico.
- [ ] Se definió el artefacto estructurado que determina el resultado funcional y la regla para localizarlo por llave de correlación.
- [ ] El resumen para el operador se construye desde ese artefacto; ante fallo técnico no intenta interpretarlo.
- [ ] La aplicación de destino está autenticada y disponible para la prueba segura.

## 3. Consola y despliegue automatizado

- [ ] Se ejecutó el generador o el comando de plan sin realizar cambios.
- [ ] Se recuperaron IDs opacos desde la configuración guardada, no desde texto copiado del diseñador.
- [ ] Se publicó el flujo de inicio y el orquestador mediante el script versionado.
- [ ] Se actualizaron las alertas del flujo que invoca PAD preservando su referencia de conexión de escritorio.
- [ ] Se anotaron commit, fecha, operador y componentes publicados.

## 4. Prueba E2E

- [ ] Se utilizó una llave de correlación nueva.
- [ ] La aplicación registró el caso o lote.
- [ ] El servicio entregó el artefacto de salida esperado.
- [ ] El evento de salida invocó el Desktop Flow una sola vez.
- [ ] El Desktop Flow terminó en modo seguro, con código técnico esperado y artefacto funcional del mismo caso.
- [ ] Teams emitió los eventos de registro, salida, inicio y fin con campos no vacíos; el resumen final coincide con el artefacto funcional.
- [ ] Se actualizó `acceptance-record.md` con ubicaciones de evidencia.

## 5. Cierre o reversa

- [ ] Se documentó la condición de éxito y la siguiente acción del operador.
- [ ] Se documentó qué procesos cierran y cuáles permanecen abiertos de forma intencional al completar la ejecución.
- [ ] Se retiraron configuraciones temporales que ya no son necesarias.
- [ ] Si hubo error, se revirtió el componente afectado y se repitió con una llave nueva.
