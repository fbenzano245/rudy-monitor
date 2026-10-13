import re
import json
import time
import datetime
import requests
from bs4 import BeautifulSoup
import os

RUDY_URL = "https://rudyburgers.com"
LOCALES = {
    "Pocitos":        "pocitos",
    "Punta Carretas": "punta carretas",
    "Carrasco":       "carrasco",
    "Centro":         "centro",
    "Prado":          "prado",
}

# Locales que, si no se detectan, NO invalidan el envío: simplemente se omiten.
LOCALES_OPCIONALES = ["Prado"]

SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL")
if not SHEETS_WEBHOOK_URL:
    raise ValueError("Falta la variable SHEETS_WEBHOOK_URL")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RudyMonitor/1.0)"}

def en_horario_operativo(ahora):
    minutos = ahora.hour * 60 + ahora.minute
    return not (minutos >= 90 and minutos < 660)

# ── Lectura de la web ────────────────────────────────────────────────────────

def interpretar_contenido(contenido):
    """'15 min' -> 15 · 'CERRADO' -> 'cerrado' · cualquier otra cosa -> None"""
    c = contenido.strip().lower()
    if "cerrad" in c:
        return "cerrado"
    m = re.search(r"(\d+)", c)
    return int(m.group(1)) if m else None

def interpretar_enlace(href):
    """Respaldo: el enlace de la tienda trae el dato, ej. '.../rudy-burgers-centro-takeaway-15-min_4'."""
    m = re.search(r"takeaway-([^/?#]+?)_\d+", (href or "").lower())
    return interpretar_contenido(m.group(1).replace("-", " ")) if m else None

def leer_por_enlaces(soup):
    """Lee cada local desde su enlace de tienda: 'RUDY Burgers Pocitos - Takeaway (15 min)'.
    Devuelve (valores, por_url): por_url indica los locales que se leyeron desde la dirección del enlace."""
    encontrados, por_url = {}, set()
    for a in soup.select('a[href*="/tiendas/"]'):
        texto = a.get_text(" ", strip=True)
        bajo = texto.lower()
        if "takeaway" not in bajo:
            continue
        valor, desde_url = None, False
        m = re.search(r"\(([^)]*)\)", texto)
        if m:
            valor = interpretar_contenido(m.group(1))
        if valor is None:
            valor = interpretar_enlace(a.get("href"))
            desde_url = valor is not None
        if valor is None:
            continue
        for nombre, keyword in LOCALES.items():
            if keyword in bajo and nombre not in encontrados:
                encontrados[nombre] = valor
                if desde_url:
                    por_url.add(nombre)
    return encontrados, por_url

