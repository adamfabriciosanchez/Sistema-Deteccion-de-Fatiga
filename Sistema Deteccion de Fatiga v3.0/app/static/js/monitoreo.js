/**
 * ===============================================================================
 * TRANS COPACABANA - CENTRO DE MONITOREO Y CONTROL EN TIEMPO REAL
 * LEAFLET.JS + WEBSOCKETS + RUTAS OFICIALES ATT + VISOR EN VIVO DE CABINA
 * (Totalmente desvinculado de simulaciones ficticias)
 * ===============================================================================
 */

let map = null;
let currentOfficialRouteLayer = null; // Capa de la ruta oficial activa en el mapa
let currentLiveRouteLayer = null;     // Capa de la ruta en carretera en vivo (verde)
let ultimaRutaCalculada = { lat: 0, lng: 0, ts: 0 };
let ultimoRenderFlota = 0;
const markers = {};                   // hoja_id -> L.marker
const fleetData = {};                 // hoja_id -> BusSnapshot
let activeIncidentes = {};           // incidente_id -> data
let busSeleccionadoId = null;         // ID de la hoja de ruta actualmente en foco

// Variables para grabación y subida de audio PPS
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initWebSocket();
    cargarFlotaInicial();
    initFormularioPPS();
});

// 1. Inicialización del Mapa Leaflet con Control Nativo de Pantalla Completa
function initMap() {
    map = L.map('mapContainer', {
        zoomControl: true
    }).setView([-17.4, -66.15], 7);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors | Red Vial Fundamental ATT Trans Copacabana'
    }).addTo(map);

    map.on('click', (e) => {
        // Clic en área vacía del mapa
    });
}

// Control Nativo de Pantalla Completa HTML5
window.toggleMapFullscreen = function() {
    const mapEl = document.getElementById('mapContainer');
    if (!document.fullscreenElement) {
        if (mapEl.requestFullscreen) {
            mapEl.requestFullscreen();
        } else if (mapEl.webkitRequestFullscreen) {
            mapEl.webkitRequestFullscreen();
        } else if (mapEl.msRequestFullscreen) {
            mapEl.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
};

document.addEventListener('fullscreenchange', () => {
    const icon = document.getElementById('iconMapFullscreen');
    if (document.fullscreenElement) {
        if (icon) icon.className = 'fa-solid fa-compress';
    } else {
        if (icon) icon.className = 'fa-solid fa-expand';
    }
    setTimeout(() => { if (map) map.invalidateSize(); }, 250);
});

// 2. Generador de Iconos de Pines según Semáforo de Riesgo
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
        if (statusBadge) {
            statusBadge.className = 'badge bg-success';
            statusBadge.textContent = 'EN VIVO';
        }
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWebSocketMessage(msg);
        } catch (err) {
            console.error('[Monitoreo] Error al procesar mensaje:', err);
        }
    };

    socket.onclose = () => {
        if (statusBadge) {
            statusBadge.className = 'badge bg-danger';
            statusBadge.textContent = 'DESCONECTADO';
        }
        setTimeout(initWebSocket, 3000);
    };
}

// 4. Carga Inicial de la Flota Activa
function cargarFlotaInicial() {
    if (window.INITIAL_FLEET_DATA && Array.isArray(window.INITIAL_FLEET_DATA)) {
        window.INITIAL_FLEET_DATA.forEach(b => updateBusOnMap(b));
        if (window.FILTRO_HOJA_ID && fleetData[window.FILTRO_HOJA_ID]) {
            seleccionarBus(window.FILTRO_HOJA_ID);
        }
    }

    fetch('/api/v1/telemetria/monitoreo-flota')
        .then(res => res.json())
        .then(buses => {
            if (Array.isArray(buses)) {
                buses.forEach(b => updateBusOnMap(b));
                if (window.FILTRO_HOJA_ID && fleetData[window.FILTRO_HOJA_ID]) {
                    seleccionarBus(window.FILTRO_HOJA_ID);
                }
            }
        })
        .catch(err => console.warn('[Monitoreo] Error al sincronizar flota:', err));
}

