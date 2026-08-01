# -*- coding: utf-8 -*-

UNIDADES = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
DIEZ_A_DIECINUEVE = [
    'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete',
    'dieciocho', 'diecinueve',
]
DECENAS = [
    '', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta',
    'ochenta', 'noventa',
]
CENTENAS = [
    '', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
    'seiscientos', 'setecientos', 'ochocientos', 'novecientos',
]


def _bloque_menor_1000(n):
    if n == 0:
        return ''
    if n == 100:
        return 'cien'
    texto = ''
    centena, resto = divmod(n, 100)
    if centena:
        texto += CENTENAS[centena]
    if resto:
        if texto:
            texto += ' '
        if resto < 10:
            texto += UNIDADES[resto]
        elif resto < 20:
            texto += DIEZ_A_DIECINUEVE[resto - 10]
        else:
            decena, unidad = divmod(resto, 10)
            texto += DECENAS[decena]
            if unidad:
                texto += ' y ' + UNIDADES[unidad]
    return texto


def numero_a_letras(numero):
    """Convierte un número entero (positivo) a su expresión en letras, en
    español. Pensado para montos en Guaraníes (sin decimales); para otras
    monedas, el importe ya viene redondeado a entero antes de llamar a
    esta función."""
    numero = int(round(numero))
    if numero == 0:
        return 'cero'

    millones, resto_millones = divmod(numero, 1000000)
    miles, resto = divmod(resto_millones, 1000)

    partes = []
    if millones:
        if millones == 1:
            partes.append('un millón')
        else:
            partes.append('%s millones' % _bloque_menor_1000(millones))
    if miles:
        if miles == 1:
            partes.append('mil')
        else:
            partes.append('%s mil' % _bloque_menor_1000(miles))
    if resto:
        partes.append(_bloque_menor_1000(resto))

    texto = ' '.join(partes).strip()
    return texto[0].upper() + texto[1:] if texto else 'Cero'
