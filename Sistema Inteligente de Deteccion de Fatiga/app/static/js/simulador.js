/**
 * ===============================================================================
 * TRANS COPACABANA - SIMULADOR DE RASTREO GPS CON CÁLCULO DE FATIGA
 * Interpola coordenadas entre origen y destino, simula velocidad variable,
 * calcula PERCLOS e Índice de Fatiga (IF), y genera incidentes simulados.
 * ===============================================================================
 */

// Coordenadas de ciudades principales de Bolivia
const COORDS_CIUDADES = {
    "La Paz":      [-16.4883, -68.1408],
    "Cochabamba":  [-17.4042, -66.1583],
    "Santa Cruz":  [-17.7833, -63.1821],
    "Oruro":       [-17.9667, -67.1167],
    "Sucre":       [-19.0333, -65.2627],
    "Potosí":      [-19.5836, -65.7531],
    "Tarija":      [-21.5355, -64.7296],
    "Trinidad":    [-14.8333, -64.9000],
    "Cobija":      [-11.0267, -68.7692]
};

// Puntos intermedios para rutas principales (curvas realistas)
const WAYPOINTS_RUTAS = {
    "Cochabamba->La Paz": [
        [-17.4042, -66.1583], [-17.3800, -66.3000], [-17.3500, -66.5000],
        [-17.2900, -66.7200], [-17.1500, -66.9000], [-17.0000, -67.2000],
        [-16.8000, -67.5000], [-16.6500, -67.8000], [-16.4883, -68.1408]
    ],
    "La Paz->Cochabamba": null, // reverse de la anterior
    "Cochabamba->Santa Cruz": [
        [-17.4042, -66.1583], [-17.4500, -65.8000], [-17.5000, -65.4000],
        [-17.5500, -65.0000], [-17.6200, -64.5000], [-17.7000, -64.0000],
        [-17.7500, -63.5000], [-17.7833, -63.1821]
    ],
    "La Paz->Oruro": [
        [-16.4883, -68.1408], [-16.7000, -67.8000], [-16.9500, -67.5000],
        [-17.2000, -67.3000], [-17.5000, -67.2000], [-17.9667, -67.1167]
    ],
    "Cochabamba->Sucre": [
        [-17.4042, -66.1583], [-17.6000, -66.0000], [-17.8000, -65.8000],
        [-18.0000, -65.6000], [-18.3000, -65.5000], [-18.6000, -65.4000],
        [-19.0333, -65.2627]
    ]
};

let simulationInterval = null;
let simulationStep = 0;
let simulationRoute = [];
let simulationWs = null;

/**
 * Genera una ruta interpolada entre dos ciudades con N puntos
 */
function generarRutaInterpolada(origen, destino, totalPuntos = 60) {
    // Intentar encontrar waypoints predefinidos
    const key = `${origen}->${destino}`;
    const keyReverse = `${destino}->${origen}`;

    let waypoints = null;
    if (WAYPOINTS_RUTAS[key]) {
        waypoints = WAYPOINTS_RUTAS[key];
    } else if (WAYPOINTS_RUTAS[keyReverse]) {
        waypoints = [...WAYPOINTS_RUTAS[keyReverse]].reverse();
    }

    if (!waypoints) {
        // Interpolación lineal simple
        const coordOrigen = COORDS_CIUDADES[origen] || [-17.4042, -66.1583];
        const coordDestino = COORDS_CIUDADES[destino] || [-17.7833, -63.1821];
        waypoints = [coordOrigen, coordDestino];
    }

    // Interpolar entre waypoints para obtener totalPuntos
    const route = [];
    const segmentos = waypoints.length - 1;
    const puntosPerSegmento = Math.floor(totalPuntos / segmentos);

    for (let s = 0; s < segmentos; s++) {
        const start = waypoints[s];
        const end = waypoints[s + 1];
        const nPts = (s === segmentos - 1) ? (totalPuntos - route.length) : puntosPerSegmento;

        for (let i = 0; i < nPts; i++) {
            const t = i / nPts;
            // Agregar pequeña variación aleatoria para simular carretera real
            const jitterLat = (Math.random() - 0.5) * 0.005;
            const jitterLng = (Math.random() - 0.5) * 0.005;
            route.push([
                start[0] + (end[0] - start[0]) * t + jitterLat,
                start[1] + (end[1] - start[1]) * t + jitterLng
            ]);
        }
    }
    // Agregar punto final
    route.push(waypoints[waypoints.length - 1]);
    return route;
}

