"""
Servicio y Catálogo Canónico de Rutas Oficiales y Terminales de Bolivia
Basado en la Red Vial Fundamental de la Administradora Boliviana de Carreteras (ABC)
y Regulaciones de Transporte Interdepartamental de la ATT.
"""

from typing import Dict, List, Optional, Tuple, Any

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

# Coordenadas geográficas oficiales de las terminales de buses de Bolivia
COORDENADAS_TERMINALES: Dict[str, Tuple[float, float]] = {
    # La Paz
    "Terminal de Buses La Paz": (-16.4883, -68.1408),
    "Terminal Minasa": (-16.4789, -68.1189),
    # Cochabamba
    "Terminal de Buses Cochabamba": (-17.4042, -66.1583),
    # Santa Cruz
    "Terminal Bimodal Santa Cruz": (-17.7833, -63.1583),
    # Oruro
    "Terminal de Buses Oruro (Hernando Siles)": (-17.9667, -67.1167),
    "Nueva Terminal de Buses Oruro": (-17.9355, -67.0986),
    # Sucre
    "Terminal Interdepartamental Sucre": (-19.0333, -65.2627),
    # Potosí
    "Terminal de Buses Potosí": (-19.5836, -65.7531),
    # Tarija
    "Terminal de Buses Tarija (Torrecillas)": (-21.5355, -64.7296),
    # Trinidad
    "Terminal de Buses Trinidad": (-14.8333, -64.9000),
    # Cobija
    "Terminal de Buses Cobija": (-11.0267, -68.7692)
}

# Coordenadas geográficas oficiales de las terminales/ciudades principales de Bolivia
COORDENADAS_CIUDADES: Dict[str, Tuple[float, float]] = {
    "La Paz": (-16.4883, -68.1408),
    "Cochabamba": (-17.4042, -66.1583),
    "Santa Cruz": (-17.7833, -63.1583),
    "Oruro": (-17.9667, -67.1167),
    "Sucre": (-19.0333, -65.2627),
    "Potosí": (-19.5836, -65.7531),
    "Tarija": (-21.5355, -64.7296),
    "Trinidad": (-14.8333, -64.9000),
    "Cobija": (-11.0267, -68.7692)
}

# Trazados oficiales georreferenciados según la Red Vial Fundamental de la ABC
# Formato: lista de coordenadas [latitud, longitud] que siguen la carretera real
TRAZADOS_OFICIALES_RED_VIAL: Dict[str, List[List[float]]] = {
    "Cochabamba->La Paz": [
        [-17.4042, -66.1583], [-17.3930, -66.2790], [-17.3970, -66.3190],
        [-17.4410, -66.3680], [-17.5500, -66.3450], [-17.6580, -66.5050],
        [-17.6830, -66.6230], [-17.7120, -66.7500], [-17.7500, -66.8600],
        [-17.7330, -67.0500], [-17.6330, -67.2170], [-17.4500, -67.4330],
        [-17.3800, -67.5500], [-17.3330, -67.7330], [-17.2330, -67.9170],
        [-16.9000, -68.1170], [-16.5500, -68.1800], [-16.5000, -68.1600],
        [-16.4883, -68.1408]
    ],
    "Cochabamba->Santa Cruz": [
        [-17.4042, -66.1583], [-17.4040, -66.0410], [-17.3400, -65.8600],
        [-17.1500, -65.7500], [-16.9730, -65.4200], [-16.9980, -65.2500],
        [-16.9900, -65.1300], [-17.0300, -64.8600], [-17.2500, -64.3500],
        [-17.4000, -63.8800], [-17.3500, -63.3900], [-17.3400, -63.2500],
        [-17.5100, -63.1600], [-17.7833, -63.1821]
    ],
    "La Paz->Oruro": [
        [-16.4883, -68.1408], [-16.5500, -68.1800], [-16.9000, -68.1170],
        [-17.2330, -67.9170], [-17.3330, -67.7330], [-17.3800, -67.5500],
        [-17.4500, -67.4330], [-17.6330, -67.2170], [-17.7500, -67.1500],
        [-17.9667, -67.1167]
    ],
    "Cochabamba->Oruro": [
        [-17.4042, -66.1583], [-17.3930, -66.2790], [-17.4410, -66.3680],
        [-17.5500, -66.3450], [-17.6830, -66.6230], [-17.7500, -66.8600],
        [-17.6330, -67.2170], [-17.7500, -67.1500], [-17.9667, -67.1167]
    ],
    "Oruro->Potosí": [
        [-17.9667, -67.1167], [-18.1500, -67.0500], [-18.3800, -66.9600],
        [-18.5500, -66.9000], [-18.9000, -66.7700], [-19.2000, -66.3500],
        [-19.4500, -66.0000], [-19.5836, -65.7531]
    ],
    "Potosí->Sucre": [
        [-19.5836, -65.7531], [-19.5000, -65.6500], [-19.3500, -65.5000],
        [-19.2000, -65.3800], [-19.0333, -65.2627]
    ],
    "Potosí->Tarija": [
        [-19.5836, -65.7531], [-19.7800, -65.7000], [-20.1500, -65.5000],
        [-20.6500, -65.2000], [-21.0500, -65.0000], [-21.3500, -64.8500],
        [-21.5355, -64.7296]
    ],
    "La Paz->Santa Cruz": [
        [-16.4883, -68.1408], [-16.5000, -68.1600], [-16.5500, -68.1800],
        [-16.9000, -68.1170], [-17.2330, -67.9170], [-17.3330, -67.7330],
        [-17.3800, -67.5500], [-17.4500, -67.4330], [-17.6330, -67.2170],
        [-17.7330, -67.0500], [-17.7500, -66.8600], [-17.7120, -66.7500],
        [-17.6830, -66.6230], [-17.6580, -66.5050], [-17.5500, -66.3450],
        [-17.4410, -66.3680], [-17.3970, -66.3190], [-17.3930, -66.2790],
        [-17.4042, -66.1583], [-17.4040, -66.0410], [-17.3400, -65.8600],
        [-17.1500, -65.7500], [-16.9730, -65.4200], [-16.9980, -65.2500],
        [-16.9900, -65.1300], [-17.0300, -64.8600], [-17.2500, -64.3500],
        [-17.4000, -63.8800], [-17.3500, -63.3900], [-17.3400, -63.2500],
        [-17.5100, -63.1600], [-17.7833, -63.1583]
    ]
}

