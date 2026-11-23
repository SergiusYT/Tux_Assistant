"""Calcula los resultados de la prueba con usuarios a partir de registro_usuarios.csv.
Tareas: escribir «si», «ayuda» o «no». Escalas: números del 1 al 5.
Uso: python3 validacion/calcular_resultados.py
"""
import csv, os, statistics
ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registro_usuarios.csv")
filas = [f for f in csv.DictReader(open(ruta, encoding="utf-8")) if f.get("T1")]
if not filas:
    raise SystemExit("Aún no hay participantes registrados.")
print(f"Participantes: {len(filas)}")
for t in ("T1", "T2", "T3", "T4", "T5"):
    v = [f[t].strip().lower() for f in filas if f[t].strip()]
    if v:
        print(f"{t}: {sum(x == 'si' for x in v)}/{len(v)} sin ayuda · {sum(x == 'ayuda' for x in v)} con ayuda")
sus = []
for f in filas:
    try:
        r = [int(f[f"SUS{i}"]) for i in range(1, 11)]
    except ValueError:
        continue
    sus.append(2.5 * sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(r)))
if sus:
    print(f"SUS promedio: {statistics.mean(sus):.1f} (mín {min(sus):.0f}, máx {max(sus):.0f})")
for b in ("B1", "B2", "B3", "B4"):
    v = [int(f[b]) for f in filas if f[b].strip().isdigit()]
    if v:
        print(f"{b}: {statistics.mean(v):.1f} / 5")
