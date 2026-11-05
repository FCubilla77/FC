# -*- coding: utf-8 -*-
"""Funciones puras (sin Odoo) del módulo de recepción de facturas.

Se mantienen aparte para poder probarlas sin una base de datos:
  * cálculo de precio y descuento de una línea,
  * elección del término de pago de Odoo más cercano a la condición del XML,
  * comparación de unidades de medida.
"""

import re
from decimal import ROUND_HALF_UP, Decimal


# ---------------------------------------------------------------------------
# Precio y descuento de una línea
# ---------------------------------------------------------------------------
def calcular_precio_descuento(precio, cantidad, total_item, pct_xml=None, redondeo=Decimal('1')):
    """Devuelve (precio_unitario, descuento_pct) para cargar la línea en Odoo.

    El XML trae el precio unitario, un descuento por ítem y el total de la
    línea (dTotOpeItem). Odoo guarda el descuento como un porcentaje con 2
    decimales, así que no siempre puede reproducir el total exacto. Orden:

      1. sin descuento, si precio x cantidad ya da el total;
      2. con el porcentaje del XML (o el derivado de los importes), si
         redondeado a 2 decimales reproduce el total de la línea;
      3. si no, precio unitario neto y descuento 0, para que el total de la
         línea sea el del XML.

    `redondeo` es la unidad de redondeo de la moneda (1 en PYG, 0.01 en USD):
    el resultado se acepta si se desvía menos de la mitad de esa unidad.
    """
    precio = Decimal(precio)
    cantidad = Decimal(cantidad)
    redondeo = Decimal(redondeo)
    tolerancia = redondeo / 2
    if cantidad == 0 or precio == 0:
        return precio, Decimal(0)
    bruto = precio * cantidad
    total = bruto if total_item is None else Decimal(total_item)
    if abs(bruto - total) <= tolerancia:
        return precio, Decimal(0)

    candidatos = []
    if pct_xml is not None and Decimal(pct_xml) > 0:
        candidatos.append(Decimal(pct_xml))
    candidatos.append((1 - total / bruto) * 100)
    for pct in candidatos:
        pct = pct.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if abs(bruto * (1 - pct / 100) - total) <= tolerancia:
            return precio, pct
    return total / cantidad, Decimal(0)


# ---------------------------------------------------------------------------
# Término de pago más cercano a la condición del XML
# ---------------------------------------------------------------------------
def dias_de_plazo(texto):
    """'30 días' -> 30, '12 meses' -> 360, '28' -> 28. None si no hay número."""
    if not texto:
        return None
    coincidencia = re.search(r'(\d+)', texto)
    if not coincidencia:
        return None
    cantidad = int(coincidencia.group(1))
    minusculas = texto.lower()
    if 'mes' in minusculas:
        return cantidad * 30
    if 'año' in minusculas or 'ano' in minusculas:
        return cantidad * 365
    return cantidad


def perfil_xml(condicion, plazo_texto, cuotas, fecha_emision):
    """Lista de días de pago que describe el XML.

    Contado -> [0]. Crédito por plazo -> [días]. Crédito por cuotas -> los
    días de cada vencimiento contados desde la emisión (None si la cuota no
    trae fecha). Crédito sin plazo ni cuotas -> [].
    """
    if condicion != 2:
        return [0]
    if cuotas:
        dias = []
        for cuota in cuotas:
            vencimiento = cuota.get('vencimiento')
            if vencimiento and fecha_emision:
                dias.append((vencimiento - fecha_emision).days)
            else:
                dias.append(None)
        return dias
    plazo = dias_de_plazo(plazo_texto)
    return [plazo] if plazo is not None else []


def elegir_termino(perfil, terminos):
    """Elige el término de pago cuyo perfil de días más se acerca al del XML.

    `terminos`: lista de (id, [días de cada línea]) en el orden de preferencia
    (el primero gana los empates). Devuelve el id o None.

      * Contado: un término de una línea sin demora.
      * Plazo: un término de una línea, con el plazo más cercano.
      * Cuotas: uno con la misma cantidad de líneas y vencimientos más
        cercanos; si no hay, el que tenga más líneas pero la menor cantidad.
    """
    if not perfil:
        return None
    n = len(perfil)
    if n == 1:
        dia = perfil[0]
        de_una_linea = [t for t in terminos if len(t[1]) == 1]
        if dia == 0:
            for termino in de_una_linea:
                if termino[1][0] == 0:
                    return termino[0]
            return None
        if dia is None:
            return None
        con_plazo = [t for t in de_una_linea if t[1][0] > 0]
        if not con_plazo:
            return None
        return min(con_plazo, key=lambda t: abs(t[1][0] - dia))[0]

    candidatos = [t for t in terminos if len(t[1]) == n]
    if not candidatos:
        mayores = [t for t in terminos if len(t[1]) > n]
        if not mayores:
            return None
        menor = min(len(t[1]) for t in mayores)
        candidatos = [t for t in mayores if len(t[1]) == menor]

    conocidos = [d for d in perfil if d is not None]

    def puntaje(termino):
        if len(conocidos) != n:
            return 0
        return sum(abs(a - b) for a, b in zip(sorted(termino[1]), sorted(conocidos)))

    return min(candidatos, key=puntaje)[0]


def describir_perfil(dias):
    """Texto corto de un perfil de días, para mostrarlo al usuario."""
    if not dias:
        return 'sin condición informada'
    if len(dias) == 1:
        if dias[0] == 0:
            return 'contado'
        return 'a %s días' % dias[0] if dias[0] is not None else 'a plazo'
    detalle = '/'.join(str(d) if d is not None else '?' for d in dias)
    return '%s cuotas (%s días)' % (len(dias), detalle)


# ---------------------------------------------------------------------------
# Unidades de medida
# ---------------------------------------------------------------------------
_GRUPOS_UNIDAD = {
    'unidad': {'uni', 'unidad', 'unidades', 'unit', 'units', 'u', 'und', 'un'},
    'kg': {'kg', 'kilogramo', 'kilogramos', 'kilo', 'kilos'},
    'g': {'g', 'gr', 'gramo', 'gramos'},
    'litro': {'lt', 'l', 'litro', 'litros', 'liter', 'liters'},
    'ml': {'ml', 'mililitro', 'mililitros'},
    'metro': {'m', 'mt', 'metro', 'metros'},
    'cm': {'cm', 'centimetro', 'centimetros', 'centímetro', 'centímetros'},
    'm2': {'m2', 'm²', 'metro cuadrado', 'metros cuadrados'},
    'm3': {'m3', 'm³', 'metro cubico', 'metros cubicos', 'metro cúbico', 'metros cúbicos'},
    'hora': {'hs', 'h', 'hora', 'horas', 'hour', 'hours'},
    'dia': {'di', 'dia', 'día', 'dias', 'días', 'day', 'days'},
}


def grupo_unidad(texto):
    """Familia de una unidad ('UNI', 'Units' -> 'unidad'), o None si no se conoce."""
    normalizado = (texto or '').strip().lower().replace('.', '')
    for grupo, nombres in _GRUPOS_UNIDAD.items():
        if normalizado in nombres:
            return grupo
    return None


def unidades_distintas(unidad_xml, unidad_odoo):
    """True solo si ambas son conocidas y son de familias distintas."""
    g_xml = grupo_unidad(unidad_xml)
    g_odoo = grupo_unidad(unidad_odoo)
    return bool(g_xml and g_odoo and g_xml != g_odoo)
