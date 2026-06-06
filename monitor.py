import re
import json
import datetime
import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
RUDY_URL = "https://rudyburgers.com"

LOCALES = {
    "Pocitos":        "pocitos",
    "Punta Carretas": "punta carretas",
    "Carrasco":       "carrasco",
    "Centro":         "centro",
}

# Google Sheets — completar con tu webhook de Apps Script
SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyRpBlfxh311Ep5BY9iLVVGhh0iJbXw6Xa70kyEmhtD0EZkye-E372fQpGa9jljfgGt/exec"

# ─────────────────────────────────────────────
# SCRAPING
# ─────────────────────────────────────────────
def scrape_tiempos():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RudyMonitor/1.0)"}
    response = requests.get(RUDY_URL, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    texto_pagina = soup.get_text(" ", strip=True).lower()

    resultados = {}
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    for nombre, keyword in LOCALES.items():
        # Busca el bloque de texto cercano al nombre del local
        patron = rf"{keyword}[^(]*takeaway[^(]*\((\d+)\s*min\)"
        match = re.search(patron, texto_pagina, re.IGNORECASE)

        if match:
            minutos = int(match.group(1))
            resultados[nombre] = minutos
        else:
            resultados[nombre] = None  # No se encontró tiempo

    return timestamp, resultados

# ─────────────────────────────────────────────
# ENVÍO A GOOGLE SHEETS
# ─────────────────────────────────────────────
def enviar_a_sheets(timestamp, resultados):
    fila = {
        "timestamp": timestamp,
        "Pocitos":        resultados.get("Pocitos"),
        "Punta Carretas": resultados.get("Punta Carretas"),
        "Carrasco":       resultados.get("Carrasco"),
        "Centro":         resultados.get("Centro"),
    }

    response = requests.post(
        SHEETS_WEBHOOK_URL,
        json=fila,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    return response.status_code

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(f"🍔 RUDY Monitor — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 45)

    timestamp, resultados = scrape_tiempos()

    for local, minutos in resultados.items():
        if minutos is not None:
            estado = "✅" if minutos <= 20 else "⚠️"
            print(f"  {estado} {local}: {minutos} min")
        else:
            print(f"  ❌ {local}: no se detectó tiempo")

    print("─" * 45)

    if SHEETS_WEBHOOK_URL != "https://script.google.com/macros/s/AKfycbyRpBlfxh311Ep5BY9iLVVGhh0iJbXw6Xa70kyEmhtD0EZkye-E372fQpGa9jljfgGt/exec":
        status = enviar_a_sheets(timestamp, resultados)
        print(f"  📊 Sheets: {'OK' if status == 200 else f'Error {status}'}")
    else:
        print("  ⚠️  Webhook no configurado — datos no enviados a Sheets")
        print(f"  Datos: {json.dumps(resultados, ensure_ascii=False)}")

if __name__ == "__main__":
    main()