// 5. Manejador de Mensajes en Tiempo Real
function handleWebSocketMessage(msg) {
    if (msg.tipo_evento === 'SNAPSHOT_INICIAL') {
        if (Array.isArray(msg.buses)) {
            msg.buses.forEach(b => updateBusOnMap(b));
        }
    } else if (msg.tipo_evento === 'TELEMETRIA_ACTUALIZADA' || msg.tipo_evento === 'HOJA_AUTORIZADA') {
        updateBusOnMap(msg.data);
    } else if (msg.tipo_evento === 'NOTIFICACION_CONDUCTOR') {
        handleNotificacionConductor(msg);
    } else if (msg.tipo_evento === 'INCIDENTE_ALERTA') {
        handleIncidenteAlerta(msg);
    } else if (msg.tipo_evento === 'INCIDENTE_ATENDIDO') {
        handleIncidenteAtendido(msg);
    }
}

// 6. Actualización de Marcadores y Panel Lateral
function updateBusOnMap(data) {
    if (!data || !data.hoja_de_ruta_id) return;
    const hojaId = data.hoja_de_ruta_id;
    fleetData[hojaId] = Object.assign({}, fleetData[hojaId] || {}, data);

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

        marker.on('click', () => {
            seleccionarBus(hojaId);
        });

        markers[hojaId] = marker;
    } else {
        const marker = markers[hojaId];
        marker.setLatLng(latlng);
        marker.setIcon(createBusIcon(busDisco, nivelRiesgo, estadoHoja));
    }

    // Si este bus es el actualmente seleccionado, actualizar el panel lateral y ruta en vivo
    if (busSeleccionadoId === hojaId) {
        actualizarContenidoPanelDetalle(fleetData[hojaId]);
        if (data.latitud !== null && data.longitud !== null && currentOfficialRouteLayer) {
            const latlngs = currentOfficialRouteLayer.getLatLngs();
            if (latlngs && latlngs.length > 0) {
                const destPunto = latlngs[latlngs.length - 1];
                trazarRutaEnVivoVerde(data.latitud, data.longitud, destPunto.lat, destPunto.lng);
            }
        }
    }

    renderFleetList();
    updateFleetCounters();
}

// 7. Selección de Bus y Trazado de Ruta Oficial de la ATT On-Demand
function seleccionarBus(hojaId) {
    const data = fleetData[hojaId];
    if (!data) return;

    busSeleccionadoId = hojaId;

    // Centrar mapa suavemente en el bus
    if (markers[hojaId]) {
        map.panTo(markers[hojaId].getLatLng(), { animate: true, duration: 0.8 });
    }

    // Dibujar ruta oficial ATT y ruta en carretera en vivo hasta el destino
    trazarRutaOficialATT(hojaId);

    // Abrir y actualizar el panel lateral derecho con cámara y datos
    const panel = document.getElementById('panelDetalleBus');
    if (panel) panel.style.display = 'block';

    actualizarContenidoPanelDetalle(data);
}

// 8. Trazar la Ruta Oficial ATT y Trazado en Vivo por Carretera hacia Destino
function trazarRutaOficialATT(hojaId) {
    if (currentOfficialRouteLayer) {
        map.removeLayer(currentOfficialRouteLayer);
        currentOfficialRouteLayer = null;
    }
    if (currentLiveRouteLayer) {
        map.removeLayer(currentLiveRouteLayer);
        currentLiveRouteLayer = null;
    }

    fetch(`/api/v1/telemetria/ruta-oficial/${hojaId}`)
        .then(res => res.json())
        .then(res => {
            if (res && res.puntos_latlng && res.puntos_latlng.length > 0) {
                // Trazado base oficial ATT
                currentOfficialRouteLayer = L.polyline(res.puntos_latlng, {
                    color: '#C8102E',
                    weight: 3,
                    opacity: 0.55,
                    dashArray: '6, 6'
                }).addTo(map);

                // Destino oficial de la terminal
                const destPunto = res.puntos_latlng[res.puntos_latlng.length - 1];
                const data = fleetData[hojaId];

                // Si el bus reporta telemetría GPS, trazar la ruta en verde por carretera hasta la terminal destino
                if (data && data.latitud !== null && data.longitud !== null && destPunto) {
                    trazarRutaEnVivoVerde(data.latitud, data.longitud, destPunto[0], destPunto[1], true);
                }
            }
        })
        .catch(err => console.warn('[Monitoreo] Error al cargar ruta oficial:', err));
}

