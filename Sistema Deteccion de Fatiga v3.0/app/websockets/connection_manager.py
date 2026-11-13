import json
from typing import Dict, Set, List, Any
from uuid import UUID
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Conexiones de operadores en el Dashboard de Monitoreo
        self.dashboard_connections: Set[WebSocket] = set()
        
        # Conexiones de telemetría por cada Hoja de Ruta activa
        self.telemetry_connections: Dict[str, Set[WebSocket]] = {}
        
        # Caché en memoria de la última posición conocida de cada bus activo
        # Clave: str(hoja_de_ruta_id) -> Valor: BusSnapshot dict
        self.latest_fleet_snapshots: Dict[str, Dict[str, Any]] = {}

        # Conductor activo al volante por Hoja de Ruta (Exclusividad de Cámara)
        # Clave: str(hoja_de_ruta_id) -> Valor: str(conductor_id)
        self.active_driver_by_hoja: Dict[str, str] = {}

    async def connect_dashboard(self, websocket: WebSocket):
        await websocket.accept()
        self.dashboard_connections.add(websocket)
        # Enviar inmediatamente el snapshot actual de la flota activa
        initial_data = {
            "tipo_evento": "SNAPSHOT_INICIAL",
            "buses": list(self.latest_fleet_snapshots.values())
        }
        await websocket.send_json(initial_data)

    def disconnect_dashboard(self, websocket: WebSocket):
        self.dashboard_connections.discard(websocket)

    async def connect_telemetry(self, hoja_id: str, websocket: WebSocket):
        await websocket.accept()
        if hoja_id not in self.telemetry_connections:
            self.telemetry_connections[hoja_id] = set()
        self.telemetry_connections[hoja_id].add(websocket)

    def disconnect_telemetry(self, hoja_id: str, websocket: WebSocket):
        if hoja_id in self.telemetry_connections:
            self.telemetry_connections[hoja_id].discard(websocket)
            if not self.telemetry_connections[hoja_id]:
                del self.telemetry_connections[hoja_id]

    async def broadcast_to_dashboard(self, message: Dict[str, Any]):
        """
        Emite un mensaje JSON a todas las pantallas de monitoreo activas.
        Remueve automáticamente cualquier conexión muerta.
        """
        dead_connections = set()
        for connection in list(self.dashboard_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)
        
        for dead in dead_connections:
            self.dashboard_connections.discard(dead)

    async def send_to_telemetry(self, hoja_id: str, message: Dict[str, Any]):
        """
        Envía un comando o acuse de recibo al bus correspondiente.
        """
        connections = self.telemetry_connections.get(hoja_id, set())
        for connection in list(connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass

    def update_snapshot(self, hoja_id: str, snapshot_data: Dict[str, Any]):
        self.latest_fleet_snapshots[hoja_id] = snapshot_data

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        return list(self.latest_fleet_snapshots.values())

    def get_active_driver(self, hoja_id: str):
        return self.active_driver_by_hoja.get(str(hoja_id))

    def set_active_driver(self, hoja_id: str, conductor_id: str):
        self.active_driver_by_hoja[str(hoja_id)] = str(conductor_id)

    def release_driver(self, hoja_id: str, conductor_id: str):
        if self.active_driver_by_hoja.get(str(hoja_id)) == str(conductor_id):
            del self.active_driver_by_hoja[str(hoja_id)]

# Instancia singleton para toda la aplicación
manager = ConnectionManager()
