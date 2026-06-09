# -*- coding: utf-8 -*-
import sys
import os
import math
import datetime
import json
import threading
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import socket as sock
from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit
from pywebpush import webpush, WebPushException

VAPID_PRIVATE_KEY = """-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIP3Rh9H/CxIfKskSN2lcmvgS90SuoWLIjrxFsITFEtN8oAoGCCqGSM49
AwEHoUQDQgAESMzfjzY1k/UiZq5EhMjXZYaEsd5yqzXudnqeyffezyupl1buIsfd
67dLWXpFwUsp56VQxBfIgAnRbzvI71viYA==
-----END EC PRIVATE KEY-----"""
VAPID_PUBLIC_KEY = "BEjM3482NZP1ImauRITI12WGhLHecqs17nZ6nsn33s8rqZdW7iLH3eu3S1l6RcFLKeelUMQXyIAJ0W87yO9b4mA"
VAPID_EMAIL = "mailto:washingtonmontoya3@gmail.com"

app = Flask(__name__, static_folder='public')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

ADMIN_PASSWORD = 'taxi2024'
BLOQUEADOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bloqueados.json')

def cargar_bloqueados():
    try:
        with open(BLOQUEADOS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    except Exception:
        return set()

def guardar_bloqueados():
    try:
        with open(BLOQUEADOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(bloqueados), f, ensure_ascii=False)
    except Exception as e:
        print(f'[ADMIN] No se pudo guardar bloqueados: {e}')

# Estado del sistema en memoria
taxis = {}         # sid -> dict con datos del chofer
solicitudes = {}   # clienteSid -> dict con datos del cliente
historial = []     # lista de carreras completadas
suscripciones = {} # sid -> push subscription dict
bloqueados = cargar_bloqueados()


def get_local_ip():
    try:
        s = sock.socket(sock.AF_INET, sock.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'localhost'


def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Rutas HTML ──────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('public', 'cliente.html')

@app.route('/api/historial')
def api_historial():
    return jsonify(historial)

@app.route('/api/vapid-public-key')
def vapid_public_key():
    return jsonify({'key': VAPID_PUBLIC_KEY})

@app.route('/admin')
def admin_page():
    pwd = request.args.get('pwd', '')
    if pwd != ADMIN_PASSWORD:
        return '<h2 style="font-family:sans-serif;padding:40px">Acceso denegado.<br><small>Agrega <b>?pwd=tu_contrasena</b> a la URL</small></h2>', 403
    return send_from_directory('public', 'admin.html')

@app.route('/api/admin/estado')
def admin_estado():
    if request.args.get('pwd') != ADMIN_PASSWORD:
        return jsonify({'error': 'No autorizado'}), 403
    return jsonify({'taxis': list(taxis.values()), 'bloqueados': sorted(list(bloqueados))})

@app.route('/api/admin/bloquear', methods=['POST'])
def admin_bloquear():
    if request.args.get('pwd') != ADMIN_PASSWORD:
        return jsonify({'error': 'No autorizado'}), 403
    nombre = request.json.get('nombre', '').lower().strip()
    if not nombre:
        return jsonify({'error': 'Nombre vacio'}), 400
    bloqueados.add(nombre)
    guardar_bloqueados()
    # Expulsar al chofer si está conectado ahora
    for sid, t in list(taxis.items()):
        if t['nombre'].lower().strip() == nombre:
            socketio.emit('chofer:bloqueado', to=sid)
            del taxis[sid]
    socketio.emit('taxis:actualizar', list(taxis.values()))
    print(f'[ADMIN] Bloqueado: {nombre}')
    return jsonify({'ok': True, 'bloqueados': sorted(list(bloqueados))})

@app.route('/api/admin/desbloquear', methods=['POST'])
def admin_desbloquear():
    if request.args.get('pwd') != ADMIN_PASSWORD:
        return jsonify({'error': 'No autorizado'}), 403
    nombre = request.json.get('nombre', '').lower().strip()
    bloqueados.discard(nombre)
    guardar_bloqueados()
    print(f'[ADMIN] Desbloqueado: {nombre}')
    return jsonify({'ok': True, 'bloqueados': sorted(list(bloqueados))})

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('public', filename)


# ── Eventos Socket.IO ───────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print(f'[+] Conectado: {request.sid}')
    # Enviar lista actual de taxis al nuevo cliente
    emit('taxis:actualizar', list(taxis.values()))


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in taxis:
        print(f'[-] Chofer desconectado: {taxis[sid]["nombre"]}')
        del taxis[sid]
        socketio.emit('taxis:actualizar', list(taxis.values()))
    if sid in solicitudes:
        del solicitudes[sid]
    suscripciones.pop(sid, None)
    print(f'[-] Desconectado: {sid}')


# ── CHOFER ──────────────────────────────────────────────────

@socketio.on('chofer:registrar')
def chofer_registrar(data):
    sid = request.sid
    nombre = data.get('nombre', 'Chofer')
    if nombre.lower().strip() in bloqueados:
        emit('chofer:bloqueado')
        print(f'[ADMIN] Intento de acceso bloqueado: {nombre}')
        return
    taxis[sid] = {
        'id': sid,
        'nombre': nombre,
        'numero': data.get('numero', ''),
        'disponible': True,
        'lat': None,
        'lng': None,
    }
    print(f'[CHOFER] Registrado: {taxis[sid]["nombre"]}')
    socketio.emit('taxis:actualizar', list(taxis.values()))
    emit('chofer:registrado')


@socketio.on('chofer:ubicacion')
def chofer_ubicacion(data):
    sid = request.sid
    if sid in taxis:
        taxis[sid]['lat'] = data.get('lat')
        taxis[sid]['lng'] = data.get('lng')
        socketio.emit('taxis:actualizar', list(taxis.values()))


@socketio.on('chofer:disponibilidad')
def chofer_disponibilidad(disponible):
    sid = request.sid
    if sid in taxis:
        taxis[sid]['disponible'] = disponible
        estado = 'Disponible' if disponible else 'Ocupado'
        print(f'[CHOFER] {taxis[sid]["nombre"]} -> {estado}')
        socketio.emit('taxis:actualizar', list(taxis.values()))


@socketio.on('chofer:aceptar')
def chofer_aceptar(data):
    sid = request.sid
    cliente_sid = data.get('clienteSocketId')
    if sid in taxis:
        taxis[sid]['disponible'] = False
        socketio.emit('taxis:actualizar', list(taxis.values()))
    socketio.emit('solicitud:aceptada', {
        'choferNombre': taxis.get(sid, {}).get('nombre', ''),
        'choferNumero': taxis.get(sid, {}).get('numero', ''),
    }, to=cliente_sid)
    # Guardar cliente_sid para notificarle al completar la carrera
    if sid in solicitudes:
        solicitudes[sid]['clienteSocketId'] = cliente_sid
    print(f'[SOLICITUD] Aceptada por {taxis.get(sid, {}).get("nombre", "")}')


@socketio.on('chofer:rechazar')
def chofer_rechazar(data):
    cliente_sid = data.get('clienteSocketId')
    socketio.emit('solicitud:rechazada', to=cliente_sid)
    solicitudes.pop(cliente_sid, None)
    print('[SOLICITUD] Rechazada')


@socketio.on('chofer:completar')
def chofer_completar():
    sid = request.sid
    if sid in taxis:
        nombre_chofer = taxis[sid]['nombre']
        taxis[sid]['disponible'] = True
        socketio.emit('taxis:actualizar', list(taxis.values()))
        print(f'[CHOFER] {nombre_chofer} completo carrera')

        # Avisar al cliente que la carrera terminó
        sol = solicitudes.get(sid) or {}
        cliente_sid = sol.get('clienteSocketId')
        if cliente_sid:
            socketio.emit('carrera:completada', to=cliente_sid)

        # Guardar en historial
        ahora = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
        entrada = {
            'fecha': ahora,
            'chofer': nombre_chofer,
            'cliente': sol.get('nombre', 'Desconocido'),
            'telefono': sol.get('telefono', '-'),
        }
        historial.insert(0, entrada)
        # Máximo 100 registros
        if len(historial) > 100:
            historial.pop()
        socketio.emit('historial:actualizar', historial)


@socketio.on('emergencia:activar')
def emergencia_activar(data):
    sid = request.sid
    nombre = data.get('nombre', 'Alguien')
    tipo = data.get('tipo', 'usuario')
    lat = data.get('lat')
    lng = data.get('lng')
    print(f'[EMERGENCIA] {nombre} ({tipo}) activo boton de auxilio')
    socketio.emit('emergencia:alerta', {
        'nombre': nombre,
        'tipo': tipo,
        'lat': lat,
        'lng': lng,
    })


@socketio.on('chofer:suscribir')
def chofer_suscribir(data):
    sid = request.sid
    suscripciones[sid] = data
    print(f'[PUSH] Suscripcion guardada para {taxis.get(sid, {}).get("nombre", sid)}')


def enviar_push(sid, titulo, cuerpo):
    sub = suscripciones.get(sid)
    if not sub:
        return
    def _send():
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({'title': titulo, 'body': cuerpo}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={'sub': VAPID_EMAIL},
            )
        except WebPushException as e:
            print(f'[PUSH] Error enviando notificacion: {e}')
        except Exception as e:
            print(f'[PUSH] Error inesperado: {e}')
    threading.Thread(target=_send, daemon=True).start()


@socketio.on('chofer:terminar_turno')
def chofer_terminar_turno():
    sid = request.sid
    if sid in taxis:
        print(f'[CHOFER] {taxis[sid]["nombre"]} termino turno')
        del taxis[sid]
        socketio.emit('taxis:actualizar', list(taxis.values()))
    emit('chofer:turno_terminado')


@socketio.on('historial:limpiar')
def historial_limpiar():
    historial.clear()
    socketio.emit('historial:actualizar', historial)
    print('[HISTORIAL] Limpiado')


# ── CLIENTE ─────────────────────────────────────────────────

@socketio.on('cliente:solicitar')
def cliente_solicitar(data):
    sid = request.sid
    disponibles = [t for t in taxis.values() if t['disponible']]

    if not disponibles:
        emit('solicitud:sinTaxis')
        return

    lat = data.get('lat')
    lng = data.get('lng')

    elegido = disponibles[0]
    if lat and lng:
        def distancia_a(taxi):
            if taxi['lat'] and taxi['lng']:
                return haversine(lat, lng, taxi['lat'], taxi['lng'])
            return float('inf')
        elegido = min(disponibles, key=distancia_a)

    solicitudes[sid] = {
        'clienteId': sid,
        'nombre': data.get('nombre'),
        'telefono': data.get('telefono'),
        'lat': lat,
        'lng': lng,
    }
    # Guardar la solicitud también asociada al chofer para el historial
    solicitudes[elegido['id']] = solicitudes[sid]

    socketio.emit('solicitud:nueva', {
        'clienteSocketId': sid,
        'nombre': data.get('nombre'),
        'telefono': data.get('telefono'),
        'lat': lat,
        'lng': lng,
    }, to=elegido['id'])

    # Push notification al chofer por si la app está en segundo plano
    nombre_cliente = data.get('nombre') or 'un cliente'
    enviar_push(elegido['id'], 'Nueva solicitud de carrera', f'{nombre_cliente} necesita un taxi')

    emit('solicitud:enviada', {'taxiNombre': elegido['nombre']})
    print(f'[SOLICITUD] {data.get("nombre")} -> {elegido["nombre"]}')


# ── Inicio ──────────────────────────────────────────────────

if __name__ == '__main__':
    import os
    ip = get_local_ip()
    port = int(os.environ.get('PORT', 3000))
    print('\n========================================')
    print('  TAXI APP - Servidor iniciado')
    print('========================================')
    print(f'  Local:   http://localhost:{port}')
    print(f'  Red:     http://{ip}:{port}')
    print('----------------------------------------')
    print(f'  Cliente: http://{ip}:{port}/cliente.html')
    print(f'  Chofer:  http://{ip}:{port}/chofer.html')
    print(f'  Historial: http://{ip}:{port}/historial.html')
    print('========================================\n')
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)
