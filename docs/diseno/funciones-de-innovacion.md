# Tux Assistant — funciones de innovación (diseño)

## Por qué
Proyecto de Innovación Tecnológica (U. El Bosque). Tux debe pasar de "responder preguntas" a
**enseñar Linux de forma guiada y proactiva**, respetando: explicar antes de automatizar,
transparencia, autonomía progresiva, mínimo privilegio (OWASP: nada de agencia excesiva).

## Metas
1. **Vigilancia de terminal**: cuando un comando falla en bash, Tux aparece y explica el error.
2. **Semáforo de riesgo**: analiza un comando antes de ejecutarlo (🟢 seguro / 🟡 cuidado / 🔴 peligroso),
   parte por parte. Reglas fijas en código, no IA.
3. **Misiones verificadas**: retos prácticos que Tux comprueba con código; completar misiones sube el nivel.
4. **Planes de estudio por tema** (enfoque C, mixto): lecciones y misiones fijas, curadas; la IA solo
   elige qué temas, en qué orden y a qué ritmo según la meta y nivel del usuario. Cada plan es un chat
   propio que se guarda y se retoma.

## No-metas / anti-metas
- Tux nunca ejecuta comandos que modifiquen el sistema ni corrige el error por el usuario.
- No registrar todo lo que el usuario escribe en la terminal (solo el último comando fallido).
- Nada pesado: almacenamiento mínimo.

## Restricciones
- Almacenamiento muy ligero: JSON compacto en `~/.config/tux-assistant/`; chats con máximo 150 mensajes;
  no se guarda información del PC (se mide en cada pregunta). Archivo de error < 1 KB, sobrescrito.
- Modelo local pequeño (qwen3 4B): nada que dependa de que la IA invente datos verificables.
- Misiones dentro de `~/tux-practica/` para no tocar archivos reales del usuario.

## Enfoques considerados
- Planes: A) rutas fijas (fiable, poco personal), B) IA inventa el plan (personal, frágil con 4B),
  **C) mixto (elegido)**: catálogo fijo + IA ordena/selecciona según meta.
- Guardado: **JSON (elegido)** vs SQLite (sin ventaja a este tamaño, menos transparente).
- UI de chats: **selector compacto arriba (elegido)** vs barra lateral (ensancha la ventana, invasiva).
- Terminal: **hook `PROMPT_COMMAND` en `~/.bashrc` (elegido)**, con marcadores para poder quitarlo;
  bash no expone stderr, así que se usa código de salida + re-ejecución SOLO si el comando pasa la
  lista blanca de solo lectura + `command-not-found` de Ubuntu para el código 127.

## Diseño
- `riesgo.py`: `analizar(cmd) -> {nivel, motivos, partes}`. Se usa en el chat ("analiza …", "/riesgo …",
  "¿es seguro …?", mensajes que empiezan con `$ `) y como insignia en las tarjetas de comando.
- `terminal.py`: instalar/quitar hook, leer último error, explicación rápida por código de salida.
  Tux sondea el archivo cada 1 s; burbuja con explicación instantánea + enlace "Explícame más ›" (IA).
  Se activa con «activar terminal» / se quita con «desactivar terminal».
- `aprendizaje.py`: catálogo de temas/lecciones/misiones, verificaciones (existe, permisos, contiene,
  ejecutable, instalado, respuesta comparada con dato real), progreso, planes y chats en JSON.
  Subida de nivel automática: 4 misiones → intermedio, 10 → avanzado (se avisa; el usuario puede cambiarlo).
- `main.py`: selector de chats, línea de progreso del plan, flujo «empezar/siguiente/listo»,
  contexto de la lección para la IA, vigilancia de terminal.

## Decisiones del implementador
Nombres de temas y lecciones, textos de misiones, umbrales de subida de nivel, intervalo de sondeo.
