/**
 * ===============================================================================
 * TRANS COPACABANA - CENTRO DE MONITOREO Y CONTROL EN TIEMPO REAL
 * LEAFLET.JS + WEBSOCKETS + PROTOCOLO DE PARADA SEGURA (PPS)
 * ===============================================================================
 */

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initWebSocket();
    cargarFlotaInicial();
});

let map;
const markers = {};       // hoja_id -> L.marker
const polylines = {};     // hoja_id -> L.polyline
const fleetData = {};     // hoja_id -> BusSnapshot
let activeIncidentes = {}; // incidente_id -> data

// Variables para grabación de audio PPS
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// 1. Inicialización del Mapa Leaflet
function initMap() {
    map = L.map('mapContainer').setView([-17.1, -66.6], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors | Trans Copacabana'
    }).addTo(map);
}

// 2. Generador de Iconos Dinámicos según Semáforo de Riesgo
function createBusIcon(disco, nivelRiesgo, estadoHoja) {
    let colorCls = 'marker-verde';
    if (nivelRiesgo === 'GRIS' || estadoHoja === 'AUTORIZADA' || estadoHoja === 'FINALIZADA') {
        colorCls = 'marker-gris';
    } else if (nivelRiesgo === 'AMARILLO') {
        colorCls = 'marker-amarillo';
    } else if (nivelRiesgo === 'ROJO') {
        colorCls = 'marker-rojo';
    }

    const htmlContent = `
        <div class="custom-bus-marker ${colorCls}">
            <i class="fa-solid fa-bus"></i>
            <span class="marker-disco">${disco || '--'}</span>
        </div>
    `;
    return L.divIcon({
        className: 'tc-bus-div-icon',
        html: htmlContent,
        iconSize: [40, 40],
        iconAnchor: [20, 20],
        popupAnchor: [0, -22]
    });
}

// 3. Conexión WebSocket al Servidor de Monitoreo
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
    const socket = new WebSocket(wsUrl);
    const statusBadge = document.getElementById('wsConnectionStatus');

    socket.onopen = () => {
        console.log('[WebSocket] Conectado al Centro de Control.');
        if (statusBadge) {
            statusBadge.className = 'badge bg-success';
            statusBadge.innerHTML = '<i class="fa-solid fa-circle-dot me-1"></i> EN VIVO';
        }
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWebSocketMessage(msg);
        } catch (err) {
            console.error('[WebSocket] Error al procesar mensaje:', err);
        }
    };

    socket.onclose = () => {
        console.warn('[WebSocket] Conexión cerrada. Reintentando en 3s...');
        if (statusBadge) {
            statusBadge.className = 'badge bg-danger';
            statusBadge.innerHTML = '<i class="fa-solid fa-circle-xmark me-1"></i> DESCONECTADO';
        }
        setTimeout(initWebSocket, 3000);
    };
}

// 4. Carga Inicial de Flota
function cargarFlotaInicial() {
    fetch('/api/v1/telemetria/monitoreo-flota')
        .then(res => res.json())
        .then(buses => {
            if (Array.isArray(buses)) {
                buses.forEach(b => updateBusOnMap(b));

                // Sincronizar dinámicamente las hojas de ruta en el combobox del simulador
                buses.forEach(b => sincronizarHojaEnSelect(b));
            }
        })
        .catch(err => console.warn('[Monitoreo] Error al sincronizar flota inicial:', err));

    fetch('/api/v1/incidentes/activos')
        .then(res => res.json())
        .then(incidentes => {
            if (Array.isArray(incidentes)) {
                incidentes.forEach(inc => {
                    activeIncidentes[inc.id] = {
                        incidente_id: inc.id,
                        hoja_de_ruta_id: inc.hoja_de_ruta_id,
                        bus_disco: inc.hoja_de_ruta && inc.hoja_de_ruta.vehiculo ? inc.hoja_de_ruta.vehiculo.numero_interno : '--',
                        bus_placa: inc.hoja_de_ruta && inc.hoja_de_ruta.vehiculo ? inc.hoja_de_ruta.vehiculo.placa : '',
                        conductor: inc.conductor && inc.conductor.usuario ? `${inc.conductor.usuario.nombre} ${inc.conductor.usuario.apellido}` : 'Conductor',
                        velocidad: inc.velocidad_instantanea || 0,
                        nivel_riesgo: inc.nivel_riesgo,
                        alerta: inc.tipo_incidente,
                        indice_fatiga: inc.indice_fatiga_if,
                        perclos: inc.perclos_porcentaje,
                        timestamp: inc.timestamp_evento
                    };
                });
                renderIncidentesList();
                updateFleetCounters();
            }
        })
        .catch(() => {});
}

