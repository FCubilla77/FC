# -*- coding: utf-8 -*-
"""Plantilla Excel de configuración de local_py: generación, lectura y validación.

Mismo criterio que `l10n_py/models/plantilla_excel.py`: este archivo NO usa el ORM,
trabaja con diccionarios simples, así se puede probar sin base de datos. Quien llama
le pasa, en `contexto`, los datos de la base contra los que hay que validar (códigos
de cuenta, diarios, usuarios, bancos, monedas, etc.); este archivo no los busca.

Para qué sirve: local_py no asume ningún plan de cuentas en particular. Antes se
completaba su configuración con códigos fijos del plan estándar de Paraguay
(`hooks.py`), lo que solo funcionaba si el cliente usaba ese plan. Ahora el usuario
descarga esta planilla, indica qué cuenta de SU plan cumple cada función, y la sube:
si todo está correcto se aplica la configuración completa de una sola vez.

Estructura de datos (`datos`), igual para la plantilla de ejemplo y para la del cliente:

    {
      'cuentas':   {clave_rol: codigo_de_cuenta},
      'diarios':   {clave_rol: {'nombre', 'codigo', 'cuenta'}},
      'parametros': {clave: valor ya convertido (bool / float / str / lista)},
      'diarios_fiscales': [{'nombre', 'codigo', 'tipo_fiscal', 'timbrado',
                            'nro_documento', 'nro_documento_final',
                            'inicio_vigencia', 'vencimiento'}],
      'series_recibo':    [{'nombre', 'usuario', 'numero_inicial', 'numero_final'}],
      'rubricas':         [{'idrubrica', 'fecha', 'uso', 'cantidad_hojas', 'nro_entrada',
                            'fecha_entrada', 'numero_inicial', 'numero_final'}],
      'chequeras':        [{'nombre', 'banco', 'cuenta_bancaria', 'moneda', 'tipo',
                            'numero_inicial', 'numero_final', 'diario'}],
      'detalle_inventario': [{'cuenta', 'criterio', 'nivel', 'cantidad'}],
      'renumeracion':       [{'anio', 'numero_inicial'}],
      'no_retencion':       [{'ruc', 'tipo_retencion', 'nro_resolucion',
                              'fecha_desde', 'fecha_hasta'}],
      'conceptos_inr':      [{'codigo', 'porcentaje_imputacion', 'porcentaje',
                              'porcentaje_absorcion'}],
    }

Filas de ejemplo: las hojas de lista vienen con filas de ejemplo cuyo primer campo
empieza con «#». Esas filas se ignoran al leer, así la planilla recién descargada se
puede subir sin errores; el usuario le quita el «#» a las que quiera activar. Las
hojas de clave/valor (Cuentas, Diarios, Parámetros) no usan «#»: traen directamente
los valores del plan estándar de Paraguay como ejemplo, para reemplazar.
"""
import datetime
import io
import re

MARCA_EJEMPLO = '#'

CODIGO_CUENTA_REGEX = re.compile(r'^[A-Za-z0-9.]+$')
NRO_DOCUMENTO_REGEX = re.compile(r'^\d{3}-\d{3}-\d{7}$')

# ---------------------------------------------------------------------------
# Hoja «Cuentas»: las 7 cuentas contables que local_py necesita.
#   clave, descripción, obligatoria, tipos de cuenta admitidos (None = cualquiera),
#   código de ejemplo (plan estándar Paraguay), campo de Configuraciones Localización
# ---------------------------------------------------------------------------
TIPOS_GASTO = ('expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')
TIPOS_ACTIVO = ('asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
                'asset_prepayments', 'asset_fixed')

CUENTAS = [
    ('cuenta_gasto_absorcion', 'Cuenta de Gasto por Absorción (IVA)', False, TIPOS_GASTO,
     '7.02.17.01.001', 'local_py_cuenta_gasto_absorcion_id'),
    ('cuenta_gasto_absorcion_renta', 'Cuenta de Gasto por Absorción (Renta)', False, TIPOS_GASTO,
     '7.02.17.01.001', 'local_py_cuenta_gasto_absorcion_renta_id'),
    ('cuenta_retencion_a_confirmar', 'Cuenta «Retenido a Confirmar»', False, TIPOS_ACTIVO,
     '1.01.03.02.006', 'local_py_cuenta_retencion_a_confirmar_id'),
    ('cuenta_retenciones_recibidas_iva', 'Cuenta «Retenciones Recibidas» (IVA)', False, TIPOS_ACTIVO,
     '1.01.03.02.002', 'local_py_cuenta_retenciones_recibidas_iva_id'),
    ('cuenta_retenciones_recibidas_renta', 'Cuenta «Retenciones Recibidas» (Renta)', False, TIPOS_ACTIVO,
     '1.01.03.02.005', 'local_py_cuenta_retenciones_recibidas_renta_id'),
    ('cuenta_retenciones_diferencia', 'Cuenta «Diferencia» (Retenciones Recibidas)', False, None,
     '7.02.18.01.002', 'local_py_cuenta_retenciones_diferencia_id'),
    ('cuenta_cheques_rechazados', 'Cuenta «Cheques Rechazados»', False, TIPOS_ACTIVO,
     '1.01.03.04.001', 'local_py_cuenta_cheques_rechazados_id'),
]
CUENTAS_POR_CLAVE = {c[0]: c for c in CUENTAS}

# ---------------------------------------------------------------------------
# Hoja «Diarios»: los 4 diarios operativos de local_py. El TIPO de diario lo fija el
# rol (no es una columna): los tres de retención son Misceláneos y el de cheques de
# clientes es de Banco. Los diarios de VENTA no van acá: tienen su propia hoja,
# porque exigen Timbrado y numeración reales asignados por la DNIT.
#   clave, descripción, tipo de diario, nombre de ejemplo, código de ejemplo,
#   cuenta de ejemplo, campo de Configuraciones Localización
# ---------------------------------------------------------------------------
DIARIOS = [
    ('diario_retencion_iva', 'Diario de Retención IVA', 'general',
     'Retención IVA', 'RIVA', '2.01.03.01.004', 'local_py_diario_retencion_iva_id'),
    ('diario_retencion_renta', 'Diario de Retención Renta', 'general',
     'Retención Renta', 'RRTA', '2.01.03.01.004', 'local_py_diario_retencion_renta_id'),
    ('diario_retencion_recibida', 'Diario de Retención Recibida', 'general',
     'Retención Recibida', 'RREC', '1.01.03.02.006', 'local_py_diario_retencion_recibida_id'),
    ('diario_cheque_cliente', 'Diario de Cheques de Clientes', 'bank',
     'Cheques de Clientes', 'CHCL', '1.01.01.01.004', 'local_py_diario_cheque_cliente_id'),
]
DIARIOS_POR_CLAVE = {d[0]: d for d in DIARIOS}