/**
 * Genera la velocidad simulada según el escenario
 */
function generarVelocidadSimulada(step, totalSteps, escenario) {
    const progreso = step / totalSteps;

    switch (escenario) {
        case 'exceso_velocidad':
            // Velocidad alta frecuentemente
            if (progreso > 0.2 && progreso < 0.8) {
                return 75 + Math.random() * 30; // 75-105 km/h
            }
            return 50 + Math.random() * 25;

        case 'fatiga_critica':
        case 'somnolencia':
        case 'fatiga_progresiva':
            // Velocidad normal con variación
            return 55 + Math.random() * 20;

        case 'mixto':
            // Alternancia entre velocidad normal y exceso
            if (step % 15 < 5 && progreso > 0.3) {
                return 82 + Math.random() * 15;
            }
            return 55 + Math.random() * 20;

        default: // normal
            return 50 + Math.random() * 25; // 50-75 km/h
    }
}

/**
 * Calcula los parámetros de fatiga simulados según el escenario.
 * 
 * Cálculo del Índice de Fatiga (IF):
 * - Se basa en el PERCLOS (% de cierre de ojos en ventana de 60s)
 * - IF = w1 * PERCLOS_norm + w2 * frecuencia_bostezos_norm
 * - Umbral VERDE: IF < 0.50
 * - Umbral AMARILLO: 0.50 <= IF < 0.75 (Somnolencia Preventiva)
 * - Umbral ROJO: IF >= 0.75 (Fatiga Crítica)
 */
function calcularFatigaSimulada(step, totalSteps, escenario) {
    const progreso = step / totalSteps;
    let perclos = 0;
    let indiceFatiga = 0;

    switch (escenario) {
        case 'fatiga_progresiva':
            // PERCLOS sube gradualmente: empieza en 5%, llega a 85% al final
            perclos = 5 + progreso * 80;
            // Agregar ruido
            perclos += (Math.random() - 0.5) * 8;
            perclos = Math.max(0, Math.min(100, perclos));
            // Cálculo IF: ponderación del PERCLOS normalizado
            // IF = 0.7 * (PERCLOS/100) + 0.3 * frecuencia_bostezos
            const freq_bostezos = progreso * 0.8; // sube con el tiempo
            indiceFatiga = 0.7 * (perclos / 100) + 0.3 * freq_bostezos;
            indiceFatiga = Math.max(0, Math.min(1, indiceFatiga));
            break;

        case 'fatiga_critica':
            // Salto inmediato a fatiga crítica para pruebas directas del protocolo PPS
            perclos = 75 + Math.random() * 20;
            indiceFatiga = 0.78 + Math.random() * 0.18;
            break;

        case 'somnolencia':
            // Somnolencia preventiva inmediata (zona amarilla 0.50-0.74)
            perclos = 50 + Math.random() * 18;
            indiceFatiga = 0.55 + Math.random() * 0.15;
            break;

        case 'mixto':
            // Fatiga que va subiendo combinada con exceso de velocidad
            perclos = 5 + progreso * 70 + (Math.random() - 0.5) * 10;
            perclos = Math.max(0, Math.min(100, perclos));
            indiceFatiga = 0.6 * (perclos / 100) + 0.4 * (progreso * 0.9);
            indiceFatiga = Math.max(0, Math.min(1, indiceFatiga));
            break;

        case 'exceso_velocidad':
            // Sin fatiga significativa, solo exceso de velocidad
            perclos = 3 + Math.random() * 8;
            indiceFatiga = 0.05 + Math.random() * 0.10;
            break;

        default: // normal
            perclos = 3 + Math.random() * 7;
            indiceFatiga = 0.03 + Math.random() * 0.08;
            break;
    }

    return {
        perclos: Math.round(perclos * 100) / 100,
        indice_fatiga: Math.round(indiceFatiga * 1000) / 1000
    };
}

/**
 * Inicia la simulación de rastreo GPS
 */