// 5. Despachador de Mensajes en Tiempo Real
function handleWebSocketMessage(msg) {
    if (msg.tipo_evento === 'SNAPSHOT_INICIAL') {
        if (Array.isArray(msg.buses)) {
            msg.buses.forEach(b => updateBusOnMap(b));
        }
    } else if (msg.tipo_evento === 'TELEMETRIA_ACTUALIZADA' || msg.tipo_evento === 'HOJA_AUTORIZADA') {
        updateBusOnMap(msg.data);
    } else if (msg.tipo_evento === 'VIAJE_INICIADO') {
        if (fleetData[msg.hoja_de_ruta_id]) {
            fleetData[msg.hoja_de_ruta_id].nivel_riesgo = 'VERDE';
            fleetData[msg.hoja_de_ruta_id].estado_hoja = 'EN_TRANSITO';
            updateBusOnMap(fleetData[msg.hoja_de_ruta_id]);
        }
    } else if (msg.tipo_evento === 'VIAJE_FINALIZADO') {
        if (fleetData[msg.hoja_de_ruta_id]) {
            fleetData[msg.hoja_de_ruta_id].nivel_riesgo = 'GRIS';
            fleetData[msg.hoja_de_ruta_id].estado_hoja = 'FINALIZADA';
            updateBusOnMap(fleetData[msg.hoja_de_ruta_id]);
        }
    } else if (msg.tipo_evento === 'INCIDENTE_ALERTA') {
        handleIncidenteAlerta(msg);
    } else if (msg.tipo_evento === 'INCIDENTE_ATENDIDO') {
        handleIncidenteAtendido(msg);
    }
}

// 6. Actualización Reactiva de Marcadores
function updateBusOnMap(data) {
    if (!data || !data.hoja_de_ruta_id) return;
    const hojaId = data.hoja_de_ruta_id;
    fleetData[hojaId] = Object.assign({}, fleetData[hojaId] || {}, data);
    sincronizarHojaEnSelect(fleetData[hojaId]);

    const lat = data.latitud;
    const lng = data.longitud;
    if (lat === null || lat === undefined || lng === null || lng === undefined) return;
    const latlng = [lat, lng];

    const busDisco = data.bus_numero_interno || data.bus_disco || '--';
    const nivelRiesgo = data.nivel_riesgo;
    const estadoHoja = data.estado_hoja;

    if (!markers[hojaId]) {
        const marker = L.marker(latlng, {
            icon: createBusIcon(busDisco, nivelRiesgo, estadoHoja)
        }).addTo(map);
        marker.bindPopup(buildPopupHtml(fleetData[hojaId]));
        markers[hojaId] = marker;
        polylines[hojaId] = L.polyline([latlng], {
            color: '#C8102E', weight: 4, opacity: 0.7
        }).addTo(map);

        if (estadoHoja === 'EN_TRANSITO') {
            fetch(`/api/v1/telemetria/historial/${hojaId}`)
                .then(res => res.json())
                .then(geo => {
                    if (geo.features && geo.features[0]) {
                        const coords = geo.features[0].geometry.coordinates.map(c => [c[1], c[0]]);
                        if (coords.length > 0) polylines[hojaId].setLatLngs(coords);
                    }
                })
                .catch(() => {});
        }
    } else {
        const marker = markers[hojaId];
        marker.setLatLng(latlng);
        marker.setIcon(createBusIcon(busDisco, nivelRiesgo, estadoHoja));
        marker.setPopupContent(buildPopupHtml(fleetData[hojaId]));
        if (estadoHoja === 'EN_TRANSITO' && (data.velocidad_kmh > 0 || polylines[hojaId].getLatLngs().length === 0)) {
            polylines[hojaId].addLatLng(latlng);
        }
    }
    renderFleetList();
    updateFleetCounters();
}

