const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');
const os = require('os');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.static(path.join(__dirname, 'public')));

// Estado del sistema
const taxis = {};       // socketId -> datos del chofer
const solicitudes = {}; // clienteId -> datos de la solicitud

io.on('connection', (socket) => {
    console.log(`[+] Conectado: ${socket.id}`);

    // ── CHOFER ──────────────────────────────────────────────

    socket.on('chofer:registrar', ({ nombre, numero }) => {
        taxis[socket.id] = {
            id: socket.id,
            nombre,
            numero: numero || '',
            disponible: true,
            lat: null,
            lng: null
        };
        console.log(`[CHOFER] Registrado: ${nombre}`);
        io.emit('taxis:actualizar', Object.values(taxis));
        socket.emit('chofer:registrado');
    });

    socket.on('chofer:ubicacion', ({ lat, lng }) => {
        if (taxis[socket.id]) {
            taxis[socket.id].lat = lat;
            taxis[socket.id].lng = lng;
            io.emit('taxis:actualizar', Object.values(taxis));
        }
    });

    socket.on('chofer:disponibilidad', (disponible) => {
        if (taxis[socket.id]) {
            taxis[socket.id].disponible = disponible;
            console.log(`[CHOFER] ${taxis[socket.id].nombre} → ${disponible ? 'Disponible' : 'Ocupado'}`);
            io.emit('taxis:actualizar', Object.values(taxis));
        }
    });

    socket.on('chofer:aceptar', ({ clienteSocketId }) => {
        if (taxis[socket.id]) {
            taxis[socket.id].disponible = false;
            io.emit('taxis:actualizar', Object.values(taxis));
        }
        io.to(clienteSocketId).emit('solicitud:aceptada', {
            choferNombre: taxis[socket.id]?.nombre,
            choferNumero: taxis[socket.id]?.numero
        });
        console.log(`[SOLICITUD] Aceptada por ${taxis[socket.id]?.nombre}`);
    });

    socket.on('chofer:rechazar', ({ clienteSocketId }) => {
        io.to(clienteSocketId).emit('solicitud:rechazada');
        delete solicitudes[clienteSocketId];
        console.log(`[SOLICITUD] Rechazada`);
    });

    socket.on('chofer:completar', () => {
        if (taxis[socket.id]) {
            taxis[socket.id].disponible = true;
            io.emit('taxis:actualizar', Object.values(taxis));
            console.log(`[CHOFER] ${taxis[socket.id].nombre} completó carrera`);
        }
    });

    // ── CLIENTE ─────────────────────────────────────────────

    socket.on('cliente:solicitar', ({ nombre, telefono, lat, lng }) => {
        const disponibles = Object.values(taxis).filter(t => t.disponible);
        if (disponibles.length === 0) {
            socket.emit('solicitud:sinTaxis');
            return;
        }

        // Elegir el taxi más cercano si tiene ubicación, sino el primero disponible
        let elegido = disponibles[0];
        if (lat && lng) {
            elegido = disponibles.reduce((mejor, taxi) => {
                if (!taxi.lat || !taxi.lng) return mejor;
                const distActual = distancia(lat, lng, taxi.lat, taxi.lng);
                const distMejor = mejor.lat
                    ? distancia(lat, lng, mejor.lat, mejor.lng)
                    : Infinity;
                return distActual < distMejor ? taxi : mejor;
            }, disponibles[0]);
        }

        solicitudes[socket.id] = { clienteId: socket.id, nombre, telefono, lat, lng };

        io.to(elegido.id).emit('solicitud:nueva', {
            clienteSocketId: socket.id,
            nombre,
            telefono,
            lat,
            lng
        });

        socket.emit('solicitud:enviada', { taxiNombre: elegido.nombre });
        console.log(`[SOLICITUD] ${nombre} → ${elegido.nombre}`);
    });

    // ── DESCONEXIÓN ─────────────────────────────────────────

    socket.on('disconnect', () => {
        if (taxis[socket.id]) {
            console.log(`[-] Chofer desconectado: ${taxis[socket.id].nombre}`);
            delete taxis[socket.id];
            io.emit('taxis:actualizar', Object.values(taxis));
        }
        delete solicitudes[socket.id];
        console.log(`[-] Desconectado: ${socket.id}`);
    });
});

// Fórmula Haversine para distancia en km
function distancia(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLng = ((lng2 - lng1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function getLocalIP() {
    const interfaces = os.networkInterfaces();
    for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name]) {
            if (iface.family === 'IPv4' && !iface.internal) return iface.address;
        }
    }
    return 'localhost';
}

const PORT = 3000;
server.listen(PORT, '0.0.0.0', () => {
    const ip = getLocalIP();
    console.log('\n========================================');
    console.log('  🚕  TAXI APP — Servidor iniciado');
    console.log('========================================');
    console.log(`  Local:   http://localhost:${PORT}`);
    console.log(`  Red:     http://${ip}:${PORT}`);
    console.log('----------------------------------------');
    console.log(`  Cliente: http://${ip}:${PORT}/cliente.html`);
    console.log(`  Chofer:  http://${ip}:${PORT}/chofer.html`);
    console.log('========================================\n');
});
