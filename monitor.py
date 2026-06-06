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

SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL") or "https://script.google.com/macros/s/AKfycbyF1fB2WuwoqDsc1MBDxA5qSmXs5sONTCg39CnRjLjgoHmWDN8D6X5vlIXrqVTg4bBp/exec"

def scrape_tiempos():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RudyMonitor/1.0)"}
    response = requests.get(RUDY_URL, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    texto_pagina = soup.get_text(" ", strip=True).lower()
    resultados = {}
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M")
    for nombre, keyword in LOCALES.items():
        patron = rf"{keyword}[^(]*takeaway[^(]*\((\d+)\s*min\)"
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
        timeout=10,
    )
    return response.status_code

def main():
    print(f"🍔 RUDY Monitor — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 45)
    timestamp, resultados = scrape_tiempos()
    for local, minutos in resultados.items():
        if minutos is not None:
            estado = "✅" if minutos != "cerrado" and minutos <= 20 else "⚠️"
            print(f"  {estado} {local}: {minutos}")
        else:
            print(f"  ❌ {local}: no se detectó tiempo")
    print("─" * 45)
    status = enviar_a_sheets(timestamp, resultados)
    print(f"  📊 Sheets: {'OK' if status == 200 else f'Error {status}'}")

if __name__ == "__main__":
    main()
