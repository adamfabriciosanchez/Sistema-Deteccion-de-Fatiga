"""
Módulo de Métodos Numéricos y Estimación de Telemetría
Trans Copacabana S.A.

Implementación de algoritmos de interpolación polinomial:
- Interpolación de Newton hacia Adelante (Forward Differences)
- Interpolación de Newton hacia Atrás (Backward Differences)
- Interpolación Lineal (Grado 1)

Aplicado a la reconstrucción y auditoría de series temporales de fatiga (IF y PERCLOS)
en rutas interdepartamentales con pérdida o baches de señal GPS/4G.
"""

from typing import List, Dict, Tuple, Any
import math

def calcular_diferencias_adelante(y: List[float]) -> List[List[float]]:
    """
    Construye la tabla de diferencias finitas hacia adelante:
    delta[k][i] = delta[k-1][i+1] - delta[k-1][i]
    """
    n = len(y)
    tabla: List[List[float]] = []
    tabla.append([round(val, 4) for val in y])
    
    for k in range(1, n):
        fila: List[float] = []
        for i in range(n - k):
            diff = tabla[k - 1][i + 1] - tabla[k - 1][i]
            fila.append(round(diff, 4))
        tabla.append(fila)
    return tabla


def calcular_diferencias_atras(y: List[float]) -> List[List[float]]:
    """
    Construye la tabla de diferencias finitas hacia atrás:
    nabla[k][i] = nabla[k-1][i] - nabla[k-1][i-1]
    """
    n = len(y)
    tabla: List[List[float]] = []
    tabla.append([round(val, 4) for val in y])
    
    for k in range(1, n):
        fila: List[float] = []
        for i in range(k, n):
            # En la tabla de orden k-1, los indices corresponden
            diff = tabla[k - 1][i - k + 1] - tabla[k - 1][i - k]
            fila.append(round(diff, 4))
        tabla.append(fila)
    return tabla


def interpolar_newton_adelante(x: List[float], y: List[float], t: float) -> Dict[str, Any]:
    """
    Evalúa el Polinomio de Newton hacia adelante en el punto t.
    P_n(t) = y0 + s*Delta(y0) + s(s-1)/2! * Delta^2(y0) + ...
    Donde s = (t - x0) / h.
    """
    n = len(x)
    if n < 2:
        return {"error": "Se requieren al menos 2 puntos para interpolar."}
    
    h = x[1] - x[0]
    if abs(h) < 1e-7:
        return {"error": "El paso h no puede ser cero."}
    
    s = (t - x[0]) / h
    tabla_delta = calcular_diferencias_adelante(y)
    
    resultado = tabla_delta[0][0]
    terminos_detallados = [{"termino": 0, "coeficiente": tabla_delta[0][0], "producto_s": 1.0, "valor": tabla_delta[0][0]}]
    
    factor_s = 1.0
    factorial = 1
    
    for k in range(1, n):
        factor_s *= (s - (k - 1))
        factorial *= k
        delta_k = tabla_delta[k][0]
        term_val = (delta_k * factor_s) / factorial
        resultado += term_val
        terminos_detallados.append({
            "termino": k,
            "coeficiente": delta_k,
            "producto_s": round(factor_s, 4),
            "factorial": factorial,
            "valor": round(term_val, 4)
        })
        
    resultado_clamped = max(0.0, min(1.0, resultado))
    return {
        "metodo": "Newton hacia Adelante",
        "t": t,
        "x0": x[0],
        "h": round(h, 4),
        "s": round(s, 4),
        "resultado": round(resultado_clamped, 4),
        "resultado_raw": round(resultado, 4),
        "tabla_diferencias": tabla_delta,
        "terminos": terminos_detallados
    }


def interpolar_newton_atras(x: List[float], y: List[float], t: float) -> Dict[str, Any]:
    """
    Evalúa el Polinomio de Newton hacia atrás en el punto t.
    P_n(t) = yn + s*Nabla(yn) + s(s+1)/2! * Nabla^2(yn) + ...
    Donde s = (t - xn) / h.
    """
    n = len(x)
    if n < 2:
        return {"error": "Se requieren al menos 2 puntos para interpolar."}
    
    h = x[1] - x[0]
    if abs(h) < 1e-7:
        return {"error": "El paso h no puede ser cero."}
    
    xn = x[-1]
    yn = y[-1]
    s = (t - xn) / h
    tabla_delta = calcular_diferencias_adelante(y)
    
    # En diferencias hacia atrás, los coeficientes del extremo final corresponden a los últimos elementos de cada fila
    resultado = yn
    terminos_detallados = [{"termino": 0, "coeficiente": yn, "producto_s": 1.0, "valor": yn}]
    
    factor_s = 1.0
    factorial = 1
    
    for k in range(1, n):
        factor_s *= (s + (k - 1))
        factorial *= k
        nabla_k = tabla_delta[k][-1]  # Último elemento de la fila de orden k
        term_val = (nabla_k * factor_s) / factorial
        resultado += term_val
        terminos_detallados.append({
            "termino": k,
            "coeficiente": nabla_k,
            "producto_s": round(factor_s, 4),
            "factorial": factorial,
            "valor": round(term_val, 4)
        })
        
    resultado_clamped = max(0.0, min(1.0, resultado))
    return {
        "metodo": "Newton hacia Atrás",
        "t": t,
        "xn": xn,
        "h": round(h, 4),
        "s": round(s, 4),
        "resultado": round(resultado_clamped, 4),
        "resultado_raw": round(resultado, 4),
        "tabla_diferencias": tabla_delta,
        "terminos": terminos_detallados
    }


def interpolar_lineal(x: List[float], y: List[float], t: float) -> Dict[str, Any]:
    """
    Interpolación lineal simple en el intervalo [x_k, x_{k+1}] que contiene a t.
    """
    n = len(x)
    if n < 2:
        return {"error": "Se requieren al menos 2 puntos."}
    
    # Encontrar intervalo
    idx = 0
    if t <= x[0]:
        idx = 0
    elif t >= x[-1]:
        idx = n - 2
    else:
        for i in range(n - 1):
            if x[i] <= t <= x[i + 1]:
                idx = i
                break
                
    x0, x1 = x[idx], x[idx + 1]
    y0, y1 = y[idx], y[idx + 1]
    
    if abs(x1 - x0) < 1e-7:
        pendiente = 0.0
    else:
        pendiente = (y1 - y0) / (x1 - x0)
        
    resultado = y0 + pendiente * (t - x0)
    resultado_clamped = max(0.0, min(1.0, resultado))
    
    return {
        "metodo": "Interpolación Lineal",
        "t": t,
        "intervalo": [x0, x1],
        "valores": [y0, y1],
        "pendiente": round(pendiente, 4),
        "resultado": round(resultado_clamped, 4),
        "resultado_raw": round(resultado, 4)
    }