# ---------------------------------------------------------------------------
# Hoja «Parámetros».
#   clave, descripción, tipo ('bool'|'float'|'texto'|'lista'), valor de ejemplo,
#   campo de Configuraciones Localización (None = no es un campo directo)
# ---------------------------------------------------------------------------
PARAMETROS = [
    ('retencion_iva', 'Retención IVA activa', 'bool', True,
     'local_py_retencion_iva'),
    ('retencion_iva_porcentaje', 'Porcentaje de Retención IVA predeterminado', 'float', 30.0,
     'local_py_retencion_iva_porcentaje'),
    ('retencion_iva_minimo', 'Valor imponible mínimo para retener IVA (moneda de la empresa)',
     'float', 0.0, 'local_py_retencion_iva_minimo'),
    ('retencion_renta', 'Retención Renta activa', 'bool', False,
     'local_py_retencion_renta'),
    ('concepto_iva', 'Concepto IVA predeterminado (código oficial DNIT, ver hoja «Listas»)',
     'texto', 'IVA.1', 'local_py_concepto_iva_id'),
    ('pagos_proveedores_activo', 'Permitir Pagos a Proveedores fuera de Orden de Pago', 'bool', True,
     'local_py_pagos_proveedores_activo'),
    ('pagos_clientes_activo', 'Permitir Pagos de Clientes fuera de Recibo', 'bool', True,
     'local_py_pagos_clientes_activo'),
    ('asiento_ajuste_inventario', 'Generar Asiento por Ajuste de Inventario Físico', 'bool', False,
     'local_py_asiento_ajuste_inventario'),
    ('imputacion_tributaria', 'Imputación Tributaria de la empresa (uno o varios, separados por «;»)',
     'lista', 'IVA;IRE', None),
]
PARAMETROS_POR_CLAVE = {p[0]: p for p in PARAMETROS}

USOS_RUBRICA = {
    'L. Diario': 'diario', 'L. Mayor': 'mayor', 'L. Inventario': 'inventario',
    'L. Compras': 'compras', 'L. Ventas': 'ventas',
}
TIPOS_CHEQUERA = {'Al día': 'al_dia', 'Diferido': 'diferido'}
CRITERIOS_DETALLE = {'Contacto': 'contacto', 'Producto': 'producto'}
NIVELES_DETALLE = {'Todos': 'todos', 'Top X': 'top'}
TIPOS_RETENCION = {'IVA': 'iva', 'Renta': 'renta'}

HOJA_INSTRUCCIONES = 'Instrucciones'
HOJA_CUENTAS = 'Cuentas'
HOJA_DIARIOS = 'Diarios'
HOJA_PARAMETROS = 'Parámetros'
HOJA_DIARIOS_FISCALES = 'Diarios Fiscales'
HOJA_SERIES = 'Series de Recibo'
HOJA_RUBRICAS = 'Rúbricas'
HOJA_CHEQUERAS = 'Chequeras'
HOJA_DETALLE_INV = 'Detalle Libro Inventario'
HOJA_RENUMERACION = 'Renumeración'
HOJA_NO_RETENCION = 'No Retención'
HOJA_INR = 'Conceptos Renta No Residente'
HOJA_LISTAS = 'Listas'

ENCABEZADOS = {
    HOJA_CUENTAS: ['Clave', 'Descripción', 'Código de cuenta'],
    HOJA_DIARIOS: ['Clave', 'Descripción', 'Nombre del diario', 'Código', 'Código de cuenta'],
    HOJA_PARAMETROS: ['Clave', 'Descripción', 'Valor'],
    HOJA_DIARIOS_FISCALES: ['Nombre del diario', 'Código', 'Tipo Fiscal', 'Timbrado',
                            'Nro. Documento', 'Nro. Documento Final',
                            'Inicio Vigencia', 'Venc. Timbrado'],
    HOJA_SERIES: ['Serie', 'Usuario (login)', 'Número Inicial', 'Número Final'],
    HOJA_RUBRICAS: ['Id Rúbrica', 'Fecha', 'Uso', 'Cant. de hojas', 'Nro. Entrada',
                    'Fecha Entrada', 'Número Inicial', 'Número Final'],
    HOJA_CHEQUERAS: ['Número de Chequera', 'Banco', 'Cuenta bancaria', 'Moneda', 'Tipo',
                     'Número Inicial', 'Número Final', 'Código del diario'],
    HOJA_DETALLE_INV: ['Código de cuenta', 'Criterio', 'Nivel', 'Cantidad (X)'],
    HOJA_RENUMERACION: ['Año', 'Número Asiento Fiscal Inicial'],
    HOJA_NO_RETENCION: ['RUT del Proveedor', 'Tipo de Retención', 'Nro. Resolución',
                        'Fecha Desde', 'Fecha Hasta'],
    HOJA_INR: ['Código', 'Nombre (informativo)', '% Imputación', '% Retención', '% Absorción'],
}

INSTRUCCIONES = [
    'PLANTILLA DE CONFIGURACIÓN — Localización Paraguay (local_py)',
    '',
    'Esta planilla contiene TODO lo que local_py necesita configurar. Complétela con los '
    'datos de su empresa y cárguela en Ajustes > Configuración local_py > Configuración por '
    'plantilla. Si la validación no encuentra errores, la configuración se aplica completa '
    'de una sola vez.',
    '',
    'Reglas generales:',
    '• No cambie los nombres de las hojas ni los encabezados de la fila 1. Los datos empiezan en la fila 2.',
    '• Las cuentas se indican siempre por CÓDIGO, y tienen que existir en el plan de cuentas de su '
    'empresa. local_py no crea cuentas: solo las usa.',
    '• Los campos SI/NO se completan con SI o NO. Las fechas, con formato de fecha de Excel '
    '(o texto AAAA-MM-DD). Los números, sin separador de miles.',
    '• Hojas «Cuentas», «Diarios» y «Parámetros»: no agregue ni borre filas; complete solo la '
    'columna de valor. Vienen con los valores del plan estándar de Paraguay como ejemplo.',
    '• Un valor vacío en esas tres hojas significa «no configurar eso»: queda como está.',
    '',
    'FILAS DE EJEMPLO:',
    '• Las demás hojas (listas) traen filas de ejemplo que empiezan con «#» en la primera columna. '
    'Esas filas SE IGNORAN al cargar, así la planilla recién descargada se puede subir sin errores.',
    '• Para activar una fila de ejemplo, quítele el «#». Para cargar sus propios datos, agregue '
    'filas nuevas sin «#» (o reemplace las de ejemplo).',
    '• Una hoja de lista vacía es válida: no se crea nada de eso.',
    '',
    'Qué se crea y qué se busca:',
    '• Hoja «Diarios»: si no existe un diario con ese código, se crea con la cuenta indicada. Si ya '
    'existe, se usa el existente (no se modifica).',
    '• Hoja «Diarios Fiscales»: diarios de VENTA con Timbrado. Si el código ya existe, se le '
    'completa el timbrado y la numeración; si no, se crea. El Nro. Documento va en formato '
    'completo 999-999-9999999 (Establecimiento-Punto de Expedición-Correlativo).',
    '• Hojas «Series de Recibo», «Rúbricas», «Chequeras», «Renumeración», «No Retención» y '
    '«Detalle Libro Inventario»: se crean los registros indicados.',
    '• Hoja «Conceptos Renta No Residente»: los conceptos ya vienen cargados con local_py; acá solo '
    'se ajustan sus porcentajes. El código no se puede cambiar ni agregar conceptos nuevos.',
    '• Rúbricas: la imagen y la primera hoja no se pueden cargar por planilla; se adjuntan después '
    'en la ficha de cada Rúbrica.',
    '',
    'IMPORTANTE: la plantilla aplica la configuración una vez. Después, los cambios se hacen en el '
    'sistema; volver a cargar la planilla no borra lo ya creado (solo agrega lo que falte).',
]


# ---------------------------------------------------------------------------
# Datos de ejemplo (plan estándar Paraguay) -> datos
# ---------------------------------------------------------------------------