// 7. Alerta de Incidentes
function handleIncidenteAlerta(msg) {
    const data = msg.data;
    const incId = msg.incidente_id;
    activeIncidentes[incId] = {
        incidente_id: incId,
        hoja_de_ruta_id: data.hoja_de_ruta_id,
        bus_disco: data.bus_numero_interno || data.bus_disco || '--',
        bus_placa: data.bus_placa || '',
        conductor: data.conductor || 'Conductor',
        velocidad: data.velocidad_kmh,
        nivel_riesgo: data.nivel_riesgo || msg.nivel_riesgo,
        alerta: data.alerta_mensaje,
        tipo_incidente: msg.tipo_incidente,
        indice_fatiga: msg.indice_fatiga || data.indice_fatiga,
        perclos: msg.perclos || data.perclos,
        timestamp: data.timestamp
    };
    if (markers[data.hoja_de_ruta_id]) {
        markers[data.hoja_de_ruta_id].openPopup();
    }
    // Reproducir sonido de alarma según nivel de riesgo
    if (msg.nivel_riesgo === 'ROJO') {
        playAlertSound('critical');
    } else {
        playAlertSound('warning');
    }
    renderIncidentesList();
    updateFleetCounters();
}

// 8. Atención de Incidentes
function handleIncidenteAtendido(msg) {
    const incId = msg.incidente_id;
    if (activeIncidentes[incId]) {
        delete activeIncidentes[incId];
    }
    renderIncidentesList();
    updateFleetCounters();
}