function trazarRutaEnVivoVerde(latActual, lngActual, latDest, lngDest, forzar = false) {
    const ahora = Date.now();
    const distancia = Math.hypot(latActual - ultimaRutaCalculada.lat, lngActual - ultimaRutaCalculada.lng);
    // Solo consultar OSRM si es la primera vez, si el bus se movió más de ~150 metros, o si pasaron 40 segundos
    if (!forzar && distancia < 0.0015 && (ahora - ultimaRutaCalculada.ts) < 40000) {
        return;
    }
    ultimaRutaCalculada = { lat: latActual, lng: lngActual, ts: ahora };

    const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${lngActual},${latActual};${lngDest},${latDest}?overview=full&geometries=geojson`;
    fetch(osrmUrl)
        .then(r => r.json())
        .then(res => {
            if (res.routes && res.routes[0] && res.routes[0].geometry) {
                const coords = res.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                if (currentLiveRouteLayer) {
                    map.removeLayer(currentLiveRouteLayer);
                }
                currentLiveRouteLayer = L.polyline(coords, {
                    color: '#198754',
                    weight: 5,
                    opacity: 0.9
                }).addTo(map);
            }
        })
        .catch(() => {
            // Silencioso en caso de indisponibilidad externa
        });
}

// 9. Actualización del Panel Lateral con Datos y Cámara en Vivo
function actualizarContenidoPanelDetalle(data) {
    if (!data) return;

    // Encabezado
    const spanNum = document.getElementById('detBusNumero');
    const spanPlaca = document.getElementById('detBusPlaca');
    if (spanNum) spanNum.textContent = `Bus Interno ${data.bus_numero_interno || data.bus_disco || '--'}`;
    if (spanPlaca) spanPlaca.textContent = `(${data.bus_placa || ''})`;

    // Estado / Riesgo
    const badgeRiesgo = document.getElementById('detBadgeRiesgo');
    if (badgeRiesgo) {
        if (data.nivel_riesgo === 'ROJO') {
            badgeRiesgo.className = 'badge bg-danger';
            badgeRiesgo.textContent = 'CRÍTICO';
        } else if (data.nivel_riesgo === 'AMARILLO') {
            badgeRiesgo.className = 'badge bg-warning text-dark';
            badgeRiesgo.textContent = 'ADVERTENCIA';
        } else {
            badgeRiesgo.className = 'badge bg-success';
            badgeRiesgo.textContent = 'ÓPTIMO';
        }
    }

    // Cámara Feed (Frame Base64 transmitido)
    const imgFeed = document.getElementById('detCamFeed');
    const phFeed = document.getElementById('detCamPlaceholder');
    if (data.frame_b64 && imgFeed) {
        imgFeed.src = data.frame_b64;
        imgFeed.classList.remove('d-none');
        if (phFeed) phFeed.classList.add('d-none');
    }

    // Velocidad e IF
    const spanVel = document.getElementById('detVelocidad');
    const spanIf = document.getElementById('detIndiceFatiga');
    if (spanVel) spanVel.textContent = (data.velocidad_kmh || 0).toFixed(1);
    if (spanIf && data.indice_fatiga !== undefined && data.indice_fatiga !== null) {
        spanIf.textContent = parseFloat(data.indice_fatiga).toFixed(2);
    }

    // Foto y Datos del Bus
    const busFoto = document.getElementById('detBusFoto');
    const busFotoPh = document.getElementById('detBusFotoPh');
    if (data.foto_bus && busFoto) {
        busFoto.src = data.foto_bus;
        busFoto.classList.remove('d-none');
        if (busFotoPh) busFotoPh.classList.add('d-none');
    } else if (busFoto && busFotoPh) {
        busFoto.classList.add('d-none');
        busFotoPh.classList.remove('d-none');
    }

    const busModelo = document.getElementById('detBusModelo');
    const busTipo = document.getElementById('detBusTipo');
    const busRuta = document.getElementById('detBusRuta');
    if (busModelo) busModelo.textContent = `${data.bus_modelo || 'Mercedes-Benz'}`;
    if (busTipo) busTipo.textContent = `Tipo: ${data.tipo_bus || 'Leito / Semi Cama'}`;
    if (busRuta) busRuta.textContent = `Ruta: ${data.ruta || '--'}`;

    // Conductor Principal
    const choferNombre = document.getElementById('detChoferNombre');
    const choferLic = document.getElementById('detChoferLic');
    const choferFoto = document.getElementById('detChoferFoto');
    const choferFotoPh = document.getElementById('detChoferFotoPh');
    if (choferNombre) choferNombre.textContent = data.conductor || 'Conductor Asignado';
    if (choferLic) choferLic.textContent = `Licencia: ${data.licencia_conductor || 'Profesional'}`;

    if (data.foto_conductor && choferFoto) {
        choferFoto.src = data.foto_conductor;
        choferFoto.classList.remove('d-none');
        if (choferFotoPh) choferFotoPh.classList.add('d-none');
    } else if (choferFoto && choferFotoPh) {
        choferFoto.classList.add('d-none');
        choferFotoPh.classList.remove('d-none');
    }

    // Conductor de Relevo
    const relevoRow = document.getElementById('detRelevoRow');
    if (data.conductor_relevo && relevoRow) {
        relevoRow.classList.remove('d-none');
        const relevoNombre = document.getElementById('detRelevoNombre');
        const relevoLic = document.getElementById('detRelevoLic');
        const relevoFoto = document.getElementById('detRelevoFoto');
        const relevoFotoPh = document.getElementById('detRelevoFotoPh');

        if (relevoNombre) relevoNombre.textContent = data.conductor_relevo;
        if (relevoLic) relevoLic.textContent = `Licencia: ${data.licencia_relevo || 'Profesional'}`;

        if (data.foto_relevo && relevoFoto) {
            relevoFoto.src = data.foto_relevo;
            relevoFoto.classList.remove('d-none');
            if (relevoFotoPh) relevoFotoPh.classList.add('d-none');
        } else if (relevoFoto && relevoFotoPh) {
            relevoFoto.classList.add('d-none');
            relevoFotoPh.classList.remove('d-none');
        }
    } else if (relevoRow) {
        relevoRow.classList.add('d-none');
    }

    // Métricas para Operador
    const earEl = document.getElementById('detEar');
    const marEl = document.getElementById('detMar');
    const perclosEl = document.getElementById('detPerclos');
    if (earEl) earEl.textContent = data.ear ? parseFloat(data.ear).toFixed(3) : '--';
    if (marEl) marEl.textContent = data.mar ? parseFloat(data.mar).toFixed(3) : '--';
    if (perclosEl) perclosEl.textContent = data.perclos ? `${parseFloat(data.perclos).toFixed(1)}%` : '--';

    // Alerta o petición activa en panel lateral
    const alertMsgEl = document.getElementById('detAlertaMensaje');
    if (alertMsgEl) {
        if (data.alerta_mensaje) {
            alertMsgEl.textContent = data.alerta_mensaje;
            alertMsgEl.classList.remove('d-none');
        } else {
            alertMsgEl.classList.add('d-none');
        }
    }
}

function cerrarPanelDetalleBus() {
    busSeleccionadoId = null;
    const panel = document.getElementById('panelDetalleBus');
    if (panel) panel.style.display = 'none';
    if (currentOfficialRouteLayer) {
        map.removeLayer(currentOfficialRouteLayer);
        currentOfficialRouteLayer = null;
    }
    if (currentLiveRouteLayer) {
        map.removeLayer(currentLiveRouteLayer);
        currentLiveRouteLayer = null;
    }
}

// 10. Renderizado de Flota Activa en Panel Lateral (optimizado con throttling)
function renderFleetList(forzar = false) {
    const ahora = Date.now();
    if (!forzar && (ahora - ultimoRenderFlota < 2500)) return;
    ultimoRenderFlota = ahora;

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

        html += `
            <div class="list-group-item list-group-item-action p-2 mb-2 border rounded cursor-pointer" onclick="seleccionarBus('${b.hoja_de_ruta_id}')">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <strong class="text-dark">Interno #${busNum} <span class="text-muted small">(${b.bus_placa || ''})</span></strong>
                    <span class="badge ${badgeCls}">${txtEstado}</span>
                </div>
                <div class="text-muted small text-truncate"><i class="fa-solid fa-route me-1"></i>${b.ruta || '--'}</div>
                <div class="d-flex justify-content-between align-items-center mt-1">
                    <span class="text-muted small">${b.conductor || '--'}</span>
                    ${b.indice_fatiga ? `<span class="badge bg-light text-dark border">IF: ${parseFloat(b.indice_fatiga).toFixed(2)}</span>` : ''}
                </div>
            </div>
        `;
    });
    listContainer.innerHTML = html;
}

// 11. Manejo de Peticiones del Conductor
function handleNotificacionConductor(msg) {
    const hojaId = msg.hoja_de_ruta_id;
    const busData = (hojaId && fleetData[hojaId]) ? fleetData[hojaId] : {};
    const busNum = busData.bus_numero_interno || busData.bus_disco || '--';
    const peticionTxt = (msg.tipo_peticion || '').replace(/_/g, ' ');
    const mensajeDetalle = msg.mensaje || peticionTxt;

    // Mostrar banner de notificación emergente superior
    const banner = document.getElementById('bannerNotificacionConductor');
    const bBus = document.getElementById('bannerConductorBus');
    const bMsg = document.getElementById('bannerConductorMsg');
    if (banner && bBus && bMsg) {
        bBus.textContent = `Bus Interno #${busNum}`;
        bMsg.textContent = `${peticionTxt}: "${mensajeDetalle}"`;
        banner.classList.remove('d-none');
    }

    if (hojaId && fleetData[hojaId]) {
        fleetData[hojaId].alerta_mensaje = `PETICIÓN CONDUCTOR: ${peticionTxt} ("${mensajeDetalle}")`;
        fleetData[hojaId].nivel_riesgo = 'AMARILLO';
        updateBusOnMap(fleetData[hojaId]);
        seleccionarBus(hojaId);
    }
}