def datos_ejemplo():
    """Datos con los que se arma la plantilla descargable: los valores del plan estándar
    de Paraguay en las hojas de clave/valor, y filas de ejemplo marcadas con «#» en las
    hojas de lista."""
    return {
        'cuentas': {c[0]: c[4] for c in CUENTAS},
        'diarios': {d[0]: {'nombre': d[3], 'codigo': d[4], 'cuenta': d[5]} for d in DIARIOS},
        'parametros': {p[0]: p[3] for p in PARAMETROS},
        'diarios_fiscales': [{
            'nombre': 'Factura de Venta', 'codigo': 'FV01', 'tipo_fiscal': 'Factura',
            'timbrado': 12345678, 'nro_documento': '001-001-0000001',
            'nro_documento_final': '001-001-9999999',
            'inicio_vigencia': datetime.date(2026, 1, 1), 'vencimiento': datetime.date(2026, 12, 31),
        }, {
            'nombre': 'Nota de Crédito de Venta', 'codigo': 'NCV01', 'tipo_fiscal': 'Nota de Credito',
            'timbrado': 12345678, 'nro_documento': '001-001-0000001',
            'nro_documento_final': '001-001-9999999',
            'inicio_vigencia': datetime.date(2026, 1, 1), 'vencimiento': datetime.date(2026, 12, 31),
        }],
        'series_recibo': [
            {'nombre': 'A', 'usuario': 'admin', 'numero_inicial': 1, 'numero_final': 1000},
        ],
        'rubricas': [{
            'idrubrica': 'RUB-0001', 'fecha': datetime.date(2026, 1, 2), 'uso': 'L. Inventario',
            'cantidad_hojas': 500, 'nro_entrada': 'E-0001',
            'fecha_entrada': datetime.date(2026, 1, 2), 'numero_inicial': 1, 'numero_final': 500,
        }],
        'chequeras': [{
            'nombre': 'CH-0001', 'banco': 'Banco Ejemplo', 'cuenta_bancaria': '0000000001',
            'moneda': 'PYG', 'tipo': 'Al día', 'numero_inicial': 1, 'numero_final': 100,
            'diario': 'BNK1',
        }],
        'detalle_inventario': [
            {'cuenta': '1.01.03.01.001', 'criterio': 'Contacto', 'nivel': 'Todos', 'cantidad': 0},
            {'cuenta': '1.01.04.01.001', 'criterio': 'Producto', 'nivel': 'Top X', 'cantidad': 20},
        ],
        'renumeracion': [{'anio': 2026, 'numero_inicial': 1}],
        'no_retencion': [{
            'ruc': '80000000-0', 'tipo_retencion': 'IVA', 'nro_resolucion': '12345',
            'fecha_desde': datetime.date(2026, 1, 1), 'fecha_hasta': datetime.date(2026, 12, 31),
        }],
        'conceptos_inr': [],  # se completa con los conceptos reales de la base
    }


# ---------------------------------------------------------------------------
# datos -> Excel
# ---------------------------------------------------------------------------

def _si_no(valor):
    return 'SI' if valor else 'NO'


def _valor_parametro_excel(clave, valor):
    tipo = PARAMETROS_POR_CLAVE[clave][2]
    if tipo == 'bool':
        return _si_no(valor)
    if tipo == 'float':
        return valor
    if tipo == 'lista':
        return ';'.join(valor) if isinstance(valor, (list, tuple)) else (valor or '')
    return valor or ''


