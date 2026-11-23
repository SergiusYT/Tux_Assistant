# Resultados de la validación técnica

Modelo: `qwen3:4b-instruct-2507-q4_K_M` · Equipo: 16 hilos, 37.5 GB RAM, GPU: 3415, 4096, NVIDIA GeForce RTX 3050 Laptop GPU

| Prueba | Resultado |
|---|---|
| Semáforo de riesgo (45 comandos) | 45/45 (100%); peligrosos marcados como seguros: 0 |
| Corrección de errores de escritura (20 casos) | 18/20 (90%) en la 1.ª medición → 20/20 (100%) tras el ajuste |
| Tiempo al primer texto (mediana, 8 preguntas) | 0.7 s |
| Tiempo de respuesta completa (mediana / máximo) | 10.1 s / 12.3 s |
| Datos del equipo correctos en la respuesta | 3/3 |
| Misiones generadas válidas y comprobables | 6/8 (pasos promedio 2.3) |