def leer_por_texto(texto_pagina, keyword):
    """Método de siempre: busca en el texto completo de la página."""
    patron = rf"{keyword}[^(]*takeaway[^(]*\((\d+)"
    match = re.search(patron, texto_pagina, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if re.search(rf"{keyword}[^)]*cerrado", texto_pagina, re.IGNORECASE):
        return "cerrado"
    return None

def contexto_local(texto_pagina, keyword, ancho=140):
    """Fragmento del texto de la página alrededor del local (para diagnosticar)."""
    i = texto_pagina.find(keyword)
    if i < 0:
        return "(el texto de la página no menciona este local)"
    return "…" + texto_pagina[max(0, i - 20): i + ancho] + "…"

def descargar_pagina(intentos=3):
    ultimo_error = None
    for n in range(1, intentos + 1):
        try:
            r = requests.get(RUDY_URL, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r
        except Exception as e:
            ultimo_error = e
            print(f"  ⚠️ Descarga de la web, intento {n}/{intentos}: {e}")
            if n < intentos:
                time.sleep(3)
    raise ultimo_error

def scrape_tiempos():
    response = descargar_pagina()
    soup = BeautifulSoup(response.text, "html.parser")
    texto_pagina = soup.get_text(" ", strip=True).lower()
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M")

    por_enlace, por_url = leer_por_enlaces(soup)
    resultados, metodo = {}, {}
    for nombre, keyword in LOCALES.items():
        if por_enlace.get(nombre) is not None:
            resultados[nombre] = por_enlace[nombre]
            metodo[nombre] = "enlace (desde la dirección)" if nombre in por_url else "enlace"
            continue
        valor = leer_por_texto(texto_pagina, keyword)
        resultados[nombre] = valor
        metodo[nombre] = "texto" if valor is not None else "no detectado"

    diag = {
        "http": response.status_code,
        "bytes": len(response.text),
        "enlaces_tienda": len(por_enlace),
        "metodo": metodo,
        "texto": texto_pagina,
    }
    return timestamp, resultados, diag

# ── Envío a Sheets ───────────────────────────────────────────────────────────

def armar_fila(timestamp, resultados):
    fila = {"type": "log_tiempos_promesa", "timestamp": timestamp}
    for local in LOCALES:
        valor = resultados.get(local)
        # Un local opcional que no se detectó se omite del envío (no se manda null)
        if valor is None and local in LOCALES_OPCIONALES:
            continue
        fila[local] = valor
    return fila

def enviar_a_sheets(timestamp, resultados, intentos=3):
    """Devuelve (ok, detalle). Reintenta si Apps Script responde algo que no es el JSON esperado."""
    fila = armar_fila(timestamp, resultados)
    detalle = ""
    for n in range(1, intentos + 1):
        try:
            r = requests.post(
                SHEETS_WEBHOOK_URL,
                json=fila,
                headers={"Content-Type": "application/json"},
                timeout=25,
            )
            cuerpo = (r.text or "")[:200].replace("\n", " ")
            detalle = f"HTTP {r.status_code} · {cuerpo}"
            try:
                ok = r.status_code == 200 and json.loads(r.text).get("status") == "ok"
            except Exception:
                ok = False   # no vino el JSON esperado (ej. una página de error de Google)
            if ok:
                return True, detalle
            print(f"  ⚠️ Envío a Sheets, intento {n}/{intentos}: {detalle}")
        except Exception as e:
            detalle = f"excepción: {e}"
            print(f"  ⚠️ Envío a Sheets, intento {n}/{intentos}: {detalle}")
        if n < intentos:
            time.sleep(4)
    return False, detalle

# ── Principal ────────────────────────────────────────────────────────────────

def main():
    ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    if not en_horario_operativo(ahora):
        print(f"⏸ Fuera de horario ({ahora.strftime('%H:%M')}) — sin acción")
        return
    print(f"🍔 RUDY Monitor — {ahora.strftime('%H:%M')}")
    print("─" * 45)
    timestamp, resultados, diag = scrape_tiempos()
    print(f"  🌐 Web: HTTP {diag['http']} · {diag['bytes']} bytes · {diag['enlaces_tienda']} enlaces de tienda leídos")
    for local, valor in resultados.items():
        if valor is not None:
            estado = "✅" if valor != "cerrado" and valor <= 20 else "⚠️"
            print(f"  {estado} {local}: {valor}   (leído por {diag['metodo'][local]})")
        else:
            print(f"  ❌ {local}: no se detectó tiempo")
    print("─" * 45)

    faltan = [l for l, v in resultados.items() if v is None and l not in LOCALES_OPCIONALES]
    if faltan:
        print(f"  🚨 CICLO NO ENVIADO: no se detectó el tiempo de {', '.join(faltan)}.")
        print("  Así se veía la página alrededor de cada uno:")
        for l in faltan:
            print(f"    · {l}: {contexto_local(diag['texto'], LOCALES[l])}")
        return

    ok, detalle = enviar_a_sheets(timestamp, resultados)
    print(f"  📊 Sheets: {'OK' if ok else 'ERROR'} — {detalle}")

if __name__ == "__main__":
    main()