def generar_libro(datos, contexto=None):
    """Devuelve el contenido (bytes) de un .xlsx con `datos` volcado en las hojas.

    `contexto` (opcional) es el mismo diccionario que recibe `leer_libro`: se usa para
    llenar la hoja «Listas» con los valores reales de la base (tipos fiscales, conceptos
    IVA, bancos, monedas, diarios), así los desplegables ofrecen lo que existe."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    contexto = contexto or {}
    libro = Workbook()
    negrita = Font(bold=True, color='FFFFFF')
    relleno = PatternFill('solid', fgColor='4F6D8F')
    gris = Font(color='808080', italic=True)

    def hoja_nueva(nombre, anchos):
        hoja = libro.create_sheet(nombre)
        hoja.append(ENCABEZADOS[nombre])
        for col, ancho in enumerate(anchos, start=1):
            hoja.column_dimensions[get_column_letter(col)].width = ancho
            celda = hoja.cell(row=1, column=col)
            celda.font, celda.fill = negrita, relleno
            celda.alignment = Alignment(wrap_text=True, vertical='center')
        hoja.freeze_panes = 'A2'
        return hoja

    def ejemplo(hoja, valores):
        """Agrega una fila de ejemplo: el primer campo lleva «#» y la fila va en gris."""
        hoja.append([MARCA_EJEMPLO + str(valores[0] if valores[0] is not None else '')] + list(valores[1:]))
        for col in range(1, len(valores) + 1):
            hoja.cell(row=hoja.max_row, column=col).font = gris

    def texto(hoja, columnas, hasta_fila):
        for fila in range(2, hasta_fila + 1):
            for col in columnas:
                hoja.cell(row=fila, column=col).number_format = '@'

    def fecha(hoja, columnas, hasta_fila):
        for fila in range(2, hasta_fila + 1):
            for col in columnas:
                hoja.cell(row=fila, column=col).number_format = 'YYYY-MM-DD'

    def lista(hoja, columna, opciones, hasta_fila):
        """Desplegable. Excel rechaza (y «repara» quitándolas) las listas escritas dentro
        de la validación que superan los 255 caracteres: las largas se toman de un rango
        de la hoja «Listas», que se pasa como fórmula ya armada."""
        if isinstance(opciones, str):
            formula = opciones
        else:
            texto_opciones = ','.join(opciones)
            if len(texto_opciones) > 250:
                return  # sin desplegable; la validación al cargar igual controla el valor
            formula = '"%s"' % texto_opciones
        validacion = DataValidation(type='list', formula1=formula, allow_blank=True)
        hoja.add_data_validation(validacion)
        validacion.add('%s2:%s%d' % (columna, columna, hasta_fila))

    # --- Instrucciones ---------------------------------------------------
    instrucciones = libro.active
    instrucciones.title = HOJA_INSTRUCCIONES
    instrucciones.column_dimensions['A'].width = 130
    for linea in INSTRUCCIONES:
        instrucciones.append([linea])
        instrucciones.cell(row=instrucciones.max_row, column=1).alignment = Alignment(wrap_text=True)
    instrucciones['A1'].font = Font(bold=True, size=14)

    # --- Hoja «Listas» (valores reales de la base, para los desplegables) -
    listas = libro.create_sheet(HOJA_LISTAS)
    listas.append(['Tipos Fiscales', 'Conceptos IVA', 'Imputación Tributaria', 'Monedas',
                   'Bancos', 'Diarios de Banco', 'Usuarios (login)'])
    for col in range(1, 8):
        listas.column_dimensions[get_column_letter(col)].width = 28
        listas.cell(row=1, column=col).font = negrita
        listas.cell(row=1, column=col).fill = relleno
    columnas_listas = [
        sorted(contexto.get('tipos_fiscales') or []),
        sorted(contexto.get('conceptos_iva') or []),
        sorted(contexto.get('imputaciones') or []),
        sorted(contexto.get('monedas') or []),
        sorted(contexto.get('bancos') or []),
        sorted(contexto.get('diarios_banco') or []),
        sorted(contexto.get('usuarios') or []),
    ]
    for fila in range(max([len(c) for c in columnas_listas] or [0])):
        listas.append([c[fila] if fila < len(c) else None for c in columnas_listas])

    def rango_listas(columna, cantidad):
        """Fórmula de rango sobre la hoja «Listas», o None si esa columna está vacía."""
        return "'%s'!$%s$2:$%s$%d" % (HOJA_LISTAS, columna, columna, cantidad + 1) if cantidad else None

    # --- Cuentas ---------------------------------------------------------
    hoja = hoja_nueva(HOJA_CUENTAS, [36, 62, 24])
    for clave, descripcion, obligatoria, _tipos, _std, _campo in CUENTAS:
        hoja.append([clave, descripcion + (' (OBLIGATORIA)' if obligatoria else ''),
                     datos['cuentas'].get(clave, '')])
    texto(hoja, (3,), hoja.max_row)

    # --- Diarios ---------------------------------------------------------
    hoja = hoja_nueva(HOJA_DIARIOS, [30, 40, 28, 12, 24])
    for clave, descripcion, tipo, _nom, _cod, _cta, _campo in DIARIOS:
        valores = datos['diarios'].get(clave) or {}
        etiqueta = 'Misceláneo' if tipo == 'general' else 'Banco'
        hoja.append([clave, '%s — diario de tipo %s' % (descripcion, etiqueta),
                     valores.get('nombre', ''), valores.get('codigo', ''), valores.get('cuenta', '')])
    texto(hoja, (4, 5), hoja.max_row)

    # --- Parámetros ------------------------------------------------------
    hoja = hoja_nueva(HOJA_PARAMETROS, [32, 70, 24])
    filas_bool = []
    for numero, (clave, descripcion, tipo, _std, _campo) in enumerate(PARAMETROS, start=2):
        hoja.append([clave, descripcion, _valor_parametro_excel(clave, datos['parametros'].get(clave))])
        if tipo == 'bool':
            filas_bool.append(numero)
        if tipo in ('texto', 'lista'):
            hoja.cell(row=numero, column=3).number_format = '@'
    for numero in filas_bool:
        validacion = DataValidation(type='list', formula1='"SI,NO"', allow_blank=True)
        hoja.add_data_validation(validacion)
        validacion.add('C%d' % numero)

    # --- Diarios Fiscales ------------------------------------------------
    hoja = hoja_nueva(HOJA_DIARIOS_FISCALES, [30, 12, 26, 14, 20, 20, 16, 16])
    for d in datos['diarios_fiscales']:
        ejemplo(hoja, [d['nombre'], d['codigo'], d['tipo_fiscal'], d['timbrado'],
                       d['nro_documento'], d['nro_documento_final'],
                       d['inicio_vigencia'], d['vencimiento']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1, 2, 3, 5, 6), limite)
    fecha(hoja, (7, 8), limite)
    lista(hoja, 'C', rango_listas('A', len(columnas_listas[0])), limite)

    # --- Series de Recibo ------------------------------------------------
    hoja = hoja_nueva(HOJA_SERIES, [16, 26, 16, 16])
    for s in datos['series_recibo']:
        ejemplo(hoja, [s['nombre'], s['usuario'], s['numero_inicial'], s['numero_final']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1, 2), limite)
    lista(hoja, 'B', rango_listas('G', len(columnas_listas[6])), limite)

    # --- Rúbricas --------------------------------------------------------
    hoja = hoja_nueva(HOJA_RUBRICAS, [16, 14, 18, 14, 16, 16, 16, 16])
    for r in datos['rubricas']:
        ejemplo(hoja, [r['idrubrica'], r['fecha'], r['uso'], r['cantidad_hojas'],
                       r['nro_entrada'], r['fecha_entrada'], r['numero_inicial'], r['numero_final']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1, 3, 5), limite)
    fecha(hoja, (2, 6), limite)
    lista(hoja, 'C', list(USOS_RUBRICA), limite)

    # --- Chequeras -------------------------------------------------------
    hoja = hoja_nueva(HOJA_CHEQUERAS, [22, 26, 22, 12, 14, 16, 16, 20])
    for c in datos['chequeras']:
        ejemplo(hoja, [c['nombre'], c['banco'], c['cuenta_bancaria'], c['moneda'], c['tipo'],
                       c['numero_inicial'], c['numero_final'], c['diario']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1, 2, 3, 4, 8), limite)
    lista(hoja, 'B', rango_listas('E', len(columnas_listas[4])), limite)
    lista(hoja, 'D', rango_listas('D', len(columnas_listas[3])), limite)
    lista(hoja, 'E', list(TIPOS_CHEQUERA), limite)
    lista(hoja, 'H', rango_listas('F', len(columnas_listas[5])), limite)

    # --- Detalle Libro Inventario ----------------------------------------
    hoja = hoja_nueva(HOJA_DETALLE_INV, [24, 16, 14, 14])
    for d in datos['detalle_inventario']:
        ejemplo(hoja, [d['cuenta'], d['criterio'], d['nivel'], d['cantidad']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1,), limite)
    lista(hoja, 'B', list(CRITERIOS_DETALLE), limite)
    lista(hoja, 'C', list(NIVELES_DETALLE), limite)

    # --- Renumeración ----------------------------------------------------
    hoja = hoja_nueva(HOJA_RENUMERACION, [12, 32])
    for r in datos['renumeracion']:
        ejemplo(hoja, [r['anio'], r['numero_inicial']])
    texto(hoja, (1,), max(hoja.max_row, 50))

    # --- No Retención ----------------------------------------------------
    hoja = hoja_nueva(HOJA_NO_RETENCION, [22, 20, 20, 16, 16])
    for r in datos['no_retencion']:
        ejemplo(hoja, [r['ruc'], r['tipo_retencion'], r['nro_resolucion'],
                       r['fecha_desde'], r['fecha_hasta']])
    limite = max(hoja.max_row, 200)
    texto(hoja, (1, 3), limite)
    fecha(hoja, (4, 5), limite)
    lista(hoja, 'B', list(TIPOS_RETENCION), limite)

    # --- Conceptos Renta No Residente ------------------------------------
    hoja = hoja_nueva(HOJA_INR, [14, 52, 16, 16, 16])
    for c in datos['conceptos_inr']:
        hoja.append([c['codigo'], c.get('nombre', ''), c['porcentaje_imputacion'],
                     c['porcentaje'], c['porcentaje_absorcion']])
    texto(hoja, (1,), max(hoja.max_row, 100))

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# ---------------------------------------------------------------------------
# Excel -> datos (con validación)
# ---------------------------------------------------------------------------

class _Lector:
    def __init__(self):
        self.errores = []
        self.advertencias = []

    def error(self, hoja, fila, mensaje):
        self.errores.append("Hoja «%s»%s: %s" % (hoja, ", fila %s" % fila if fila else '', mensaje))

    def aviso(self, hoja, fila, mensaje):
        self.advertencias.append("Hoja «%s»%s: %s" % (hoja, ", fila %s" % fila if fila else '', mensaje))


def _texto(valor):
    if valor is None:
        return ''
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.strftime('%Y-%m-%d')
    if isinstance(valor, float) and valor == int(valor):
        return str(int(valor))
    return str(valor).strip()


def _flag(valor):
    t = _texto(valor).lower()
    if t in ('si', 'sí', 'true', '1', 'x', 'verdadero'):
        return True
    if t in ('', 'no', 'false', '0', 'falso'):
        return False
    return None


def _entero(valor):
    t = _texto(valor).replace('.', '').replace(',', '')
    try:
        return int(t) if t else 0
    except ValueError:
        return None


def _numero(valor):
    t = _texto(valor).replace(',', '.')
    try:
        return float(t) if t else 0.0
    except ValueError:
        return None


def _fecha(valor):
    """Fecha como 'AAAA-MM-DD', None si el valor no es una fecha, '' si está vacío."""
    if valor is None or _texto(valor) == '':
        return ''
    if isinstance(valor, datetime.datetime):
        return valor.date().isoformat()
    if isinstance(valor, datetime.date):
        return valor.isoformat()
    t = _texto(valor)
    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.datetime.strptime(t, formato).date().isoformat()
        except ValueError:
            continue
    return None


def _es_ejemplo(fila):
    return _texto(fila[0]).startswith(MARCA_EJEMPLO)


