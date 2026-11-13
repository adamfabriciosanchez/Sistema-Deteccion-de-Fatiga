/**
 * ===============================================================================
 * TRANS COPACABANA - CABINA INTELIGENTE Y DETECCIÓN DE FATIGA EN TIEMPO REAL
 * MediaPipe Face Landmarker (WASM/WebGL) + Web Audio API con Volumen Progresivo
 * Transmisión de Telemetría y Video Streaming en Vivo hacia el Centro de Monitoreo
 * ===============================================================================
 */

(function () {
    'use strict';

    // Puntos faciales de interés en MediaPipe
    const P_OLHO_ESQ = [385, 380, 387, 373, 362, 263];
    const P_OLHO_DIR = [160, 144, 158, 153, 33, 133];
    const P_BOCA     = [82, 87, 13, 14, 312, 317, 78, 308];
    const P_PUNTOS   = [...P_OLHO_ESQ, ...P_OLHO_DIR, ...P_BOCA];

    // Umbrales biométricos calibrados
    const EAR_LIMIAR = 0.26;
    const MAR_LIMIAR = 0.50;
    const TIEMPO_CRITICO_OJOS = 1.5;
    const PARPADEOS_MIN_DEFAULT = 10;

    // Estado del motor de visión
    let faceLandmarker = null;
    let drawingUtils = null;
    let FaceLandmarkerModule = null;
    let FilesetResolverModule = null;
    let stream = null;
    let activo = false;
    let animFrameId = null;
    let ultimoTiempoVideo = -1;
    let enEsperaRelevo = false; // Exclusividad: true si otro conductor ya está al volante transmitiendo

    // Métricas temporales
    let dormindo = false;
    let tInicialCierre = 0;
    let tiempoCierreActual = 0;
    let contagemPiscadas = 0;
    let contagemTemporaria = 0;
    let contagemLista = [];
    let cTempo = 0;
    let tInicioSesion = 0;

    // Control de Alerta Sonora Progresiva
    let tInicioAlarmaCritica = 0;
    let ultimaAlertaSonora = 0;

    // Buffer PERCLOS
    const PERCLOS_SLOTS = 120;
    const perclosBuffer = [];
    let ultimoMuestreoPerclos = 0;

    // Buffer Bostezos
    let tInicioBostezo = 0;
    let bostezando = false;
    let conteoBostezosMinuto = 0;
    const bostezosBuffer = [];

    // Audio Context
    let audioCtx = null;

    // Telemetría y Streaming
    let telemetryWs = null;
    let wsReconnectionTimer = null;
    let ultimoEnvioTelemetria = 0;
    const INTERVALO_ENVIO_MS = 800; // ~1.25 FPS: Transmisión fluida optimizada sin saturar el ancho de banda móvil

    // Canvas auxiliar para compresión de fotograma
    let offscreenCanvas = null;

    // GPS y velocidad
    let velocidadActualKmh = 0.0;
    let latitudActual = -17.4042;
    let longitudActual = -66.1583;
    let geoWatchId = null;

    // Configuración de la cabina
    const config = window.CABINA_CONFIG || {
        hoja_id: null,
        conductor_id: null,
        origen_ciudad: "Cochabamba",
        destino_ciudad: "La Paz",
        estado_hoja: "EN_TRANSITO"
    };

    function dist(a, b) {
        return Math.hypot(a.x - b.x, a.y - b.y);
    }

    function calculoEar(lm, p) {
        const f = p.map(i => lm[i]);
        const vertical = dist(f[0], f[1]) + dist(f[2], f[3]);
        const horizontal = 2 * dist(f[4], f[5]);
        return horizontal === 0 ? 0.0 : vertical / horizontal;
    }

    function calculoEarMedio(lm) {
        return (calculoEar(lm, P_OLHO_ESQ) + calculoEar(lm, P_OLHO_DIR)) / 2;
    }

    function calculoMar(lm) {
        const f = P_BOCA.map(i => lm[i]);
        const vertical = dist(f[0], f[1]) + dist(f[2], f[3]) + dist(f[4], f[5]);
        const horizontal = 2 * dist(f[6], f[7]);
        return horizontal === 0 ? 0.0 : vertical / horizontal;
    }

    /**
     * Alarma acústica del docente con volumen progresivo:
     * - Modulación de sirena: Oscilador portador 440 Hz + LFO a 2 Hz (+-220 Hz).
     * - Si la fatiga crítica persiste, el volumen aumenta suavemente desde 0.5 hasta 1.0.
     */
    function reproducirAlarmaProgresiva(duracionEnAlarma) {
        try {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }

            const inputVolMax = parseFloat(document.getElementById("cabinaVolumen")?.value || 0.85);

            // Escalamiento progresivo de volumen según los segundos continuos con ojos cerrados / fatiga
            let factorEscalamiento = 0.50;
            if (duracionEnAlarma >= 3.0) {
                factorEscalamiento = 1.0;
            } else if (duracionEnAlarma >= 1.5) {
                factorEscalamiento = 0.75;
            }
            const volumenEfectivo = Math.min(1.0, inputVolMax * factorEscalamiento);

            const t0 = audioCtx.currentTime;
            const dur = 0.8;

            const master = audioCtx.createGain();
            master.gain.setValueAtTime(volumenEfectivo, t0);
            master.gain.linearRampToValueAtTime(volumenEfectivo, t0 + dur * 0.8);
            master.gain.linearRampToValueAtTime(0.01, t0 + dur);
            master.connect(audioCtx.destination);

            // Sirena del docente: Oscilador portador 440 Hz modulado a 2 Hz (+-220 Hz)
            const osc = audioCtx.createOscillator();
            osc.type = "sine";
            osc.frequency.setValueAtTime(440, t0);

            const lfo = audioCtx.createOscillator();
            lfo.type = "sine";
            lfo.frequency.setValueAtTime(2, t0);

            const lfoGain = audioCtx.createGain();
            lfoGain.gain.setValueAtTime(220, t0);

            lfo.connect(lfoGain);
            lfoGain.connect(osc.frequency);
            osc.connect(master);

            osc.start(t0);
            lfo.start(t0);
            osc.stop(t0 + dur);
            lfo.stop(t0 + dur);

        } catch (e) {
            console.warn("[Cabina] Error de síntesis de audio:", e);
        }
    }

    /**
     * Inicialización del modelo MediaPipe Face Landmarker
     */
    async function inicializarMediaPipeModulos() {
        if (FaceLandmarkerModule && FilesetResolverModule && faceLandmarker) return;

        let bundleUrl = "/static/vendor/mediapipe/vision_bundle.mjs";
        let wasmUrl = "/static/vendor/mediapipe/wasm";
        let modelUrl = "/static/vendor/mediapipe/face_landmarker.task";

        try {
            const mod = await import(bundleUrl);
            FaceLandmarkerModule = mod.FaceLandmarker;
            FilesetResolverModule = mod.FilesetResolver;
            window.DrawingUtilsModule = mod.DrawingUtils;

            const fileset = await FilesetResolverModule.forVisionTasks(wasmUrl);
            faceLandmarker = await FaceLandmarkerModule.createFromOptions(fileset, {
                baseOptions: {
                    modelAssetPath: modelUrl,
                    delegate: "GPU"
                },
                runningMode: "VIDEO",
                numFaces: 1,
                minFaceDetectionConfidence: 0.5,
                minTrackingConfidence: 0.5
            });
            console.log("[Cabina] MediaPipe cargado exitosamente desde vendor local.");
        } catch (errLocal) {
            console.warn("[Cabina] Cargando desde CDN por fallback:", errLocal);
            bundleUrl = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";
            wasmUrl = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
            modelUrl = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

            const mod = await import(bundleUrl);
            FaceLandmarkerModule = mod.FaceLandmarker;
            FilesetResolverModule = mod.FilesetResolver;
            window.DrawingUtilsModule = mod.DrawingUtils;

            const fileset = await FilesetResolverModule.forVisionTasks(wasmUrl);
            faceLandmarker = await FaceLandmarkerModule.createFromOptions(fileset, {
                baseOptions: {
                    modelAssetPath: modelUrl,
                    delegate: "GPU"
                },
                runningMode: "VIDEO",
                numFaces: 1,
                minFaceDetectionConfidence: 0.5,
                minTrackingConfidence: 0.5
            });
        }
    }

    function loop() {
        if (!activo) return;

        const video = document.getElementById("cabinaVideo");
        const canvas = document.getElementById("cabinaOverlay");
        if (!video || !canvas) return;

        if (video.currentTime !== ultimoTiempoVideo && video.videoWidth > 0) {
            ultimoTiempoVideo = video.currentTime;
            try {
                const resultado = faceLandmarker.detectForVideo(video, performance.now());
                procesarFotograma(resultado, video, canvas);
            } catch (err) {
                console.error("[Cabina] Error en detección:", err);
            }
        }
        animFrameId = requestAnimationFrame(loop);
    }

    function procesarFotograma(resultado, video, canvas) {
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const badgeEstado = document.getElementById("cabinaBadgeEstado");
        const estadoNivelTxt = document.getElementById("conductorEstadoNivel");
        const ifProgressBar = document.getElementById("cabinaIfProgressBar");
        const hudAlertBanner = document.getElementById("cabinaHudAlert");

        const ahora = performance.now() / 1000;

        if (!resultado.faceLandmarks || resultado.faceLandmarks.length === 0) {
            dormindo = false;
            tiempoCierreActual = 0;
            tInicioAlarmaCritica = 0;
            if (badgeEstado) {
                badgeEstado.textContent = "SIN ROSTRO DETECTADO";
                badgeEstado.className = "badge bg-secondary px-3 py-1 fs-6";
            }
            if (estadoNivelTxt) {
                estadoNivelTxt.textContent = "DESPEJADO";
                estadoNivelTxt.className = "display-6 fw-bold text-secondary";
            }
            if (hudAlertBanner) hudAlertBanner.classList.add("d-none");
            return;
        }

        const lm = resultado.faceLandmarks[0];

        // Dibujar malla facial y puntos clave sobre el canvas (se transmiten al operador)
        if (window.DrawingUtilsModule) {
            if (!drawingUtils) drawingUtils = new window.DrawingUtilsModule(ctx);
            drawingUtils.drawConnectors(lm, FaceLandmarkerModule.FACE_LANDMARKS_CONTOUR, {
                color: "#00E5FF",
                lineWidth: 1
            });
            ctx.fillStyle = "#FF1744";
            P_PUNTOS.forEach(idx => {
                ctx.beginPath();
                ctx.arc(lm[idx].x * canvas.width, lm[idx].y * canvas.height, 2, 0, 2 * Math.PI);
                ctx.fill();
            });
        }

        // Cálculos biométricos
        const ear = calculoEarMedio(lm);
        const mar = calculoMar(lm);

        const ojosCerrados = (ear < EAR_LIMIAR);

        if (ojosCerrados) {
            if (!dormindo) {
                tInicialCierre = ahora;
                contagemPiscadas++;
            }
            dormindo = true;
            tiempoCierreActual = ahora - tInicialCierre;
        } else {
            dormindo = false;
            tiempoCierreActual = 0;
            tInicioAlarmaCritica = 0;
        }

        // Detección de bostezo
        if (mar > MAR_LIMIAR) {
            if (!bostezando) {
                tInicioBostezo = ahora;
                bostezando = true;
            }
            if (ahora - tInicioBostezo >= 1.5) {
                bostezosBuffer.push(ahora);
            }
        } else {
            bostezando = false;
        }

        while (bostezosBuffer.length > 0 && bostezosBuffer[0] < (ahora - 60)) {
            bostezosBuffer.shift();
        }
        conteoBostezosMinuto = bostezosBuffer.length;

        // PERCLOS
        if (ahora - ultimoMuestreoPerclos >= 0.5) {
            ultimoMuestreoPerclos = ahora;
            perclosBuffer.push(ojosCerrados ? 1 : 0);
            if (perclosBuffer.length > PERCLOS_SLOTS) {
                perclosBuffer.shift();
            }
        }

        const totalMuestras = perclosBuffer.length;
        const muestrasCerradas = perclosBuffer.reduce((acc, v) => acc + v, 0);
        const perclosPorcentaje = totalMuestras > 0 ? (muestrasCerradas / totalMuestras) * 100 : 0;

        // Parpadeos
        const transcurrido = ahora - tInicioSesion;
        if (transcurrido >= cTempo + 1) {
            cTempo = transcurrido;
            contagemLista.push(contagemPiscadas - contagemTemporaria);
            contagemTemporaria = contagemPiscadas;
            if (contagemLista.length > 60) contagemLista = contagemLista.slice(-60);
        }
        const piscadasPm = transcurrido <= 60 ? 15 : contagemLista.reduce((a, b) => a + b, 0);

        // Cálculo de IF según modelo del docente (somnolencia.html / detectarSuenho.py)
        let indiceFatiga = 0.10;

        if (tiempoCierreActual >= TIEMPO_CRITICO_OJOS) {
            // Ojos cerrados >= 1.5s -> Somnolencia crítica / microsueño profundo
            indiceFatiga = Math.min(1.0, 0.85 + (tiempoCierreActual - 1.5) * 0.10);
        } else if (tiempoCierreActual >= 0.7) {
            // Microsueño inicial (entre 0.7s y 1.5s) -> Precaución
            indiceFatiga = 0.55 + (tiempoCierreActual - 0.7) * 0.30;
        } else {
            // Ojos abiertos: evaluar PERCLOS acumulado, bostezos y parpadeos
            const perclosNorm = Math.min(0.35, (perclosPorcentaje / 100.0) * 0.40);
            const bostezoNorm = Math.min(0.20, conteoBostezosMinuto * 0.08);
            // Solo penalizar si han transcurrido más de 60s y la frecuencia es anómalamente baja (<6)
            const parpadeoNorm = (transcurrido > 60 && piscadasPm < 6) ? 0.15 : 0.0;
            indiceFatiga = Math.min(0.48, 0.10 + perclosNorm + bostezoNorm + parpadeoNorm);
        }

        // Niveles Semafóricos y Lenguaje Sencillo para Conductor
        let nivelRiesgo = "VERDE";
        let etiquetaConductor = "ÓPTIMO";
        let colorClase = "text-success";

        if (indiceFatiga >= 0.75) {
            nivelRiesgo = "ROJO";
            etiquetaConductor = "CRÍTICO";
            colorClase = "text-danger";
        } else if (indiceFatiga >= 0.50) {
            nivelRiesgo = "AMARILLO";
            etiquetaConductor = "PRECAUCIÓN";
            colorClase = "text-warning";
        }

        // Actualizar UI del Conductor
        if (estadoNivelTxt) {
            estadoNivelTxt.textContent = etiquetaConductor;
            estadoNivelTxt.className = `display-6 fw-bold ${colorClase}`;
        }

        if (badgeEstado) {
            if (nivelRiesgo === "ROJO") {
                badgeEstado.textContent = "ALERTA DE FATIGA";
                badgeEstado.className = "badge bg-danger px-3 py-1 fs-6";
            } else if (nivelRiesgo === "AMARILLO") {
                badgeEstado.textContent = "PRECAUCIÓN";
                badgeEstado.className = "badge bg-warning text-dark px-3 py-1 fs-6";
            } else {
                badgeEstado.textContent = "SISTEMA ACTIVO";
                badgeEstado.className = "badge bg-success px-3 py-1 fs-6";
            }
        }

        if (ifProgressBar) {
            const pct = Math.round(indiceFatiga * 100);
            ifProgressBar.style.width = pct + "%";
            if (nivelRiesgo === "ROJO") ifProgressBar.className = "progress-bar bg-danger";
            else if (nivelRiesgo === "AMARILLO") ifProgressBar.className = "progress-bar bg-warning";
            else ifProgressBar.className = "progress-bar bg-success";
        }

        if (hudAlertBanner) {
            if (nivelRiesgo === "ROJO") {
                hudAlertBanner.classList.remove("d-none");
            } else {
                hudAlertBanner.classList.add("d-none");
            }
        }

        // Disparo de Alarma Sonora Progresiva en Cabina (Audible en pruebas y en carretera)
        if (nivelRiesgo === "ROJO") {
            if (tInicioAlarmaCritica === 0) {
                tInicioAlarmaCritica = ahora;
            }
            const duracionEnAlarma = ahora - tInicioAlarmaCritica;

            if (ahora - ultimaAlertaSonora > 0.85) {
                reproducirAlarmaProgresiva(duracionEnAlarma);
                ultimaAlertaSonora = ahora;
            }
        } else {
            tInicioAlarmaCritica = 0;
        }

        // Streaming y Telemetría en Vivo hacia FastAPI
        const ahoraMs = Date.now();
        if (ahoraMs - ultimoEnvioTelemetria >= INTERVALO_ENVIO_MS) {
            ultimoEnvioTelemetria = ahoraMs;

            // Capturar frame comprimido del video + overlay
            const frameSnapshot = capturarFrameSnapshot(video, canvas);

            enviarTelemetriaBackend({
                latitud: latitudActual,
                longitud: longitudActual,
                velocidad_kmh: Math.round(velocidadActualKmh * 10) / 10,
                indice_fatiga_if: Math.round(indiceFatiga * 1000) / 1000,
                perclos_porcentaje: Math.round(perclosPorcentaje * 10) / 10,
                ear: Math.round(ear * 1000) / 1000,
                mar: Math.round(mar * 1000) / 1000,
                frame_b64: frameSnapshot
            });
        }
    }

    /**
     * Captura y comprime el fotograma actual para streaming en vivo ultraliviano
     */
    function capturarFrameSnapshot(video, canvas) {
        try {
            if (!offscreenCanvas) {
                offscreenCanvas = document.createElement("canvas");
                offscreenCanvas.width = 300;
                offscreenCanvas.height = 225;
            }
            const offCtx = offscreenCanvas.getContext("2d");

            // Dibujar video espejado
            offCtx.save();
            offCtx.translate(offscreenCanvas.width, 0);
            offCtx.scale(-1, 1);
            offCtx.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);
            // Dibujar overlay de landmarks
            offCtx.drawImage(canvas, 0, 0, offscreenCanvas.width, offscreenCanvas.height);
            offCtx.restore();

            return offscreenCanvas.toDataURL("image/jpeg", 0.40);
        } catch (e) {
            return null;
        }
    }

    const OFFLINE_STORAGE_KEY = "tc_offline_telemetry_queue";

    function guardarTelemetriaOffline(payload) {
        try {
            // Guardamos datos biométricos y GPS sin el frame_b64 para preservar memoria en móvil
            const payloadLight = Object.assign({}, payload);
            delete payloadLight.frame_b64;
            const queue = JSON.parse(localStorage.getItem(OFFLINE_STORAGE_KEY) || "[]");
            queue.push(payloadLight);
            if (queue.length > 250) queue.shift();
            localStorage.setItem(OFFLINE_STORAGE_KEY, JSON.stringify(queue));
        } catch (e) {
            console.warn("[Cabina] Error guardando offline:", e);
        }
    }

    function sincronizarTelemetriaOffline() {
        try {
            const queue = JSON.parse(localStorage.getItem(OFFLINE_STORAGE_KEY) || "[]");
            if (queue.length > 0 && telemetryWs && telemetryWs.readyState === WebSocket.OPEN) {
                console.log(`[Cabina] Sincronizando ${queue.length} tramas almacenadas offline...`);
                while (queue.length > 0) {
                    const item = queue.shift();
                    telemetryWs.send(JSON.stringify(item));
                }
                localStorage.removeItem(OFFLINE_STORAGE_KEY);
            }
        } catch (e) {
            console.warn("[Cabina] Error sincronizando offline:", e);
        }
    }

    function enviarTelemetriaBackend(datos) {
        if (!config.hoja_id || !config.conductor_id) return;

        const payload = {
            hoja_de_ruta_id: config.hoja_id,
            conductor_id: config.conductor_id,
            latitud: datos.latitud,
            longitud: datos.longitud,
            velocidad_kmh: datos.velocidad_kmh,
            timestamp_captura: new Date().toISOString(),
            indice_fatiga_if: datos.indice_fatiga_if,
            perclos_porcentaje: datos.perclos_porcentaje,
            ear: datos.ear,
            mar: datos.mar,
            frame_b64: enEsperaRelevo ? null : datos.frame_b64
        };

        if (telemetryWs && telemetryWs.readyState === WebSocket.OPEN) {
            telemetryWs.send(JSON.stringify(payload));
            if (!enEsperaRelevo) {
                actualizarIndicadorWs(true, "Al Volante: Transmitiendo en Vivo");
            }
        } else {
            guardarTelemetriaOffline(payload);
            actualizarIndicadorWs(false, "Sin conexión (Guardando datos localmente...)");
        }
    }

    function actualizarIndicadorWs(online, textoPersonalizado) {
        const badgeWs = document.getElementById("cabinaBadgeWs");
        if (!badgeWs) return;
        if (online) {
            badgeWs.textContent = textoPersonalizado || "Conectado al Centro de Monitoreo";
            badgeWs.className = enEsperaRelevo ? "text-warning fw-bold" : "text-success fw-bold";
        } else {
            badgeWs.textContent = textoPersonalizado || "Sin conexión (Guardando datos localmente...)";
            badgeWs.className = "text-warning small";
        }
    }

    function mostrarBannerRelevo(mostrar) {
        const banner = document.getElementById("bannerAlertaRelevoCabina");
        if (banner) {
            if (mostrar) banner.classList.remove("d-none");
            else banner.classList.add("d-none");
        }
    }

    window.asumirRelevoCabina = function() {
        if (!config.hoja_id || !config.conductor_id) return;
        const payload = {
            tipo_evento: "ASUMIR_RELEVO",
            hoja_de_ruta_id: config.hoja_id,
            conductor_id: config.conductor_id
        };
        if (telemetryWs && telemetryWs.readyState === WebSocket.OPEN) {
            telemetryWs.send(JSON.stringify(payload));
        }
        const formData = new FormData();
        formData.append("hoja_de_ruta_id", config.hoja_id);
        formData.append("conductor_id", config.conductor_id);
        fetch('/api/v1/telemetria/asumir-relevo', { method: 'POST', body: formData })
            .then(() => {
                enEsperaRelevo = false;
                mostrarBannerRelevo(false);
                actualizarIndicadorWs(true, "Al Volante: Transmitiendo en Vivo");
            })
            .catch(() => {});
    };

    function conectarWebSocketTelemetria() {
        if (!config.hoja_id) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry/${config.hoja_id}`;

        try {
            telemetryWs = new WebSocket(wsUrl);
            window.telemetryWs = telemetryWs;

            telemetryWs.onopen = () => {
                actualizarIndicadorWs(true);
                sincronizarTelemetriaOffline();
            };

            telemetryWs.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.status === "EN_ESPERA_RELEVO") {
                        enEsperaRelevo = true;
                        mostrarBannerRelevo(true);
                        actualizarIndicadorWs(true, "Cámara en espera: Otro conductor está al volante");
                        const estadoNivelTxt = document.getElementById("conductorEstadoNivel");
                        if (estadoNivelTxt) {
                            estadoNivelTxt.textContent = "EN REPOSO";
                            estadoNivelTxt.className = "display-6 fw-bold text-info";
                        }
                    } else if (msg.status === "RELEVO_CONFIRMADO") {
                        enEsperaRelevo = false;
                        mostrarBannerRelevo(false);
                        actualizarIndicadorWs(true, "Al Volante: Transmitiendo en Vivo");
                    } else if (msg.tipo_evento === "CAMBIO_CONDUCTOR_ACTIVO") {
                        if (String(msg.conductor_activo_id) === String(config.conductor_id)) {
                            enEsperaRelevo = false;
                            mostrarBannerRelevo(false);
                            actualizarIndicadorWs(true, "Al Volante: Transmitiendo en Vivo");
                        } else {
                            enEsperaRelevo = true;
                            mostrarBannerRelevo(true);
                            actualizarIndicadorWs(true, "Modo Reposo: Chofer de Relevo al Volante");
                            const estadoNivelTxt = document.getElementById("conductorEstadoNivel");
                            if (estadoNivelTxt) {
                                estadoNivelTxt.textContent = "EN REPOSO";
                                estadoNivelTxt.className = "display-6 fw-bold text-info";
                            }
                        }
                    }
                } catch (errWs) {
                    console.warn("[Cabina] Error procesando mensaje WS:", errWs);
                }
            };

            telemetryWs.onclose = () => {
                actualizarIndicadorWs(false);
                if (activo) {
                    clearTimeout(wsReconnectionTimer);
                    wsReconnectionTimer = setTimeout(conectarWebSocketTelemetria, 2500);
                }
            };
        } catch (e) {
            console.warn("[Cabina] Excepción al conectar WebSocket:", e);
        }
    }

    function iniciarGpsTracking() {
        if ("geolocation" in navigator) {
            geoWatchId = navigator.geolocation.watchPosition(
                (pos) => {
                    latitudActual = pos.coords.latitude;
                    longitudActual = pos.coords.longitude;
                    if (pos.coords.speed !== null && !isNaN(pos.coords.speed) && pos.coords.speed > 0) {
                        velocidadActualKmh = pos.coords.speed * 3.6; // m/s a km/h
                    } else {
                        velocidadActualKmh = 0.0;
                    }
                    const spanVel = document.getElementById("valCabinaVelocidad");
                    if (spanVel) spanVel.textContent = Math.round(velocidadActualKmh);

                    window.REAL_GPS_COORDS = [latitudActual, longitudActual];
                    if (window.actualizarPosicionGpsConductor) {
                        window.actualizarPosicionGpsConductor(latitudActual, longitudActual, velocidadActualKmh);
                    }
                },
                (err) => {
                    console.warn("[Cabina] Error GPS:", err.message);
                },
                { enableHighAccuracy: true, maximumAge: 2000, timeout: 5000 }
            );
        }
    }

    async function iniciarCabina() {
        const btnIniciar = document.getElementById("btnIniciarCabina");
        const btnDetener = document.getElementById("btnDetenerCabina");
        const video = document.getElementById("cabinaVideo");
        const canvas = document.getElementById("cabinaOverlay");
        const badgeEstado = document.getElementById("cabinaBadgeEstado");

        if (btnIniciar) btnIniciar.disabled = true;

        try {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') await audioCtx.resume();

            // Desbloqueo definitivo de Web Audio para navegadores móviles (Chrome/Safari en Android/iOS)
            try {
                const unlockBuffer = audioCtx.createBuffer(1, 1, 22050);
                const unlockSource = audioCtx.createBufferSource();
                unlockSource.buffer = unlockBuffer;
                unlockSource.connect(audioCtx.destination);
                unlockSource.start(0);
            } catch (eUnlock) {
                console.warn("[Cabina] Advertencia al desbloquear audio móvil:", eUnlock);
            }

            if (badgeEstado) {
                badgeEstado.textContent = "INICIALIZANDO IA...";
                badgeEstado.className = "badge bg-info text-dark px-3 py-1 fs-6";
            }

            await inicializarMediaPipeModulos();

            const selCamara = document.getElementById("cabinaSelCamara")?.value || "user";
            stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: selCamara
                },
                audio: false
            });

            video.srcObject = stream;
            await new Promise(res => video.onloadedmetadata = res);
            await video.play();

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            // Resetear contadores
            dormindo = false;
            tiempoCierreActual = 0;
            tInicioAlarmaCritica = 0;
            contagemPiscadas = 0;
            contagemTemporaria = 0;
            contagemLista = [];
            cTempo = 0;
            perclosBuffer.length = 0;
            tInicioSesion = performance.now() / 1000;

            activo = true;
            if (btnDetener) btnDetener.disabled = false;
            if (badgeEstado) {
                badgeEstado.textContent = "SISTEMA ACTIVO";
                badgeEstado.className = "badge bg-success px-3 py-1 fs-6";
            }

            conectarWebSocketTelemetria();
            iniciarGpsTracking();
            loop();

        } catch (err) {
            console.error("[Cabina] Error:", err);
            let mensaje = "No se pudo acceder a la cámara";
            if (err.name === "NotAllowedError") mensaje = "Permiso de cámara denegado";
            if (badgeEstado) {
                badgeEstado.textContent = mensaje;
                badgeEstado.className = "badge bg-danger px-3 py-1 fs-6";
            }
            if (btnIniciar) btnIniciar.disabled = false;
        }
    }

    function detenerCabina() {
        activo = false;
        if (animFrameId) cancelAnimationFrame(animFrameId);
        if (stream) {
            stream.getTracks().forEach(t => t.stop());
            stream = null;
        }

        const video = document.getElementById("cabinaVideo");
        const canvas = document.getElementById("cabinaOverlay");
        if (video) video.srcObject = null;
        if (canvas) {
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        if (geoWatchId) {
            navigator.geolocation.clearWatch(geoWatchId);
            geoWatchId = null;
        }

        if (telemetryWs) {
            try {
                if (telemetryWs.readyState === WebSocket.OPEN) {
                    telemetryWs.send(JSON.stringify({
                        tipo_evento: "LIBERAR_VOLANTE",
                        hoja_de_ruta_id: config.hoja_id,
                        conductor_id: config.conductor_id
                    }));
                }
            } catch (eLib) {}
            telemetryWs.close();
            telemetryWs = null;
            window.telemetryWs = null;
        }
        enEsperaRelevo = false;
        mostrarBannerRelevo(false);
        actualizarIndicadorWs(false);

        const btnIniciar = document.getElementById("btnIniciarCabina");
        const btnDetener = document.getElementById("btnDetenerCabina");
        const badgeEstado = document.getElementById("cabinaBadgeEstado");
        const hudAlertBanner = document.getElementById("cabinaHudAlert");
        const estadoNivelTxt = document.getElementById("conductorEstadoNivel");

        if (btnIniciar) btnIniciar.disabled = false;
        if (btnDetener) btnDetener.disabled = true;
        if (badgeEstado) {
            badgeEstado.textContent = "CÁMARA APAGADA";
            badgeEstado.className = "badge bg-secondary px-3 py-1 fs-6";
        }
        if (estadoNivelTxt) {
            estadoNivelTxt.textContent = "DESPEJADO";
            estadoNivelTxt.className = "display-6 fw-bold text-secondary";
        }
        if (hudAlertBanner) hudAlertBanner.classList.add("d-none");
    }

    document.addEventListener("DOMContentLoaded", () => {
        const btnIniciar = document.getElementById("btnIniciarCabina");
        const btnDetener = document.getElementById("btnDetenerCabina");

        if (btnIniciar) btnIniciar.addEventListener("click", iniciarCabina);
        if (btnDetener) btnDetener.addEventListener("click", detenerCabina);

        // Iniciar rastreo GPS del celular en segundo plano para el mapa
        iniciarGpsTracking();

        // Escuchar reconexión a Internet para sincronizar tramas offline
        window.addEventListener("online", sincronizarTelemetriaOffline);

        window.addEventListener("beforeunload", detenerCabina);
    });

})();
