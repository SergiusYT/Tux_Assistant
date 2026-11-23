# Prueba con usuarios — Tux Assistant

Duración por persona: 15–20 minutos. Participantes: 5 a 8 personas que estén empezando con Linux o vengan de Windows/macOS (compañeros de otras carreras, primeros semestres, etc.). No se registran nombres: cada persona se identifica como P1, P2…

## Antes de empezar (2 min)

Leer al participante:

> "Vamos a probar un asistente para aprender Linux. No te estamos evaluando a ti, sino al programa. Piensa en voz alta mientras lo usas. Puedes dejar la prueba cuando quieras."

Preguntas de perfil (marcar):

- ¿Qué sistema usas normalmente? Windows / macOS / Linux
- ¿Has usado la terminal de Linux? Nunca / Pocas veces / A menudo
- ¿Cómo resuelves hoy una duda de Linux? Google / Videos / ChatGPT u otra IA / Le pregunto a alguien / Otro

## Tareas (10 min)

El moderador solo observa. Anotar si la persona completa la tarea sin ayuda, con ayuda o no la completa, y el tiempo aproximado.

| # | Tarea | Se considera lograda si… |
|---|---|---|
| T1 | "Averigua con Tux cuánta memoria RAM está usando este computador." | Usa la pregunta rápida o el cuaderno y dice el valor correcto. |
| T2 | "Encontraste en internet el comando `sudo rm -rf /`. Antes de usarlo, pregúntale a Tux si es seguro." | Usa «Analizar comando» o pregunta, y entiende que es peligroso y por qué. |
| T3 | "Pregúntale a Tux cómo dar permiso de ejecución a un script y explícanos qué hace cada parte del comando." | Explica con sus palabras qué hacen `chmod` y `+x`. |
| T4 | "Abre la terminal, escribe `sudo apd install vlc` y mira qué hace Tux." (la vigilancia de terminal debe estar activa) | Entiende que escribió mal `apt` y sabe cuál es el comando correcto. |
| T5 (opcional) | "Crea una ruta de estudio para «empezar desde cero» y completa la primera misión." | Completa al menos un paso de la misión y Tux lo marca como hecho. |

## Encuesta (5 min)

### Parte A — Escala de usabilidad del sistema (SUS)

1 = Totalmente en desacuerdo · 5 = Totalmente de acuerdo

1. Creo que me gustaría usar este asistente con frecuencia.
2. Encontré el asistente innecesariamente complejo.
3. Pensé que era fácil de usar.
4. Creo que necesitaría ayuda de una persona con conocimientos técnicos para usarlo.
5. Las funciones del asistente están bien integradas.
6. Pensé que había demasiada inconsistencia en el asistente.
7. Imagino que la mayoría de las personas aprenderían a usarlo muy rápido.
8. Encontré el asistente muy incómodo de usar.
9. Me sentí muy seguro usando el asistente.
10. Necesité aprender muchas cosas antes de poder usarlo.

Cálculo: ítems impares (respuesta − 1), ítems pares (5 − respuesta), sumar y multiplicar por 2,5. Resultado de 0 a 100; 68 se considera el promedio.

### Parte B — Preguntas específicas (1 a 5)

- B1. Entendí **por qué** funcionaba el comando, no solo qué escribir.
- B2. Confío en que el semáforo me avisa a tiempo de un comando peligroso.
- B3. La ayuda dentro del escritorio es más cómoda que buscar en Google o foros.
- B4. Me sentiría más seguro pasándome a Linux con una herramienta así.

### Parte C — Abiertas

- ¿Qué fue lo más útil?
- ¿Qué te confundió o te molestó?
- ¿Lo usarías? ¿Por qué?

## Registro

Llenar `registro_usuarios.csv` (una fila por participante). Con eso se calculan la tasa de éxito por tarea, el SUS promedio y los promedios de B1–B4 que van al informe.
