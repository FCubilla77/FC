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


# ---------------------------------------------------------------------------
# Equivalencias de productos del proveedor
# ---------------------------------------------------------------------------
def normalizar_clave(texto):
    """Clave de comparación de códigos y descripciones: sin espacios sobrantes ni
    diferencias de mayúsculas ('  Cable  UTP ' -> 'cable utp')."""
    return ' '.join((texto or '').split()).casefold()


def elegir_mas_reciente(filas):
    """De varias equivalencias del mismo ítem, el producto de la usada más recientemente.

    `filas`: lista de (producto_id, ultimo_uso, id). Un ultimo_uso vacío pierde contra
    cualquier fecha; si empatan, gana el id más alto. Devuelve el producto_id o None.
    """
    if not filas:
        return None
    return max(filas, key=lambda fila: (fila[1] is not None, fila[1] or 0, fila[2]))[0]


def elegir_unico(candidatos):
    """El único candidato, o None si no hay ninguno o hay más de uno (ambiguo)."""
    candidatos = list(candidatos)
    return candidatos[0] if len(candidatos) == 1 else None


# ---------------------------------------------------------------------------
# Adjuntos de un correo
# ---------------------------------------------------------------------------
_RE_CDC_ID = re.compile(rb'<(?:[\w.-]+:)?DE\b[^>]*?\bId\s*=\s*["\'](\d{44})["\']')


def es_adjunto_xml(nombre):
    return (nombre or '').strip().lower().endswith('.xml')


def es_adjunto_pdf(nombre):
    return (nombre or '').strip().lower().endswith('.pdf')


def a_bytes(contenido):
    """Los adjuntos XML de un correo pueden llegar como texto: se pasan a bytes UTF-8."""
    if contenido is None:
        return b''
    return contenido.encode('utf-8') if isinstance(contenido, str) else bytes(contenido)


def extraer_cdc_aproximado(contenido):
    """CDC (44 dígitos) del atributo Id del nodo DE, sin validar el XML. Sirve para
    identificar un registro con error. False si no se encuentra."""
    encontrado = _RE_CDC_ID.search(a_bytes(contenido)[:200000])
    return encontrado.group(1).decode('ascii') if encontrado else False


def _raiz_nombre(nombre):
    base = (nombre or '').rsplit('/', 1)[-1]
    return base.rsplit('.', 1)[0].strip().casefold()


def emparejar_pdf(nombre_xml, cdc, nombres_pdf, cantidad_xml):
    """Índices de los PDF que acompañan a un XML del mismo correo.

    Con un solo XML en el correo, todos los PDF son suyos. Con varios, se emparejan
    por nombre: misma raíz, un nombre que contiene a la otra o el CDC dentro del nombre.
    """
    if cantidad_xml <= 1:
        return list(range(len(nombres_pdf)))
    raiz_xml = _raiz_nombre(nombre_xml)
    elegidos = []
    for i, nombre_pdf in enumerate(nombres_pdf):
        raiz_pdf = _raiz_nombre(nombre_pdf)
        if (raiz_xml and (raiz_pdf == raiz_xml or raiz_xml in raiz_pdf or raiz_pdf in raiz_xml)) \
                or (cdc and cdc in (nombre_pdf or '')):
            elegidos.append(i)
    return elegidos


# ---------------------------------------------------------------------------
# Adjuntos comprimidos (ZIP) y correos sin XML
# ---------------------------------------------------------------------------
MAX_MIEMBROS_ZIP = 100             # archivos que se revisan dentro de un ZIP
MAX_BYTES_MIEMBRO = 20 * 1024 * 1024    # un archivo descomprimido
MAX_BYTES_TOTAL = 100 * 1024 * 1024     # todo lo descomprimido de un correo
EXTENSIONES_COMPRIMIDAS_NO_SOPORTADAS = ('.rar', '.7z', '.tar', '.gz', '.tgz', '.bz2')


def es_adjunto_zip(nombre):
    return (nombre or '').strip().lower().endswith('.zip')


