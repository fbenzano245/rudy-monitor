import re
import json
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
}

SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL")
if not SHEETS_WEBHOOK_URL:
    raise ValueError("Falta la variable SHEETS_WEBHOOK_URL")

def en_horario_operativo(ahora):
    minutos = ahora.hour * 60 + ahora.minute
    return not (minutos >= 90 and minutos < 660)

def scrape_tiempos():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RudyMonitor/1.0)"}
    response = requests.get(RUDY_URL, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    texto_pagina = soup.get_text(" ", strip=True).lower()
    resultados = {}
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M")
    for nombre, keyword in LOCALES.items():
        patron = rf"{keyword}[^(]*takeaway[^(]*\((\d+)\s*mins?\)"
        match = re.search(patron, texto_pagina, re.IGNORECASE)
        if match:
            resultados[nombre] = int(match.group(1))
        elif re.search(rf"{keyword}[^)]*cerrado", texto_pagina, re.IGNORECASE):
            resultados[nombre] = "cerrado"
        else:
            resultados[nombre] = None
    return timestamp, resultados

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
        timeout=25,
    )
    return response.status_code

def main():
    ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    if not en_horario_operativo(ahora):
        print(f"⏸ Fuera de horario ({ahora.strftime('%H:%M')}) — sin acción")
        return
    print(f"🍔 RUDY Monitor — {ahora.strftime('%H:%M')}")
    print("─" * 45)
    timestamp, resultados = scrape_tiempos()
    for local, valor in resultados.items():
        if valor is not None:
            estado = "✅" if valor != "cerrado" and valor <= 20 else "⚠️"
            print(f"  {estado} {local}: {valor}")
        else:
            print(f"  ❌ {local}: no se detectó tiempo")
    print("─" * 45)
    status = enviar_a_sheets(timestamp, resultados)
    print(f"  📊 Sheets: {'OK' if status == 200 else f'Error {status}'}")

if __name__ == "__main__":
    main()