window.cerrarBannerNotificacion = function() {
    const banner = document.getElementById('bannerNotificacionConductor');
    if (banner) banner.classList.add('d-none');
};

// 12. Alertas de Incidentes Reales de Visión Artificial (Visuales en Monitoreo)
function handleIncidenteAlerta(msg) {
    const data = msg.data || {};
    const hojaId = data.hoja_de_ruta_id || msg.hoja_de_ruta_id;
    if (hojaId && fleetData[hojaId]) {
        fleetData[hojaId].nivel_riesgo = msg.nivel_riesgo || 'ROJO';
        fleetData[hojaId].alerta_mensaje = msg.tipo_incidente || 'FATIGA DETECTADA';
        if (msg.indice_fatiga !== undefined && msg.indice_fatiga !== null) {
            fleetData[hojaId].indice_fatiga = msg.indice_fatiga;
        }
        if (msg.perclos !== undefined && msg.perclos !== null) {
            fleetData[hojaId].perclos = msg.perclos;
        }
        updateBusOnMap(fleetData[hojaId]);
        if (busSeleccionadoId === hojaId) {
            actualizarContenidoPanelDetalle(fleetData[hojaId]);
        }
    }
}

function handleIncidenteAtendido(msg) {
    const hojaId = msg.hoja_de_ruta_id;
    if (hojaId && fleetData[hojaId]) {
        fleetData[hojaId].alerta_mensaje = null;
        fleetData[hojaId].nivel_riesgo = 'VERDE';
        updateBusOnMap(fleetData[hojaId]);
        if (busSeleccionadoId === hojaId) {
            actualizarContenidoPanelDetalle(fleetData[hojaId]);
        }
    }
}