def extension_comprimida_no_soportada(nombre):
    """Extensión (en mayúsculas, sin punto) de un comprimido que no se descomprime, o False."""
    nombre = (nombre or '').strip().lower()
    for extension in EXTENSIONES_COMPRIMIDAS_NO_SOPORTADAS:
        if nombre.endswith(extension):
            return extension[1:].upper()
    return False


def _nombre_base(nombre):
    return (nombre or '').replace('\\', '/').rsplit('/', 1)[-1]


def expandir_adjuntos(adjuntos):
    """Separa los adjuntos de un correo en XML y PDF, abriendo los ZIP (un nivel).

    `adjuntos` es una lista de (nombre, contenido). Devuelve un diccionario:
      xmls, pdfs      listas de (nombre, bytes)
      no_soportados   extensiones de comprimidos que no se abren (RAR, 7Z, ...)
      zip_danados     nombres de ZIP que no se pudieron abrir
      zip_omitidos    avisos de archivos de un ZIP que se saltearon (tamaño o cantidad)
      trae_adjuntos   si el correo traía algún adjunto
    Los límites de cantidad y tamaño evitan que un ZIP malicioso consuma la memoria.
    """
    import io
    import zipfile

    resultado = {'xmls': [], 'pdfs': [], 'no_soportados': [], 'zip_danados': [],
                 'zip_omitidos': [], 'trae_adjuntos': bool(adjuntos)}
    total = 0
    for nombre, contenido in adjuntos or []:
        if es_adjunto_xml(nombre):
            resultado['xmls'].append((nombre, a_bytes(contenido)))
        elif es_adjunto_pdf(nombre):
            resultado['pdfs'].append((nombre, a_bytes(contenido)))
        elif es_adjunto_zip(nombre):
            try:
                archivo = zipfile.ZipFile(io.BytesIO(a_bytes(contenido)))
                miembros = [m for m in archivo.infolist() if not m.is_dir()]
            except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
                resultado['zip_danados'].append(nombre)
                continue
            for numero, miembro in enumerate(miembros):
                nombre_miembro = _nombre_base(miembro.filename)
                if not (es_adjunto_xml(nombre_miembro) or es_adjunto_pdf(nombre_miembro)):
                    continue
                if numero >= MAX_MIEMBROS_ZIP:
                    resultado['zip_omitidos'].append('%s: demasiados archivos' % nombre)
                    break
                if miembro.file_size > MAX_BYTES_MIEMBRO or total + miembro.file_size > MAX_BYTES_TOTAL:
                    resultado['zip_omitidos'].append('%s/%s: demasiado grande' % (nombre, nombre_miembro))
                    continue
                try:
                    datos = archivo.read(miembro)
                except (zipfile.BadZipFile, OSError, RuntimeError, ValueError, NotImplementedError):
                    # cifrado, dañado o con método no soportado
                    resultado['zip_danados'].append('%s/%s' % (nombre, nombre_miembro))
                    continue
                if len(datos) > MAX_BYTES_MIEMBRO:
                    resultado['zip_omitidos'].append('%s/%s: demasiado grande' % (nombre, nombre_miembro))
                    continue
                total += len(datos)
                destino = resultado['xmls'] if es_adjunto_xml(nombre_miembro) else resultado['pdfs']
                destino.append((nombre_miembro, datos))
        else:
            extension = extension_comprimida_no_soportada(nombre)
            if extension:
                resultado['no_soportados'].append(extension)
    return resultado


def motivo_sin_xml(expandido):
    """Texto de por qué un correo no tiene XML que cargar (para el registro N/A)."""
    if expandido['no_soportados']:
        tipos = ', '.join(sorted(set(expandido['no_soportados'])))
        return 'El correo trae un adjunto comprimido %s, que no se descomprime; no se encontró ningún XML.' % tipos
    if expandido['zip_danados']:
        return 'No se pudo abrir el ZIP adjunto (%s): está dañado o protegido con contraseña.' % \
            ', '.join(expandido['zip_danados'])
    if expandido['zip_omitidos']:
        return 'El ZIP adjunto supera los límites de tamaño o cantidad de archivos (%s).' % \
            '; '.join(expandido['zip_omitidos'])
    if expandido['trae_adjuntos']:
        return 'El correo no trae archivos XML.'
    return 'El correo no trae adjuntos.'


