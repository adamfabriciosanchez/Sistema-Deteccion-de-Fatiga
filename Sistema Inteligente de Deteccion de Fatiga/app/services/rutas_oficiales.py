"""
Servicio y Catálogo Canónico de Rutas Oficiales y Terminales de Bolivia
Basado en la Red Vial Fundamental de la Administradora Boliviana de Carreteras (ABC)
y Regulaciones de Transporte Interdepartamental de la ATT.
"""

from typing import Dict, List, Optional, Tuple

TERMINALES_POR_CIUDAD: Dict[str, List[str]] = {
    "La Paz": [
        "Terminal de Buses La Paz",
        "Terminal Minasa"
    ],
    "Cochabamba": [
        "Terminal de Buses Cochabamba"
    ],
    "Santa Cruz": [
        "Terminal Bimodal Santa Cruz"
    ],
    "Oruro": [
        "Terminal de Buses Oruro (Hernando Siles)",
        "Nueva Terminal de Buses Oruro"
    ],
    "Sucre": [
        "Terminal Interdepartamental Sucre"
    ],
    "Potosí": [
        "Terminal de Buses Potosí"
    ],
    "Tarija": [
        "Terminal de Buses Tarija (Torrecillas)"
    ],
    "Trinidad": [
        "Terminal de Buses Trinidad"
    ],
    "Cobija": [
        "Terminal de Buses Cobija"
    ]
}

# Matriz Oficial de Rutas Interdepartamentales de Bolivia
# Clave: tuple normalizada alfabéticamente (ciudad_a, ciudad_b)
# Valor: (distancia_km, duracion_estimada_hrs)
MATRIZ_RUTAS_OFICIALES: Dict[Tuple[str, str], Tuple[float, float]] = {
    # Eje Troncal y Conexiones Principales
    ("Cochabamba", "La Paz"): (380.0, 7.5),
    ("Cochabamba", "Santa Cruz"): (480.0, 9.5),
    ("La Paz", "Santa Cruz"): (860.0, 17.0),
    ("La Paz", "Oruro"): (225.0, 3.5),
    ("Cochabamba", "Oruro"): (215.0, 4.0),
    ("Cochabamba", "Sucre"): (360.0, 8.0),
    ("Potosí", "Sucre"): (160.0, 3.0),
    ("Oruro", "Potosí"): (310.0, 5.0),
    ("La Paz", "Potosí"): (535.0, 9.0),
    ("Santa Cruz", "Sucre"): (500.0, 11.0),
    ("Santa Cruz", "Trinidad"): (550.0, 9.0),
    ("Potosí", "Tarija"): (345.0, 7.0),
    ("Cochabamba", "Tarija"): (690.0, 13.0),
    ("La Paz", "Tarija"): (910.0, 15.0),
    ("Oruro", "Tarija"): (655.0, 11.5),
    ("Santa Cruz", "Tarija"): (680.0, 12.0),
    ("Sucre", "Tarija"): (470.0, 9.5)
}

# Coordenadas geográficas oficiales de las terminales/ciudades principales de Bolivia
COORDENADAS_CIUDADES: Dict[str, Tuple[float, float]] = {
    "La Paz": (-16.4883, -68.1408),
    "Cochabamba": (-17.4042, -66.1583),
    "Santa Cruz": (-17.7833, -63.1821),
    "Oruro": (-17.9667, -67.1167),
    "Sucre": (-19.0333, -65.2627),
    "Potosí": (-19.5836, -65.7531),
    "Tarija": (-21.5355, -64.7296),
    "Trinidad": (-14.8333, -64.9000),
    "Cobija": (-11.0267, -68.7692)
}

def normalizar_ciudad(ciudad: str) -> str:
    c = ciudad.strip().title()
    # Normalizaciones comunes
    if c.lower() in ["la paz", "lapaz"]:
        return "La Paz"
    if c.lower() in ["santa cruz", "santacruz", "santa cruz de la sierra"]:
        return "Santa Cruz"
    if c.lower() in ["potosi", "potosí"]:
        return "Potosí"
    return c

def get_terminales_ciudad(ciudad: str) -> List[str]:
    c_norm = normalizar_ciudad(ciudad)
    return TERMINALES_POR_CIUDAD.get(c_norm, [f"Terminal de Buses {c_norm}"])

def get_coordenadas_ciudad(ciudad: str) -> Tuple[float, float]:
    c_norm = normalizar_ciudad(ciudad)
    return COORDENADAS_CIUDADES.get(c_norm, (-17.4042, -66.1583))

def calcular_ruta_oficial(origen: str, destino: str) -> Dict[str, float]:
    """
    Retorna la distancia oficial en km y la duración estimada en horas según la ABC/ATT.
    Si no existe trayecto directo en la matriz, calcula una estimación prudente.
    """
    c1 = normalizar_ciudad(origen)
    c2 = normalizar_ciudad(destino)

    par = tuple(sorted([c1, c2]))
    if par in MATRIZ_RUTAS_OFICIALES:
        distancia, duracion = MATRIZ_RUTAS_OFICIALES[par]
        return {
            "distancia_km": distancia,
            "duracion_estimada_hrs": duracion,
            "es_oficial": True
        }
    
    # Fallback si no está directamente en la tabla
    return {
        "distancia_km": 400.0,
        "duracion_estimada_hrs": 8.0,
        "es_oficial": False
    }