window.iniciarSimulacion = function() {
    const select = document.getElementById('simHojaSelect');
    const option = select.options[select.selectedIndex];

    if (!option || !option.value) {
        alert('Seleccione una Hoja de Ruta para simular.');
        return;
    }

    const hojaId = option.value;
    const origen = option.dataset.origen;
    const destino = option.dataset.destino;
    let conductorId = option.dataset.conductorId;
    if (!conductorId || conductorId.trim() === '') {
        if (typeof fleetData !== 'undefined' && fleetData[hojaId] && fleetData[hojaId].conductor_id) {
            conductorId = fleetData[hojaId].conductor_id;
        } else {
            conductorId = "c0000000-0000-0000-0000-000000000006";
        }
    }
    const escenario = document.getElementById('simScenario').value;
    const speed = parseInt(document.getElementById('simSpeed').value);

    // Generar ruta interpolada
    simulationRoute = generarRutaInterpolada(origen, destino, 80);
    simulationStep = 0;

    // UI Updates
    document.getElementById('btnIniciarSim').disabled = true;
    document.getElementById('btnDetenerSim').disabled = false;
    document.getElementById('simProgress').classList.remove('d-none');
    document.getElementById('simStatusBadge').textContent = 'Simulando...';
    document.getElementById('simStatusBadge').className = 'badge bg-success small';

    // Conectar WebSocket de telemetría
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    simulationWs = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry/${hojaId}`);

    simulationWs.onopen = () => {
        console.log(`[Simulador] WebSocket de telemetría conectado para hoja ${hojaId}`);

        simulationInterval = setInterval(() => {
            if (simulationStep >= simulationRoute.length) {
                detenerSimulacion();
                document.getElementById('simInfoText').textContent = '✅ Simulación completada';
                return;
            }

            const punto = simulationRoute[simulationStep];
            const velocidad = generarVelocidadSimulada(simulationStep, simulationRoute.length, escenario);
            const fatiga = calcularFatigaSimulada(simulationStep, simulationRoute.length, escenario);

            const payload = {
                hoja_de_ruta_id: hojaId,
                conductor_id: conductorId,
                latitud: punto[0],
                longitud: punto[1],
                velocidad_kmh: Math.round(velocidad * 100) / 100,
                timestamp_captura: new Date().toISOString(),
                indice_fatiga_if: fatiga.indice_fatiga,
                perclos_porcentaje: fatiga.perclos
            };

            // Enviar por WebSocket
            if (simulationWs.readyState === WebSocket.OPEN) {
                simulationWs.send(JSON.stringify(payload));
            }

            // Actualizar UI
            const progreso = Math.round((simulationStep / simulationRoute.length) * 100);
            document.getElementById('simProgressBar').style.width = progreso + '%';
            document.getElementById('simInfoText').textContent =
                `Punto ${simulationStep + 1}/${simulationRoute.length} | ${velocidad.toFixed(1)} km/h`;

            // Indicador visual de fatiga
            const fatigaText = document.getElementById('simFatigaText');
            if (fatiga.indice_fatiga >= 0.75) {
                fatigaText.innerHTML = `<span class="text-danger fw-bold">🔴 IF: ${fatiga.indice_fatiga.toFixed(3)} | PERCLOS: ${fatiga.perclos.toFixed(1)}%</span>`;
            } else if (fatiga.indice_fatiga >= 0.50) {
                fatigaText.innerHTML = `<span class="text-warning fw-bold">🟡 IF: ${fatiga.indice_fatiga.toFixed(3)} | PERCLOS: ${fatiga.perclos.toFixed(1)}%</span>`;
            } else {
                fatigaText.innerHTML = `<span class="text-success">🟢 IF: ${fatiga.indice_fatiga.toFixed(3)} | PERCLOS: ${fatiga.perclos.toFixed(1)}%</span>`;
            }

            simulationStep++;
        }, speed);
    };

    simulationWs.onmessage = (event) => {
        try {
            const ack = JSON.parse(event.data);
            if (ack.alerta) {
                console.log(`[Simulador] Alerta del servidor: ${ack.alerta}`);
            }
        } catch(e) {}
    };

    simulationWs.onerror = (error) => {
        console.error('[Simulador] Error WebSocket:', error);
        detenerSimulacion();
    };
};

/**
 * Detiene la simulación en curso
 */
window.detenerSimulacion = function() {
    if (simulationInterval) {
        clearInterval(simulationInterval);
        simulationInterval = null;
    }
    if (simulationWs && simulationWs.readyState === WebSocket.OPEN) {
        simulationWs.close();
    }
    simulationWs = null;

    document.getElementById('btnIniciarSim').disabled = false;
    document.getElementById('btnDetenerSim').disabled = true;
    document.getElementById('simStatusBadge').textContent = 'Detenido';
    document.getElementById('simStatusBadge').className = 'badge bg-secondary small';
};