// 9. Construcción de HTML para Popup con foto de bus
function buildPopupHtml(data) {
    let badgeRiesgo = '<span class="badge bg-secondary">EN TERMINAL (AUTORIZADA)</span>';
    if (data.estado_hoja === 'FINALIZADA') {
        badgeRiesgo = '<span class="badge bg-secondary">VIAJE FINALIZADO</span>';
    } else if (data.estado_hoja === 'EN_TRANSITO') {
        if (data.nivel_riesgo === 'AMARILLO') {
            badgeRiesgo = '<span class="badge bg-warning text-dark">ADVERTENCIA</span>';
        } else if (data.nivel_riesgo === 'ROJO') {
            badgeRiesgo = '<span class="badge bg-danger">PARADA CRÍTICA</span>';
        } else {
            badgeRiesgo = '<span class="badge bg-success">EN RUTA (&le; 80 km/h)</span>';
        }
    }

    let alertaHtml = '';
    if (data.alerta_mensaje) {
        const alertCls = data.nivel_riesgo === 'ROJO' ? 'alert-danger' : 'alert-warning';
        alertaHtml = `
            <div class="alert ${alertCls} py-1 px-2 small mt-2 mb-1">
                <i class="fa-solid fa-triangle-exclamation me-1"></i>
                ${data.alerta_mensaje}
            </div>
        `;
    }

    // Datos de fatiga si existen
    let fatigaHtml = '';
    if (data.indice_fatiga !== null && data.indice_fatiga !== undefined) {
        const ifVal = parseFloat(data.indice_fatiga);
        const percVal = data.perclos !== null && data.perclos !== undefined ? parseFloat(data.perclos) : 0;
        let barColor = ifVal >= 0.75 ? '#dc2626' : ifVal >= 0.50 ? '#ca8a04' : '#16a34a';
        fatigaHtml = `
            <div class="mt-1 mb-1 small">
                <strong>Índice Fatiga:</strong>
                <div class="progress mt-1" style="height: 8px;">
                    <div class="progress-bar" style="width: ${ifVal * 100}%; background-color: ${barColor}"></div>
                </div>
                <div class="d-flex justify-content-between">
                    <span>IF: <strong>${ifVal.toFixed(2)}</strong></span>
                    <span>PERCLOS: <strong>${percVal.toFixed(1)}%</strong></span>
                </div>
            </div>
        `;
    }

    // Foto del bus si existe
    let fotoHtml = '';
    if (data.foto_bus) {
        fotoHtml = `<img src="${data.foto_bus}" alt="Bus" class="img-fluid rounded mb-2" style="max-height: 80px; width: 100%; object-fit: cover;">`;
    }

    const busNum = data.bus_numero_interno || data.bus_disco || '--';

    return `
        <div class="p-1" style="min-width: 240px;">
            ${fotoHtml}
            <div class="d-flex justify-content-between align-items-center mb-1 pb-1 border-bottom">
                <strong class="text-danger">Bus Interno #${busNum}</strong>
                ${badgeRiesgo}
            </div>
            <div class="small mb-1"><strong>Placa:</strong> ${data.bus_placa || '--'}</div>
            <div class="small mb-1"><strong>Chofer:</strong> ${data.conductor || 'Asignado'}</div>
            <div class="small mb-1"><strong>Ruta:</strong> ${data.ruta || '--'}</div>
            <div class="small mb-1">
                <strong>Velocidad:</strong> 
                <span class="fs-6 fw-bold ${data.velocidad_kmh > 80 ? 'text-danger' : 'text-success'}">
                    ${(data.velocidad_kmh || 0).toFixed(1)} km/h
                </span>
            </div>
            ${fatigaHtml}
            ${alertaHtml}
            <div class="mt-2 text-center">
                <button class="btn btn-sm btn-outline-danger w-100 py-0" onclick="abrirModalPPS('${data.hoja_de_ruta_id}')">
                    <i class="fa-solid fa-shield me-1"></i> Protocolo PPS
                </button>
            </div>
        </div>
    `;
}

// 10. Renderizado de la Lista Lateral de Flota
function renderFleetList() {
    const listContainer = document.getElementById('activeFleetList');
    if (!listContainer) return;
    const buses = Object.values(fleetData);
    if (buses.length === 0) {
        listContainer.innerHTML = '<div class="text-muted small text-center py-4">No hay buses transmitiendo en este momento.</div>';
        return;
    }
    let html = '';
    buses.forEach(b => {
        let badgeCls = 'bg-secondary';
        let txtEstado = 'En Terminal';
        if (b.estado_hoja === 'EN_TRANSITO') {
            badgeCls = 'bg-success';
            txtEstado = `${(b.velocidad_kmh || 0).toFixed(1)} km/h`;
            if (b.nivel_riesgo === 'AMARILLO') badgeCls = 'bg-warning text-dark';
            else if (b.nivel_riesgo === 'ROJO') badgeCls = 'bg-danger';
        } else if (b.estado_hoja === 'FINALIZADA') {
            badgeCls = 'bg-dark';
            txtEstado = 'Finalizado';
        }
        const busNum = b.bus_numero_interno || b.bus_disco || '--';

        // Indicador de fatiga si existe
        let fatigaIndicator = '';
        if (b.indice_fatiga !== null && b.indice_fatiga !== undefined) {
            const ifv = parseFloat(b.indice_fatiga);
            const cls = ifv >= 0.75 ? 'text-danger' : ifv >= 0.50 ? 'text-warning' : 'text-success';
            fatigaIndicator = `<span class="${cls} small"><i class="fa-solid fa-brain me-1"></i>IF: ${ifv.toFixed(2)}</span>`;
        }

        html += `
            <div class="list-group-item list-group-item-action p-2 mb-2 border rounded cursor-pointer" onclick="centrarEnBus('${b.hoja_de_ruta_id}')">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <strong class="text-dark">Interno #${busNum} <span class="text-muted small">(${b.bus_placa || ''})</span></strong>
                    <span class="badge ${badgeCls}">${txtEstado}</span>
                </div>
                <div class="text-muted small text-truncate"><i class="fa-solid fa-route me-1"></i>${b.ruta || '--'}</div>
                <div class="d-flex justify-content-between align-items-center">
                    <span class="text-muted small"><i class="fa-solid fa-user me-1"></i>${b.conductor || '--'}</span>
                    ${fatigaIndicator}
                </div>
            </div>
        `;
    });
    listContainer.innerHTML = html;
}