def adjuntos_de_correo_crudo(crudo):
    """Lista de (nombre, bytes) de los adjuntos de un correo RFC822 sin procesar.
    Solo usa la biblioteca estándar."""
    import email
    import email.policy

    if isinstance(crudo, str):
        crudo = crudo.encode('utf-8')
    mensaje = email.message_from_bytes(bytes(crudo), policy=email.policy.SMTP)
    adjuntos = []
    for parte in mensaje.walk():
        nombre = parte.get_filename()
        if not nombre or parte.is_multipart():
            continue
        try:
            contenido = parte.get_payload(decode=True)
        except Exception:  # noqa: BLE001 - un adjunto ilegible no debe frenar el análisis
            continue
        adjuntos.append((nombre, contenido or b''))
    return adjuntos


def correo_trae_xml(crudo):
    """True si el correo sin procesar trae algún XML, suelto o dentro de un ZIP."""
    return bool(expandir_adjuntos(adjuntos_de_correo_crudo(crudo))['xmls'])


# ---------------------------------------------------------------------------
# Remitente del correo contra el proveedor
# ---------------------------------------------------------------------------
# Dominios de correo gratuito o masivo: no identifican a una empresa, así que con ellos
# se exige la dirección exacta del proveedor.
DOMINIOS_PUBLICOS = frozenset({
    'gmail.com', 'googlemail.com', 'hotmail.com', 'hotmail.es', 'hotmail.com.ar', 'outlook.com',
    'outlook.es', 'outlook.com.ar', 'live.com', 'live.com.ar', 'msn.com', 'yahoo.com', 'yahoo.es',
    'yahoo.com.ar', 'yahoo.com.br', 'ymail.com', 'icloud.com', 'me.com', 'aol.com', 'proton.me',
    'protonmail.com', 'gmx.com', 'mail.com', 'zoho.com', 'yandex.com',
})


def direcciones_de_correo(texto):
    """Direcciones (en minúsculas) de un campo de correo como «Nombre <a@b.com>, c@d.com»."""
    from email.utils import getaddresses

    if not texto:
        return []
    direcciones = []
    for _nombre, direccion in getaddresses([str(texto).replace(';', ',')]):
        direccion = direccion.strip().lower()
        if '@' in direccion:
            direcciones.append(direccion)
    return direcciones


def remitente_coincide(remitente, correos_proveedor):
    """(coincide, motivo). El remitente aprueba si su dirección es una de las del proveedor
    o si es del mismo dominio de la empresa (o de un subdominio); con dominios públicos
    (gmail, hotmail, etc.) solo vale la dirección exacta."""
    remitentes = direcciones_de_correo(remitente)
    if not remitentes:
        return False, 'El correo no informa un remitente que se pueda verificar.'
    propios = []
    for texto in correos_proveedor or []:
        propios += direcciones_de_correo(texto)
    if not propios:
        return False, 'El proveedor no tiene ningún correo cargado en su ficha para comparar con el remitente.'
    dominios = {d.rsplit('@', 1)[1] for d in propios if d.rsplit('@', 1)[1] not in DOMINIOS_PUBLICOS}
    for origen in remitentes:
        if origen in propios:
            return True, ''
        dominio = origen.rsplit('@', 1)[1]
        if dominio in DOMINIOS_PUBLICOS:
            continue
        if any(dominio == d or dominio.endswith('.' + d) for d in dominios):
            return True, ''
    return False, 'El remitente (%s) no coincide con los correos ni el dominio del proveedor.' % \
        ', '.join(remitentes)


def dentro_de_tolerancia(diferencia, tolerancia):
    """True si |diferencia| no supera la tolerancia (con un margen mínimo por decimales)."""
    return abs(diferencia) <= tolerancia + 1e-6


# ----------------------------------------------------------------------
# Mapeo de campos (origen: modelo de recepción; destino: factura, línea o proveedor)
# ----------------------------------------------------------------------
TIPOS_ESCALARES = ('char', 'text', 'integer', 'float', 'monetary', 'date', 'datetime',
                   'boolean', 'selection')