function updateFleetCounters() {
    const buses = Object.values(fleetData);
    const totalEl = document.getElementById('countTotalBuses');
    const badgeTotal = document.getElementById('badgeTotalUnidades');
    if (totalEl) totalEl.textContent = buses.length;
    if (badgeTotal) badgeTotal.textContent = buses.length;
}

// 14. Protocolo de Parada Segura (PPS)
function abrirModalPPS(hojaId, incId) {
    const data = fleetData[hojaId] || {};
    const inputInc = document.getElementById('inputIncidenteId');
    const inputHoja = document.getElementById('inputModalHojaId');
    const spanBus = document.getElementById('spanModalBusDisco');
    if (spanBus) spanBus.textContent = data.bus_numero_interno || data.bus_disco || '--';
    if (inputInc) inputInc.value = incId || '';
    if (inputHoja) inputHoja.value = hojaId || '';

    // Reset audio
    document.getElementById('inputAudioUrl').value = '';
    const audioPreview = document.getElementById('audioPreview');
    if (audioPreview) { audioPreview.classList.add('d-none'); audioPreview.src = ''; }
    const statusUpload = document.getElementById('audioUploadStatus');
    if (statusUpload) statusUpload.classList.add('d-none');

    const modal = new bootstrap.Modal(document.getElementById('modalAtencionIncidente'));
    modal.show();
}