def normalizar_ciudad(ciudad: str) -> str:
    c = (ciudad or "").strip().title()
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

def get_coordenadas_terminal(ciudad: Optional[str] = None, terminal: Optional[str] = None) -> Tuple[float, float]:
    """Obtiene las coordenadas GPS exactas de una terminal específica o de la ciudad."""
    if terminal:
        t_clean = terminal.strip()
        if t_clean in COORDENADAS_TERMINALES:
            return COORDENADAS_TERMINALES[t_clean]
        # Búsqueda por coincidencia parcial insensible a mayúsculas
        t_lower = t_clean.lower()
        for k, v in COORDENADAS_TERMINALES.items():
            if t_lower in k.lower() or k.lower() in t_lower:
                return v
    if ciudad:
        return get_coordenadas_ciudad(ciudad)
    return (-17.4042, -66.1583)

def calcular_ruta_oficial(origen: str, destino: str) -> Dict[str, Any]:
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
    
    return {
        "distancia_km": 400.0,
        "duracion_estimada_hrs": 8.0,
        "es_oficial": False
    }

def get_trazado_oficial(
    origen: str, 
    destino: str, 
    origen_terminal: Optional[str] = None, 
    destino_terminal: Optional[str] = None
) -> List[List[float]]:
    c1 = normalizar_ciudad(origen)
    c2 = normalizar_ciudad(destino)

    key_direct = f"{c1}->{c2}"
    key_reverse = f"{c2}->{c1}"

    p_inicio = list(get_coordenadas_terminal(c1, origen_terminal))
    p_fin = list(get_coordenadas_terminal(c2, destino_terminal))

    if key_direct in TRAZADOS_OFICIALES_RED_VIAL:
        puntos = [p_inicio] + [p for p in TRAZADOS_OFICIALES_RED_VIAL[key_direct]] + [p_fin]
        return puntos
    elif key_reverse in TRAZADOS_OFICIALES_RED_VIAL:
        puntos = [p_inicio] + [p for p in reversed(TRAZADOS_OFICIALES_RED_VIAL[key_reverse])] + [p_fin]
        return puntos

    # Fallback con coordenadas oficiales terminales origen y destino
    return [p_inicio, p_fin]