def _filas(libro, nombre, lector, saltar_ejemplos=True):
    """Filas de datos (desde la 2) como (número_de_fila, [valores]), sin las vacías y,
    salvo que se pida lo contrario, sin las filas de ejemplo marcadas con «#»."""
    if nombre not in libro.sheetnames:
        lector.error(nombre, None, "no se encontró la hoja. No cambie los nombres de las hojas.")
        return []
    hoja = libro[nombre]
    esperado = ENCABEZADOS[nombre]
    primera = next(hoja.iter_rows(min_row=1, max_row=1, max_col=len(esperado)), None)
    actual = [_texto(c.value) for c in primera] if primera else []
    if actual != esperado:
        lector.error(nombre, 1, "los encabezados no coinciden con la plantilla (se esperaba: %s)."
                     % ' | '.join(esperado))
        return []
    resultado = []
    for numero, fila in enumerate(
            hoja.iter_rows(min_row=2, max_col=len(esperado), values_only=True), start=2):
        if not any(_texto(v) for v in fila):
            continue
        if saltar_ejemplos and _es_ejemplo(fila):
            continue
        resultado.append((numero, list(fila)))
    return resultado


def _clave_valor(libro, nombre, lector, claves_validas, columna_valor):
    """Lee una hoja de clave/valor y devuelve {clave: valor_crudo}."""
    valores, vistas = {}, set()
    for n, f in _filas(libro, nombre, lector, saltar_ejemplos=False):
        clave = _texto(f[0])
        if not clave:
            lector.error(nombre, n, "falta la clave.")
            continue
        if clave in vistas:
            lector.error(nombre, n, "la clave «%s» está repetida." % clave)
            continue
        vistas.add(clave)
        if clave not in claves_validas:
            lector.aviso(nombre, n, "la clave «%s» no se reconoce y se ignora." % clave)
            continue
        valores[clave] = f[columna_valor] if len(f) > columna_valor else None
    faltantes = [c for c in claves_validas if c not in vistas]
    if faltantes:
        lector.aviso(nombre, None, "no están las claves %s: no se configuran."
                     % ', '.join(sorted(faltantes)))
    return valores