function abrirModalPPSSeleccionado() {
    if (!busSeleccionadoId) return;
    abrirModalPPS(busSeleccionadoId, '');
}

// 15. Grabación y Subida de Audio Real para PPS
async function toggleGrabacion() {
    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);

            mediaRecorder.onstop = async () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const url = URL.createObjectURL(blob);
                const audioPreview = document.getElementById('audioPreview');
                audioPreview.src = url;
                audioPreview.classList.remove('d-none');

                // Subir archivo real al servidor
                const formData = new FormData();
                formData.append('audio_file', blob, `audio_pps_${Date.now()}.webm`);

                try {
                    const res = await fetch('/api/v1/telemetria/subir-audio-pps', {
                        method: 'POST',
                        body: formData
                    });
                    const resData = await res.json();
                    if (resData.audio_url) {
                        document.getElementById('inputAudioUrl').value = resData.audio_url;
                        const statusUpload = document.getElementById('audioUploadStatus');
                        if (statusUpload) statusUpload.classList.remove('d-none');
                    }
                } catch (e) {
                    console.error('[PPS] Error al subir audio al servidor:', e);
                }
            };

            mediaRecorder.start();
            isRecording = true;
            document.getElementById('txtGrabarAudio').textContent = 'Detener';
            document.getElementById('btnGrabarAudio').classList.remove('btn-outline-danger');
            document.getElementById('btnGrabarAudio').classList.add('btn-danger');
            document.getElementById('audioRecordingIndicator').classList.remove('d-none');
        } catch (err) {
            alert('No se pudo acceder al micrófono para grabar la nota de voz.');
        }
    } else {
        mediaRecorder.stop();
        isRecording = false;
        document.getElementById('txtGrabarAudio').textContent = 'Grabar Audio';
        document.getElementById('btnGrabarAudio').classList.remove('btn-danger');
        document.getElementById('btnGrabarAudio').classList.add('btn-outline-danger');
        document.getElementById('audioRecordingIndicator').classList.add('d-none');
    }
}

// Alertas sonoras desactivadas en Monitoreo (las alarmas acústicas operan exclusivamente en cabina del conductor)
function playAlertSound(tipo) {
    // Monitoreo exclusivamente visual según requerimiento
}

// 16. Envío Asíncrono de PPS (Garantiza que la pantalla NO se recargue y la cámara siga en vivo)
function initFormularioPPS() {
    const form = document.getElementById('formAtencionPPS');
    if (!form) return;

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        const btnSubmit = this.querySelector('button[type="submit"]');
        const origText = btnSubmit ? btnSubmit.innerHTML : 'Enviar';
        if (btnSubmit) {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Transmitiendo a cabina...';
        }

        try {
            const formData = new FormData(this);
            await fetch('/monitoreo/atender', {
                method: 'POST',
                headers: { 'Accept': 'application/json' },
                body: formData
            });

            // Cerrar el modal PPS
            const modalEl = document.getElementById('modalAtencionIncidente');
            const modalInstance = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
            modalInstance.hide();

            // Limpiar campos de texto y audio
            form.reset();
            const audioPreview = document.getElementById('audioPreview');
            if (audioPreview) { audioPreview.src = ''; audioPreview.classList.add('d-none'); }
            const uploadStatus = document.getElementById('audioUploadStatus');
            if (uploadStatus) uploadStatus.classList.add('d-none');

            // Mostrar confirmación en el dashboard sin recargar la página
            mostrarToastDashboard('Instrucción y nota de voz transmitidas con éxito al conductor.');
        } catch (err) {
            console.error('[PPS] Error al transmitir atención:', err);
            alert('Error de conexión al registrar atención.');
        } finally {
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = origText;
            }
        }
    });
}

function mostrarToastDashboard(msg) {
    let toastContainer = document.getElementById('dashboardToastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'dashboardToastContainer';
        toastContainer.className = 'position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
    const toastEl = document.createElement('div');
    toastEl.className = 'toast align-items-center text-bg-success border-0 show shadow-lg mb-2';
    toastEl.role = 'alert';
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body fw-semibold">
                <i class="fa-solid fa-circle-check me-2"></i> ${msg}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.closest('.toast').remove()"></button>
        </div>
    `;
    toastContainer.appendChild(toastEl);
    setTimeout(() => {
        if (toastEl.parentNode) toastEl.remove();
    }, 4500);
}
