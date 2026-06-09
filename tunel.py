# -*- coding: utf-8 -*-
import sys
from pyngrok import ngrok, conf

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("Creando tunel publico hacia http://localhost:3000 ...")
tunnel = ngrok.connect(3000, "http")
url = tunnel.public_url

print("\n========================================")
print("  TUNEL CREADO - Usa estas direcciones")
print("  desde tu telefono (cualquier red, WiFi")
print("  o datos moviles):")
print("========================================")
print(f"  Cliente: {url}/cliente.html")
print(f"  Chofer:  {url}/chofer.html")
print("========================================")
print("\nDeja esta ventana abierta mientras usas la app.")
print("Presiona Ctrl+C para detener el tunel.\n")

try:
    ngrok_process = ngrok.get_ngrok_process()
    ngrok_process.proc.wait()
except KeyboardInterrupt:
    print("Cerrando tunel...")
    ngrok.kill()