def leer_libro(contenido, contexto=None):
    """Lee y valida un .xlsx. Devuelve (datos, errores, advertencias).

    Si hay errores, `datos` no debe usarse. `contexto` trae los datos de la base contra
    los que validar; cada clave ausente desactiva esa validación:

        cuentas            {codigo: account_type}  cuentas del plan de la compañía
        diarios            {codigo: tipo}          diarios existentes de la compañía
        diarios_banco      [codigo]                diarios de banco (para Chequeras)
        tipos_fiscales     [nombre]
        conceptos_iva      [codigo]
        imputaciones       [nombre]
        monedas            [nombre]
        bancos             [nombre]
        cuentas_bancarias  [acc_number]
        usuarios           [login]
        rucs               [vat]                   RUT de contactos (para No Retención)
        codigos_inr        [codigo]
    """
    from openpyxl import load_workbook

    contexto = contexto or {}
    lector = _Lector()
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True)
    except Exception as exc:  # archivo ilegible: no es un .xlsx válido
        return None, ["No se pudo abrir el archivo como Excel (.xlsx): %s" % exc], []

    cuentas_base = contexto.get('cuentas')
    diarios_base = contexto.get('diarios') or {}

    def _mapa_minusculas(valores):
        return {str(v).strip().lower(): str(v).strip() for v in (valores or [])}

    def _cuenta(hoja, n, codigo, tipos=None, etiqueta=''):
        """Valida un código de cuenta contra el plan y devuelve el código normalizado."""
        if cuentas_base is None:
            return codigo
        real = {c.lower(): c for c in cuentas_base}.get(codigo.lower())
        if not real:
            lector.error(hoja, n, "%sla cuenta «%s» no existe en el plan de cuentas de la empresa."
                         % (etiqueta, codigo))
            return None
        if tipos and cuentas_base[real] not in tipos:
            lector.aviso(hoja, n, "%sla cuenta %s es de tipo «%s»; se esperaba: %s."
                         % (etiqueta, real, cuentas_base[real], ', '.join(tipos)))
        return real

    datos = {}

    # --- Cuentas ---------------------------------------------------------
    crudos = _clave_valor(libro, HOJA_CUENTAS, lector, set(CUENTAS_POR_CLAVE), 2)
    cuentas = {}
    for clave, descripcion, obligatoria, tipos, _std, _campo in CUENTAS:
        if clave not in crudos:
            continue
        valor = _texto(crudos[clave])
        if isinstance(crudos[clave], float):
            lector.error(HOJA_CUENTAS, None, "«%s»: el código se leyó como número decimal; "
                                             "formatee la columna como texto." % clave)
            continue
        if not valor:
            if obligatoria:
                lector.error(HOJA_CUENTAS, None, "falta la cuenta obligatoria «%s»." % clave)
            else:
                lector.aviso(HOJA_CUENTAS, None, "«%s» quedó vacía: no se configura." % clave)
            continue
        if not CODIGO_CUENTA_REGEX.match(valor):
            lector.error(HOJA_CUENTAS, None, "«%s»: el código «%s» solo puede tener letras, "
                                             "números y puntos." % (clave, valor))
            continue
        real = _cuenta(HOJA_CUENTAS, None, valor, tipos, '«%s»: ' % clave)
        if real:
            cuentas[clave] = real
    datos['cuentas'] = cuentas

    # --- Diarios ---------------------------------------------------------
    diarios, codigos_vistos = {}, {}
    filas_diarios = {}
    for n, f in _filas(libro, HOJA_DIARIOS, lector, saltar_ejemplos=False):
        filas_diarios[_texto(f[0])] = (n, f)
    for clave, descripcion, tipo, _nom, _cod, _cta, _campo in DIARIOS:
        if clave not in filas_diarios:
            lector.aviso(HOJA_DIARIOS, None, "no está la clave «%s»: no se configura." % clave)
            continue
        n, f = filas_diarios[clave]
        nombre, codigo, cuenta = _texto(f[2]), _texto(f[3]), _texto(f[4])
        if not nombre and not codigo and not cuenta:
            lector.aviso(HOJA_DIARIOS, n, "«%s» quedó vacío: no se configura." % clave)
            continue
        if not nombre or not codigo:
            lector.error(HOJA_DIARIOS, n, "«%s»: hacen falta el nombre y el código del diario."
                         % clave)
            continue
        if len(codigo) > 5:
            lector.error(HOJA_DIARIOS, n, "«%s»: el código «%s» no puede tener más de 5 "
                                          "caracteres." % (clave, codigo))
            continue
        if codigo.lower() in codigos_vistos:
            lector.error(HOJA_DIARIOS, n, "el código «%s» está repetido (también en «%s»)."
                         % (codigo, codigos_vistos[codigo.lower()]))
            continue
        codigos_vistos[codigo.lower()] = clave
        existente = {c.lower(): c for c in diarios_base}.get(codigo.lower())
        if existente:
            if diarios_base[existente] != tipo:
                lector.error(HOJA_DIARIOS, n, "«%s»: ya existe un diario con el código «%s» pero "
                                              "es de tipo «%s»; se esperaba «%s». Use otro código."
                             % (clave, codigo, diarios_base[existente], tipo))
                continue
            lector.aviso(HOJA_DIARIOS, n, "«%s»: el diario «%s» ya existe; se usa el existente y "
                                          "no se modifica." % (clave, codigo))
        elif not cuenta:
            lector.error(HOJA_DIARIOS, n, "«%s»: hay que indicar la cuenta contable, porque el "
                                          "diario «%s» todavía no existe y hay que crearlo."
                         % (clave, codigo))
            continue
        real = _cuenta(HOJA_DIARIOS, n, cuenta, None, '«%s»: ' % clave) if cuenta else ''
        if cuenta and not real:
            continue
        diarios[clave] = {'nombre': nombre, 'codigo': codigo, 'cuenta': real or '', 'tipo': tipo}
    # Que los diarios de Retención IVA y Retención Renta tengan que ser DISTINTOS (hace
    # falta para diferenciar una de otra en la grilla de Medios) ya queda cubierto por el
    # control de código repetido de arriba: dos roles no pueden compartir código.
    datos['diarios'] = diarios

    # --- Parámetros ------------------------------------------------------
    crudos = _clave_valor(libro, HOJA_PARAMETROS, lector, set(PARAMETROS_POR_CLAVE), 2)
    conceptos_iva = _mapa_minusculas(contexto.get('conceptos_iva'))
    imputaciones = _mapa_minusculas(contexto.get('imputaciones'))
    parametros = {}
    for clave, descripcion, tipo, _std, _campo in PARAMETROS:
        if clave not in crudos:
            continue
        crudo = crudos[clave]
        if tipo == 'bool':
            valor = _flag(crudo)
            if valor is None:
                lector.error(HOJA_PARAMETROS, None, "«%s» debe ser SI o NO." % clave)
                continue
        elif tipo == 'float':
            valor = _numero(crudo)
            if valor is None:
                lector.error(HOJA_PARAMETROS, None, "«%s»: «%s» no es un número."
                             % (clave, _texto(crudo)))
                continue
            if valor < 0:
                lector.error(HOJA_PARAMETROS, None, "«%s» no puede ser negativo." % clave)
                continue
        elif tipo == 'lista':
            partes = [p.strip() for p in _texto(crudo).split(';') if p.strip()]
            if contexto.get('imputaciones') is not None:
                desconocidas = [p for p in partes if p.lower() not in imputaciones]
                if desconocidas:
                    lector.error(HOJA_PARAMETROS, None,
                                 "«%s»: %s no existe(n) (ver hoja «Listas»)."
                                 % (clave, ', '.join('«%s»' % d for d in desconocidas)))
                    continue
                partes = [imputaciones[p.lower()] for p in partes]
            if len(partes) > 1 and any(p.lower() == 'no imputa' for p in partes):
                lector.error(HOJA_PARAMETROS, None,
                             "«%s»: «No Imputa» no se puede combinar con otras opciones." % clave)
                continue
            valor = partes
        else:
            valor = _texto(crudo)
            if clave == 'concepto_iva' and valor and contexto.get('conceptos_iva') is not None:
                if valor.lower() not in conceptos_iva:
                    lector.error(HOJA_PARAMETROS, None, "«%s»: el código «%s» no existe "
                                                        "(ver hoja «Listas»)." % (clave, valor))
                    continue
                valor = conceptos_iva[valor.lower()]
        parametros[clave] = valor
    if parametros.get('retencion_iva') and not parametros.get('retencion_iva_porcentaje'):
        lector.aviso(HOJA_PARAMETROS, None, "la Retención IVA está activa pero el porcentaje "
                                            "predeterminado quedó en 0.")
    if parametros.get('retencion_iva_porcentaje', 0) > 100:
        lector.error(HOJA_PARAMETROS, None, "«retencion_iva_porcentaje» no puede ser mayor a 100.")
    datos['parametros'] = parametros

    # --- Diarios Fiscales ------------------------------------------------
    tipos_fiscales = _mapa_minusculas(contexto.get('tipos_fiscales'))
    fiscales, vistos = [], {}
    for n, f in _filas(libro, HOJA_DIARIOS_FISCALES, lector):
        nombre, codigo, tipo_fiscal = _texto(f[0]), _texto(f[1]), _texto(f[2])
        if not nombre or not codigo or not tipo_fiscal:
            lector.error(HOJA_DIARIOS_FISCALES, n, "hacen falta el nombre, el código y el Tipo Fiscal.")
            continue
        if len(codigo) > 5:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el código «%s» no puede tener más de 5 "
                                                   "caracteres." % codigo)
            continue
        if codigo.lower() in vistos:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el código «%s» está repetido (también en la "
                                                   "fila %s)." % (codigo, vistos[codigo.lower()]))
            continue
        vistos[codigo.lower()] = n
        if codigo.lower() in {c.lower(): c for c in diarios_base} and \
                diarios_base[{c.lower(): c for c in diarios_base}[codigo.lower()]] != 'sale':
            lector.error(HOJA_DIARIOS_FISCALES, n, "ya existe un diario con el código «%s» que no "
                                                   "es de venta. Use otro código." % codigo)
            continue
        if contexto.get('tipos_fiscales') is not None and tipo_fiscal.lower() not in tipos_fiscales:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el Tipo Fiscal «%s» no existe (ver hoja "
                                                   "«Listas»)." % tipo_fiscal)
            continue
        timbrado = _entero(f[3])
        if timbrado is None:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el Timbrado «%s» no es un número entero."
                         % _texto(f[3]))
            continue
        if timbrado <= 0 or len(str(timbrado)) > 8:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el Timbrado debe ser un número positivo de "
                                                   "hasta 8 dígitos.")
            continue
        nro, nro_final = _texto(f[4]), _texto(f[5])
        for etiqueta, valor in (('Nro. Documento', nro), ('Nro. Documento Final', nro_final)):
            if not NRO_DOCUMENTO_REGEX.match(valor):
                lector.error(HOJA_DIARIOS_FISCALES, n, "«%s» debe tener el formato completo "
                                                       "999-999-9999999; se leyó «%s»."
                             % (etiqueta, valor))
        if NRO_DOCUMENTO_REGEX.match(nro) and NRO_DOCUMENTO_REGEX.match(nro_final):
            if nro[:8] != nro_final[:8]:
                lector.error(HOJA_DIARIOS_FISCALES, n, "el Establecimiento-Punto de Expedición de "
                                                       "«Nro. Documento Final» (%s) tiene que ser "
                                                       "el mismo que el de «Nro. Documento» (%s)."
                             % (nro_final[:7], nro[:7]))
            elif int(nro_final[8:]) < int(nro[8:]):
                lector.error(HOJA_DIARIOS_FISCALES, n, "el correlativo final no puede ser menor "
                                                       "que el inicial.")
        inicio, vence = _fecha(f[6]), _fecha(f[7])
        for etiqueta, valor in (('Inicio Vigencia', inicio), ('Venc. Timbrado', vence)):
            if valor is None:
                lector.error(HOJA_DIARIOS_FISCALES, n, "«%s» no es una fecha válida (use "
                                                       "AAAA-MM-DD)." % etiqueta)
        if not inicio or not vence:
            lector.error(HOJA_DIARIOS_FISCALES, n, "hacen falta el Inicio de Vigencia y el "
                                                   "Vencimiento del Timbrado.")
        elif inicio and vence and inicio > vence:
            lector.error(HOJA_DIARIOS_FISCALES, n, "el Inicio de Vigencia no puede ser posterior "
                                                   "al Vencimiento del Timbrado.")
        fiscales.append({
            'nombre': nombre, 'codigo': codigo, 'tipo_fiscal': tipos_fiscales.get(
                tipo_fiscal.lower(), tipo_fiscal),
            'timbrado': timbrado, 'nro_documento': nro, 'nro_documento_final': nro_final,
            'inicio_vigencia': inicio, 'vencimiento': vence})
    # Un mismo Timbrado no puede repetirse para el mismo Tipo Fiscal (lo controla también
    # una constraint de account.journal; acá se avisa antes de llegar a aplicar).
    por_timbrado = {}
    for d in fiscales:
        clave = (d['timbrado'], d['tipo_fiscal'].lower())
        if clave in por_timbrado:
            lector.error(HOJA_DIARIOS_FISCALES, None, "el Timbrado %s ya se usa para el Tipo "
                                                      "Fiscal «%s» en otro diario de la planilla."
                         % (d['timbrado'], d['tipo_fiscal']))
        por_timbrado[clave] = d['codigo']
    datos['diarios_fiscales'] = fiscales

    # --- Series de Recibo ------------------------------------------------
    usuarios = _mapa_minusculas(contexto.get('usuarios'))
    series, vistos = [], {}
    for n, f in _filas(libro, HOJA_SERIES, lector):
        nombre, login = _texto(f[0]), _texto(f[1])
        if not nombre or not login:
            lector.error(HOJA_SERIES, n, "hacen falta la serie y el usuario.")
            continue
        if contexto.get('usuarios') is not None and login.lower() not in usuarios:
            lector.error(HOJA_SERIES, n, "el usuario «%s» no existe (ver hoja «Listas»)." % login)
            continue
        inicial, final = _entero(f[2]), _entero(f[3])
        if inicial is None or final is None:
            lector.error(HOJA_SERIES, n, "los números inicial y final deben ser enteros.")
            continue
        if final and final < inicial:
            lector.error(HOJA_SERIES, n, "el número final no puede ser menor que el inicial.")
            continue
        clave = (nombre.lower(), login.lower())
        if clave in vistos:
            lector.error(HOJA_SERIES, n, "la serie «%s» del usuario «%s» está repetida (también "
                                         "en la fila %s)." % (nombre, login, vistos[clave]))
            continue
        vistos[clave] = n
        series.append({'nombre': nombre, 'usuario': usuarios.get(login.lower(), login),
                       'numero_inicial': inicial, 'numero_final': final})
    datos['series_recibo'] = series

    # --- Rúbricas --------------------------------------------------------
    rubricas, vistos = [], {}
    for n, f in _filas(libro, HOJA_RUBRICAS, lector):
        idrubrica, uso, nro_entrada = _texto(f[0]), _texto(f[2]), _texto(f[4])
        if len(idrubrica) > 10:
            lector.error(HOJA_RUBRICAS, n, "el «Id Rúbrica» no puede tener más de 10 caracteres.")
            continue
        if len(nro_entrada) > 10:
            lector.error(HOJA_RUBRICAS, n, "el «Nro. Entrada» no puede tener más de 10 caracteres.")
            continue
        if uso not in USOS_RUBRICA:
            lector.error(HOJA_RUBRICAS, n, "«Uso» debe ser uno de: %s." % ', '.join(USOS_RUBRICA))
            continue
        fecha_rub, fecha_ent = _fecha(f[1]), _fecha(f[5])
        if fecha_rub is None or fecha_ent is None:
            lector.error(HOJA_RUBRICAS, n, "las fechas no son válidas (use AAAA-MM-DD).")
            continue
        hojas, inicial, final = _entero(f[3]), _entero(f[6]), _entero(f[7])
        if None in (hojas, inicial, final):
            lector.error(HOJA_RUBRICAS, n, "la cantidad de hojas y los números inicial y final "
                                           "deben ser enteros.")
            continue
        faltantes = [e for e, v in (('Id Rúbrica', idrubrica), ('Fecha', fecha_rub),
                                    ('Cant. de hojas', hojas), ('Nro. Entrada', nro_entrada),
                                    ('Fecha Entrada', fecha_ent), ('Número Inicial', inicial),
                                    ('Número Final', final)) if not v]
        if faltantes:
            lector.error(HOJA_RUBRICAS, n, "faltan datos obligatorios: %s." % ', '.join(faltantes))
            continue
        if final < inicial:
            lector.error(HOJA_RUBRICAS, n, "el número final no puede ser menor que el inicial.")
            continue
        if idrubrica.lower() in vistos:
            lector.error(HOJA_RUBRICAS, n, "el «Id Rúbrica» «%s» está repetido (también en la fila "
                                           "%s)." % (idrubrica, vistos[idrubrica.lower()]))
            continue
        vistos[idrubrica.lower()] = n
        rubricas.append({'idrubrica': idrubrica, 'fecha': fecha_rub, 'uso': USOS_RUBRICA[uso],
                         'cantidad_hojas': hojas, 'nro_entrada': nro_entrada,
                         'fecha_entrada': fecha_ent, 'numero_inicial': inicial,
                         'numero_final': final})
    datos['rubricas'] = rubricas

    # --- Chequeras -------------------------------------------------------
    bancos = _mapa_minusculas(contexto.get('bancos'))
    cuentas_bancarias = _mapa_minusculas(contexto.get('cuentas_bancarias'))
    monedas = _mapa_minusculas(contexto.get('monedas'))
    diarios_banco = _mapa_minusculas(contexto.get('diarios_banco'))
    # Los diarios de banco que la propia planilla crea también sirven de destino.
    for valores in diarios.values():
        if valores.get('tipo') == 'bank':
            diarios_banco.setdefault(valores['codigo'].lower(), valores['codigo'])
    chequeras, vistos = [], {}
    for n, f in _filas(libro, HOJA_CHEQUERAS, lector):
        nombre, banco, cuenta_bco = _texto(f[0]), _texto(f[1]), _texto(f[2])
        moneda, tipo_chq, diario = _texto(f[3]), _texto(f[4]), _texto(f[7])
        inicial, final = _entero(f[5]), _entero(f[6])
        if None in (inicial, final):
            lector.error(HOJA_CHEQUERAS, n, "los números inicial y final deben ser enteros.")
            continue
        faltantes = [e for e, v in (('Número de Chequera', nombre), ('Banco', banco),
                                    ('Cuenta bancaria', cuenta_bco), ('Moneda', moneda),
                                    ('Tipo', tipo_chq), ('Número Inicial', inicial),
                                    ('Número Final', final), ('Código del diario', diario))
                     if not v]
        if faltantes:
            lector.error(HOJA_CHEQUERAS, n, "faltan datos obligatorios: %s." % ', '.join(faltantes))
            continue
        if tipo_chq not in TIPOS_CHEQUERA:
            lector.error(HOJA_CHEQUERAS, n, "«Tipo» debe ser «Al día» o «Diferido».")
            continue
        if final < inicial:
            lector.error(HOJA_CHEQUERAS, n, "el número final no puede ser menor que el inicial.")
            continue
        if contexto.get('bancos') is not None and banco.lower() not in bancos:
            lector.error(HOJA_CHEQUERAS, n, "el banco «%s» no existe (ver hoja «Listas»). Créelo "
                                            "en Contactos > Configuración > Bancos." % banco)
            continue
        if contexto.get('cuentas_bancarias') is not None and cuenta_bco.lower() not in cuentas_bancarias:
            lector.error(HOJA_CHEQUERAS, n, "la cuenta bancaria «%s» no existe. Créela en la ficha "
                                            "de la empresa, solapa «Contabilidad»." % cuenta_bco)
            continue
        if contexto.get('monedas') is not None and moneda.lower() not in monedas:
            lector.error(HOJA_CHEQUERAS, n, "la moneda «%s» no existe." % moneda)
            continue
        if contexto.get('diarios_banco') is not None and diario.lower() not in diarios_banco:
            lector.error(HOJA_CHEQUERAS, n, "no hay un diario de banco con el código «%s»." % diario)
            continue
        if nombre.lower() in vistos:
            lector.error(HOJA_CHEQUERAS, n, "el número de chequera «%s» está repetido (también en "
                                            "la fila %s)." % (nombre, vistos[nombre.lower()]))
            continue
        vistos[nombre.lower()] = n
        chequeras.append({
            'nombre': nombre, 'banco': bancos.get(banco.lower(), banco),
            'cuenta_bancaria': cuentas_bancarias.get(cuenta_bco.lower(), cuenta_bco),
            'moneda': monedas.get(moneda.lower(), moneda), 'tipo': TIPOS_CHEQUERA[tipo_chq],
            'numero_inicial': inicial, 'numero_final': final,
            'diario': diarios_banco.get(diario.lower(), diario)})
    datos['chequeras'] = chequeras

    # --- Detalle Libro Inventario ----------------------------------------
    detalle, vistos = [], {}
    for n, f in _filas(libro, HOJA_DETALLE_INV, lector):
        codigo, criterio, nivel = _texto(f[0]), _texto(f[1]), _texto(f[2])
        cantidad = _entero(f[3])
        if cantidad is None:
            lector.error(HOJA_DETALLE_INV, n, "«Cantidad (X)» debe ser un número entero.")
            continue
        if not codigo:
            lector.error(HOJA_DETALLE_INV, n, "falta el código de cuenta.")
            continue
        if criterio not in CRITERIOS_DETALLE:
            lector.error(HOJA_DETALLE_INV, n, "«Criterio» debe ser «Contacto» o «Producto».")
            continue
        if nivel not in NIVELES_DETALLE:
            lector.error(HOJA_DETALLE_INV, n, "«Nivel» debe ser «Todos» o «Top X».")
            continue
        if NIVELES_DETALLE[nivel] == 'top' and cantidad <= 0:
            lector.error(HOJA_DETALLE_INV, n, "con «Nivel» = «Top X» hay que indicar una cantidad "
                                              "mayor a 0.")
            continue
        real = _cuenta(HOJA_DETALLE_INV, n, codigo)
        if not real:
            continue
        if real.lower() in vistos:
            lector.error(HOJA_DETALLE_INV, n, "la cuenta «%s» está repetida (también en la fila "
                                              "%s)." % (real, vistos[real.lower()]))
            continue
        vistos[real.lower()] = n
        detalle.append({'cuenta': real, 'criterio': CRITERIOS_DETALLE[criterio],
                        'nivel': NIVELES_DETALLE[nivel], 'cantidad': cantidad})
    datos['detalle_inventario'] = detalle

    # --- Renumeración ----------------------------------------------------
    renumeracion, vistos = [], {}
    for n, f in _filas(libro, HOJA_RENUMERACION, lector):
        anio, inicial = _entero(f[0]), _entero(f[1])
        if None in (anio, inicial):
            lector.error(HOJA_RENUMERACION, n, "el año y el número inicial deben ser enteros.")
            continue
        if not 1900 <= anio <= 2200:
            lector.error(HOJA_RENUMERACION, n, "el año «%s» no es razonable." % anio)
            continue
        if inicial < 0:
            lector.error(HOJA_RENUMERACION, n, "el número inicial no puede ser negativo.")
            continue
        if anio in vistos:
            lector.error(HOJA_RENUMERACION, n, "el año %s está repetido (también en la fila %s)."
                         % (anio, vistos[anio]))
            continue
        vistos[anio] = n
        renumeracion.append({'anio': anio, 'numero_inicial': inicial})
    datos['renumeracion'] = renumeracion

    # --- No Retención ----------------------------------------------------
    rucs = _mapa_minusculas(contexto.get('rucs'))
    no_retencion, vistos = [], {}
    for n, f in _filas(libro, HOJA_NO_RETENCION, lector):
        ruc, tipo_ret, resolucion = _texto(f[0]), _texto(f[1]), _texto(f[2])
        desde, hasta = _fecha(f[3]), _fecha(f[4])
        if desde is None or hasta is None:
            lector.error(HOJA_NO_RETENCION, n, "las fechas no son válidas (use AAAA-MM-DD).")
            continue
        faltantes = [e for e, v in (('RUT del Proveedor', ruc), ('Tipo de Retención', tipo_ret),
                                    ('Nro. Resolución', resolucion), ('Fecha Desde', desde),
                                    ('Fecha Hasta', hasta)) if not v]
        if faltantes:
            lector.error(HOJA_NO_RETENCION, n, "faltan datos obligatorios: %s." % ', '.join(faltantes))
            continue
        if tipo_ret not in TIPOS_RETENCION:
            lector.error(HOJA_NO_RETENCION, n, "«Tipo de Retención» debe ser «IVA» o «Renta».")
            continue
        if len(resolucion) > 15:
            lector.error(HOJA_NO_RETENCION, n, "el «Nro. Resolución» no puede tener más de 15 "
                                               "caracteres.")
            continue
        if desde > hasta:
            lector.error(HOJA_NO_RETENCION, n, "«Fecha Desde» no puede ser posterior a «Fecha Hasta».")
            continue
        if contexto.get('rucs') is not None and ruc.lower() not in rucs:
            lector.error(HOJA_NO_RETENCION, n, "no hay ningún contacto con el RUT «%s»." % ruc)
            continue
        clave = (ruc.lower(), TIPOS_RETENCION[tipo_ret], resolucion.lower())
        if clave in vistos:
            lector.error(HOJA_NO_RETENCION, n, "esta resolución está repetida (también en la fila "
                                               "%s)." % vistos[clave])
            continue
        vistos[clave] = n
        no_retencion.append({'ruc': rucs.get(ruc.lower(), ruc),
                             'tipo_retencion': TIPOS_RETENCION[tipo_ret],
                             'nro_resolucion': resolucion, 'fecha_desde': desde,
                             'fecha_hasta': hasta})
    datos['no_retencion'] = no_retencion

    # --- Conceptos Renta No Residente ------------------------------------
    codigos_inr = _mapa_minusculas(contexto.get('codigos_inr'))
    conceptos, vistos = [], {}
    for n, f in _filas(libro, HOJA_INR, lector, saltar_ejemplos=False):
        codigo = _texto(f[0])
        if not codigo:
            lector.error(HOJA_INR, n, "falta el código del concepto.")
            continue
        if contexto.get('codigos_inr') is not None and codigo.lower() not in codigos_inr:
            lector.error(HOJA_INR, n, "el concepto «%s» no existe. Los conceptos vienen cargados "
                                      "con local_py: no se pueden agregar desde la planilla." % codigo)
            continue
        porcentajes = [_numero(f[2]), _numero(f[3]), _numero(f[4])]
        if None in porcentajes:
            lector.error(HOJA_INR, n, "los porcentajes deben ser números.")
            continue
        if any(p < 0 or p > 100 for p in porcentajes):
            lector.error(HOJA_INR, n, "los porcentajes deben estar entre 0 y 100.")
            continue
        if codigo.lower() in vistos:
            lector.error(HOJA_INR, n, "el concepto «%s» está repetido (también en la fila %s)."
                         % (codigo, vistos[codigo.lower()]))
            continue
        vistos[codigo.lower()] = n
        conceptos.append({'codigo': codigos_inr.get(codigo.lower(), codigo),
                          'porcentaje_imputacion': porcentajes[0], 'porcentaje': porcentajes[1],
                          'porcentaje_absorcion': porcentajes[2]})
    datos['conceptos_inr'] = conceptos

    return datos, lector.errores, lector.advertencias


def resumen(datos):
    """Línea de resumen de lo que trae una plantilla ya validada."""
    return ("%d cuenta(s), %d diario(s) operativo(s), %d parámetro(s), %d diario(s) fiscal(es), "
            "%d serie(s) de recibo, %d rúbrica(s), %d chequera(s), %d cuenta(s) con detalle de "
            "inventario, %d año(s) de renumeración, %d resolución(es) de no retención y "
            "%d concepto(s) de Renta No Residente." % (
                len(datos['cuentas']), len(datos['diarios']), len(datos['parametros']),
                len(datos['diarios_fiscales']), len(datos['series_recibo']), len(datos['rubricas']),
                len(datos['chequeras']), len(datos['detalle_inventario']),
                len(datos['renumeracion']), len(datos['no_retencion']), len(datos['conceptos_inr'])))