TIPOS_ORIGEN = TIPOS_ESCALARES + ('many2one',)
TIPOS_DESTINO = TIPOS_ESCALARES + ('html', 'many2one')

# Campos que el módulo completa siempre por su cuenta: no se pueden mapear.
CAMPOS_RESERVADOS = {
    'account.move': {
        'id', 'move_type', 'company_id', 'partner_id', 'journal_id', 'currency_id', 'state',
        'invoice_line_ids', 'line_ids', 'name', 'reversed_entry_id', 'invoice_origin',
    },
    'account.move.line': {
        'id', 'move_id', 'move_type', 'company_id', 'display_type', 'product_id', 'account_id',
        'tax_ids', 'quantity', 'price_unit', 'discount', 'sequence', 'purchase_line_id',
    },
    'res.partner': {'id', 'company_id', 'user_ids'},
}

_COMPATIBLES = {
    'char': set(TIPOS_ORIGEN), 'text': set(TIPOS_ORIGEN), 'html': set(TIPOS_ORIGEN),
    'integer': {'integer', 'float', 'monetary', 'char', 'selection'},
    'float': {'integer', 'float', 'monetary', 'char', 'selection'},
    'monetary': {'integer', 'float', 'monetary', 'char', 'selection'},
    'date': {'date', 'datetime', 'char'},
    'datetime': {'date', 'datetime', 'char'},
    'boolean': {'boolean'},
    'selection': {'char', 'selection'},
    'many2one': {'char', 'selection', 'many2one'},
}


def tipos_compatibles(tipo_origen, tipo_destino):
    """True si un campo de tipo `tipo_origen` se puede copiar a uno de tipo `tipo_destino`.
    El valor fijo cuenta como 'char'."""
    return tipo_origen in _COMPATIBLES.get(tipo_destino, set())


def convertir_valor(valor, tipo_destino):
    """(ok, resultado) al llevar un valor leído al tipo del campo destino.

    Un valor vacío (None, False o '') no se copia: devuelve (False, None) para no pisar
    lo que Odoo ya completó. Los campos relacionales (many2one) los resuelve el modelo,
    acá solo pasan tal cual."""
    if valor is None or valor is False or valor == '':
        # False es válido para un boolean destino
        return (True, False) if (valor is False and tipo_destino == 'boolean') else (False, None)
    try:
        if tipo_destino in ('char', 'text', 'html'):
            return True, str(valor)
        if tipo_destino == 'integer':
            return True, int(Decimal(str(valor).strip().replace(',', '.')))
        if tipo_destino in ('float', 'monetary'):
            return True, float(Decimal(str(valor).strip().replace(',', '.')))
        if tipo_destino == 'boolean':
            if isinstance(valor, str):
                return True, valor.strip().lower() in ('1', 'true', 'si', 'sí', 'x')
            return True, bool(valor)
        if tipo_destino in ('date', 'datetime'):
            texto = valor.isoformat() if hasattr(valor, 'isoformat') else str(valor).strip()
            if tipo_destino == 'date':
                return True, texto[:10]
            return True, texto if len(texto) > 10 else texto + ' 00:00:00'
    except (ArithmeticError, ValueError):
        return False, None
    return True, valor


# ----------------------------------------------------------------------
# Cotización de la factura en moneda extranjera
# ----------------------------------------------------------------------
def tasa_odoo_desde_xml(tipo_cambio):
    """Cotización de Odoo (unidades de la moneda del documento por 1 de la moneda de la compañía)
    a partir del tipo de cambio del XML (moneda de la compañía por 1 de la moneda del documento).
    Devuelve None si el XML no informa un tipo de cambio válido."""
    try:
        valor = float(tipo_cambio or 0)
    except (TypeError, ValueError):
        return None
    return 1.0 / valor if valor > 0 else None


def cotizaciones_difieren(tasa_a, tasa_b, relativa=1e-4):
    """True si dos cotizaciones difieren más que una diferencia relativa mínima."""
    if not tasa_a or not tasa_b:
        return False
    return abs(tasa_a - tasa_b) / max(abs(tasa_a), abs(tasa_b)) > relativa