// 11. Renderizado de Incidentes Activos (PPS)
function renderIncidentesList() {
    const container = document.getElementById('incidentesList');
    if (!container) return;
    const list = Object.values(activeIncidentes);
    if (list.length === 0) {
        container.innerHTML = '<div class="text-muted small text-center py-3">No hay alertas ni incidentes viales activos.</div>';
        return;
    }
    let html = '';
    list.forEach(inc => {
        const alertCls = inc.nivel_riesgo === 'ROJO' ? 'alert-danger border-danger' : 'alert-warning border-warning';
        const tipoLabel = inc.tipo_incidente === 'FATIGA_CRITICA' ? '🔴 FATIGA CRÍTICA' :
                          inc.tipo_incidente === 'SOMNOLENCIA_PREVENTIVA' ? '🟡 SOMNOLENCIA' :
                          inc.tipo_incidente === 'EXCESO_VELOCIDAD' ? '🟡 EXCESO VELOCIDAD' :
                          (inc.alerta ? String(inc.alerta).replace(/_/g, ' ') : 'Alerta vial');

        let fatigaInfo = '';
        if (inc.indice_fatiga) {
            fatigaInfo = ` | IF: ${parseFloat(inc.indice_fatiga).toFixed(2)}`;
        }

        html += `
            <div class="alert ${alertCls} border-start border-4 p-2 mb-2">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong class="text-danger">Bus #${inc.bus_disco}</strong>
                        <div class="small fw-semibold text-dark">${tipoLabel}${fatigaInfo}</div>
                        <div class="text-muted small">${new Date(inc.timestamp).toLocaleTimeString()} | ${inc.conductor}</div>
                    </div>
                    <button class="btn btn-sm btn-tc-primary py-1 px-2" onclick="abrirModalAtencionIncidente('${inc.incidente_id}', '${inc.bus_disco}')">
                        Atender
                    </button>
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
}

// 12. Actualizador de Contadores
function updateFleetCounters() {
    const buses = Object.values(fleetData);
    const countTotal = document.getElementById('countTotalBuses');
    if (countTotal) countTotal.textContent = buses.length;
}

// 13. Helpers de Interacción
window.centrarEnBus = function(hojaId) {
    if (markers[hojaId]) {
        map.setView(markers[hojaId].getLatLng(), 11, { animate: true });
        markers[hojaId].openPopup();
    }
};

window.abrirModalPPS = function(hojaId) {
    const inc = Object.values(activeIncidentes).find(i => i.hoja_de_ruta_id === hojaId);
    if (inc) {
        abrirModalAtencionIncidente(inc.incidente_id, inc.bus_disco);
    } else {
        const bus = fleetData[hojaId];
        const disco = bus ? (bus.bus_numero_interno || bus.bus_disco || '') : '';
        alert(`La unidad #${disco} se encuentra operando dentro de los parámetros normales sin incidentes críticos de fatiga.\n\nPara probar el Protocolo de Parada Segura (PPS), seleccione el escenario "Fatiga Crítica Inmediata" en el panel del simulador e inicie la simulación.`);
    }
};

window.abrirModalAtencionIncidente = function(incidenteId, busDisco) {
    document.getElementById('inputIncidenteId').value = incidenteId;
    document.getElementById('spanModalBusDisco').textContent = busDisco;
    // Reset audio
    document.getElementById('inputAudioUrl').value = '';
    const audioPreview = document.getElementById('audioPreview');
    if (audioPreview) { audioPreview.classList.add('d-none'); audioPreview.src = ''; }
    const modalEl = document.getElementById('modalAtencionIncidente');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
};

// 14. Sonido de Alerta
function playAlertSound(type) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        if (type === 'critical') {
            osc.frequency.value = 880;
            gain.gain.value = 0.3;
            osc.start();
            setTimeout(() => { osc.frequency.value = 660; }, 200);
            setTimeout(() => { osc.frequency.value = 880; }, 400);
            setTimeout(() => { osc.stop(); ctx.close(); }, 600);
        } else {
            osc.frequency.value = 660;
            gain.gain.value = 0.2;
            osc.start();
            setTimeout(() => { osc.stop(); ctx.close(); }, 300);
        }
    } catch(e) {}
}

// 15. Grabación de Audio para PPS
window.toggleGrabacion = async function() {
    if (isRecording) {
        // Detener grabación
        mediaRecorder.stop();
        isRecording = false;
        document.getElementById('txtGrabarAudio').textContent = 'Grabar';
        document.getElementById('btnGrabarAudio').classList.remove('btn-danger');
        document.getElementById('btnGrabarAudio').classList.add('btn-outline-danger');
        document.getElementById('audioRecordingIndicator').classList.add('d-none');
    } else {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const url = URL.createObjectURL(blob);
                const audioPreview = document.getElementById('audioPreview');
                audioPreview.src = url;
                audioPreview.classList.remove('d-none');
                document.getElementById('inputAudioUrl').value = 'audio_grabado_pps_' + Date.now() + '.webm';
                stream.getTracks().forEach(t => t.stop());
            };
            mediaRecorder.start();
            isRecording = true;
            document.getElementById('txtGrabarAudio').textContent = 'Detener';
            document.getElementById('btnGrabarAudio').classList.remove('btn-outline-danger');
            document.getElementById('btnGrabarAudio').classList.add('btn-danger');
            document.getElementById('audioRecordingIndicator').classList.remove('d-none');
        } catch(e) {
            alert('No se pudo acceder al micrófono. Verifique los permisos del navegador.');
        }
    }
};

// 16. Sincronizador de Opciones en el Combobox del Simulador
function sincronizarHojaEnSelect(b) {
    const simSelect = document.getElementById('simHojaSelect');
    if (!simSelect || !b || !b.hoja_de_ruta_id) return;
    const exists = Array.from(simSelect.options).some(o => o.value === b.hoja_de_ruta_id);
    if (!exists) {
        const opt = document.createElement('option');
        opt.value = b.hoja_de_ruta_id;
        const partesRuta = (b.ruta || '').split('->');
        opt.dataset.origen = partesRuta[0] ? partesRuta[0].trim() : 'Cochabamba';
        opt.dataset.destino = partesRuta[1] ? partesRuta[1].trim() : 'Santa Cruz';
        opt.dataset.conductorId = b.conductor_id || 'c0000000-0000-0000-0000-000000000006';
        opt.dataset.bus = b.bus_numero_interno || b.bus_disco || '--';
        opt.dataset.estado = b.estado_hoja || 'EN_TRANSITO';
        const estLimpio = (b.estado_hoja || 'EN_TRANSITO').replace(/_/g, ' ');
        opt.textContent = `${b.codigo_hoja || 'HR'} | ${b.bus_numero_interno || b.bus_disco || '--'} (${b.ruta || ''}) [${estLimpio}]`;
        simSelect.appendChild(opt);
    }
}

// 17. Centrado Automático al Seleccionar Hoja en el Simulador
document.addEventListener('DOMContentLoaded', () => {
    const simSelect = document.getElementById('simHojaSelect');
    if (simSelect) {
        simSelect.addEventListener('change', (e) => {
            const hojaId = e.target.value;
            if (hojaId && markers[hojaId]) {
                centrarEnBus(hojaId);
            }
        });
    }
});
