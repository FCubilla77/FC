# -*- coding: utf-8 -*-
"""Plantilla Excel del plan de cuentas del cliente: generación, lectura y validación.

Este archivo NO usa el ORM: trabaja con diccionarios simples, así se puede probar sin
base de datos. La estructura de datos (`datos`) es la misma para el plan estándar
(leído de los CSV del módulo) y para el plan del cliente (leído del Excel):

    {
      'grupos':   [{'desde', 'hasta', 'nombre'}],
      'cuentas':  [{'codigo', 'nombre', 'tipo', 'conciliable', 'moneda', 'etiqueta'}],
      'roles':    {clave_rol: codigo_de_cuenta},
      'parametros': {'prefijo_banco', 'prefijo_caja'},
      'grupos_impuestos':   [{'nombre'}],
      'impuestos': [{'nombre', 'uso', 'importe', 'tipo_importe', 'precio_incluido',
                     'incluir_base', 'descripcion', 'grupo', 'cuenta', 'posiciones',
                     'reemplaza', 'defecto'}],
      'posiciones_fiscales': [{'nombre', 'automatica', 'ruc_requerido'}],
      'plazos_pago': [{'nombre', 'lineas': [{'porcentaje', 'dias'}]}],
    }
"""
import csv
import io
import os
import re

from odoo.fields import Command

from .plan_cuentas_report import PLAN_ACCOUNT_TYPE_SELECTION

TIPOS_CUENTA = dict(PLAN_ACCOUNT_TYPE_SELECTION)
CODIGO_CUENTA_REGEX = re.compile(r'^[A-Za-z0-9.]+$')

TIPOS_ACTIVO = tuple(t for t in TIPOS_CUENTA if t.startswith('asset_'))
TIPOS_PASIVO = tuple(t for t in TIPOS_CUENTA if t.startswith('liability_'))
TIPOS_INGRESO_ROL = ('income', 'income_other')
TIPOS_GASTO_ROL = ('expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')

# Etiquetas propias del módulo para cuentas de IVA (data/account_account_tag_data.xml).
ETIQUETAS_IVA = {
    'Crédito fiscal': 'l10n_py.tag_iva_credito_fiscal',
    'Débito fiscal': 'l10n_py.tag_iva_debito_fiscal',
}

# Cuentas que el paquete le asigna a la compañía y a los diarios. Cada rol se completa en
# la hoja «Configuración» con el CÓDIGO de una cuenta de la hoja «Cuentas».
#   clave, descripción, obligatorio, tipos permitidos (None = cualquiera),
#   id de la cuenta en el plan estándar, id especial (Odoo lo busca por ese nombre)
ROLES = [
    ('cuenta_cobrar', 'Cuenta por cobrar (clientes)', True, ('asset_receivable',),
     'py_1_01_03_01_001', None),
    ('cuenta_pagar', 'Cuenta por pagar (proveedores)', True, ('liability_payable',),
     'py_2_01_01_01_001', None),
    ('cuenta_ingreso', 'Cuenta de ingreso por defecto (categorías de producto)', True,
     TIPOS_INGRESO_ROL, 'py_4_01_01_01_001', None),
    ('cuenta_gasto', 'Cuenta de gasto por defecto (categorías de producto)', True,
     TIPOS_GASTO_ROL, 'py_5_01_01_01_001', None),
    ('cuenta_resultado_ejercicio',
     'Resultado del Ejercicio (recibe el resultado en el Cierre de Ejercicio)', True,
     ('equity', 'equity_unaffected'), 'py_3_03_01_01_002', None),
    ('cuenta_transferencia', 'Transferencias internas de liquidez', False, None,
     'py_1_01_01_01_002', None),
    ('cuenta_banco_defecto', 'Cuenta del diario de banco de ejemplo', False, None,
     'py_1_01_01_03_003', None),
    ('cuenta_transitoria_banco', 'Cuenta transitoria de conciliación bancaria', False, None,
     'py_1_01_01_03_004', None),
    ('cuenta_recibos_pendientes', 'Recibos pendientes (pagos de clientes sin conciliar)', False,
     None, 'account_journal_payment_debit_account_id', 'account_journal_payment_debit_account_id'),
    ('cuenta_pagos_pendientes', 'Pagos pendientes (pagos a proveedores sin conciliar)', False,
     None, 'account_journal_payment_credit_account_id', 'account_journal_payment_credit_account_id'),
    ('dif_cambio_ganancia', 'Diferencia de cambio: ganancia', False, None,
     'py_6_01_01_01_005', None),
    ('dif_cambio_perdida', 'Diferencia de cambio: pérdida', False, None,
     'py_7_03_01_02_001', None),
    ('dif_efectivo_ganancia', 'Diferencia de caja (redondeo): ganancia', False, None,
     'py_7_02_18_01_002', None),
    ('dif_efectivo_perdida', 'Diferencia de caja (redondeo): pérdida', False, None,
     'py_7_02_18_01_002', None),
    ('descuento_pronto_pago_perdida',
     'Descuento por pronto pago concedido a clientes', False, None, 'py_4_01_98_01_001', None),
    ('descuento_pronto_pago_ganancia',
     'Descuento por pronto pago obtenido de proveedores', False, None, 'py_6_01_01_01_003', None),
    ('valoracion_inventario', 'Valoración de inventario', False, None,
     'py_1_01_04_01_001', None),
]
ROLES_POR_CLAVE = {r[0]: r for r in ROLES}

PARAMETROS = [
    ('prefijo_banco', 'Prefijo de código para las cuentas de banco nuevas', '1.01.01.03.'),
    ('prefijo_caja', 'Prefijo de código para las cuentas de caja nuevas', '1.01.01.01.'),
]

HOJA_INSTRUCCIONES = 'Instrucciones'
HOJA_GRUPOS = 'Grupos'
HOJA_CUENTAS = 'Cuentas'
HOJA_CONFIG = 'Configuración'
HOJA_GRUPOS_IMP = 'Grupos de impuestos'
HOJA_IMPUESTOS = 'Impuestos'
HOJA_POSICIONES = 'Posiciones fiscales'
HOJA_PLAZOS = 'Plazos de pago'
HOJA_TIPOS = 'Tipos de cuenta'

ENCABEZADOS = {
    HOJA_GRUPOS: ['Código desde', 'Código hasta', 'Nombre'],
    HOJA_CUENTAS: ['Código', 'Nombre', 'Tipo de cuenta', 'Conciliable', 'Moneda', 'Etiqueta IVA'],
    HOJA_CONFIG: ['Clave', 'Descripción', 'Valor'],
    HOJA_GRUPOS_IMP: ['Nombre'],
    HOJA_IMPUESTOS: ['Nombre', 'Uso', 'Importe', 'Tipo de importe', 'Precio incluye el impuesto',
                     'Incluir en la base de otros impuestos', 'Descripción', 'Grupo de impuestos',
                     'Cuenta del impuesto', 'Posiciones fiscales', 'Reemplaza a',
                     'Por defecto'],
    HOJA_POSICIONES: ['Nombre', 'Aplicar automáticamente', 'RUC requerido'],
    HOJA_PLAZOS: ['Nombre', 'Porcentaje', 'Días'],
}
USOS = {'Venta': 'sale', 'Compra': 'purchase'}
USOS_INV = {v: k for k, v in USOS.items()}
TIPOS_IMPORTE = {'Porcentaje': 'percent', 'Importe fijo': 'fixed'}
TIPOS_IMPORTE_INV = {v: k for k, v in TIPOS_IMPORTE.items()}


def slug(codigo):
    return re.sub(r'[^a-z0-9]+', '_', str(codigo).lower()).strip('_')


# ---------------------------------------------------------------------------
# Plan estándar (CSV del módulo) -> datos
# ---------------------------------------------------------------------------

def _leer_csv(ruta_modulo, nombre):
    ruta = os.path.join(ruta_modulo, 'data', 'template', nombre)
    with open(ruta, encoding='utf-8', newline='') as archivo:
        return list(csv.DictReader(archivo))


def _bool(texto):
    return str(texto).strip().lower() in ('true', '1', 'si', 'sí')


def datos_estandar(ruta_modulo):
    """Datos del plan estándar Paraguay, tal como los carga hoy el paquete."""
    filas_grupos = _leer_csv(ruta_modulo, 'account.group-py.csv')
    filas_cuentas = _leer_csv(ruta_modulo, 'account.account-py.csv')
    id_a_codigo = {f['id']: f['code'] for f in filas_cuentas}
    etiqueta_inv = {v: k for k, v in ETIQUETAS_IVA.items()}

    datos = {
        'grupos': [{'desde': f['code_prefix_start'], 'hasta': f['code_prefix_end'],
                    'nombre': f['name']} for f in filas_grupos],
        'cuentas': [{
            'codigo': f['code'], 'nombre': f['name'], 'tipo': f['account_type'],
            'conciliable': _bool(f['reconcile']),
            'moneda': (f['currency_id'] or '').replace('base.', ''),
            'etiqueta': etiqueta_inv.get(f['tag_ids'], ''),
        } for f in filas_cuentas],
        'roles': {r[0]: id_a_codigo.get(r[4], '') for r in ROLES},
        'parametros': {clave: valor for clave, _desc, valor in PARAMETROS},
    }

    datos['grupos_impuestos'] = [
        {'nombre': f['name']} for f in _leer_csv(ruta_modulo, 'account.tax.group-py.csv')]
    id_grupo_imp = {f['id']: f['name'] for f in _leer_csv(ruta_modulo, 'account.tax.group-py.csv')}

    filas_pos = _leer_csv(ruta_modulo, 'account.fiscal.position-py.csv')
    id_pos = {f['id']: f['name'] for f in filas_pos}
    datos['posiciones_fiscales'] = [{
        'nombre': f['name'], 'automatica': _bool(f['auto_apply']),
        'ruc_requerido': _bool(f['vat_required'])} for f in filas_pos]

    impuestos, id_imp = [], {}
    for fila in _leer_csv(ruta_modulo, 'account.tax-py.csv'):
        if fila['id']:
            impuesto = {
                'id': fila['id'], 'nombre': fila['name'], 'uso': USOS_INV[fila['type_tax_use']],
                'importe': float(fila['amount']),
                'tipo_importe': TIPOS_IMPORTE_INV[fila['amount_type']],
                'precio_incluido': fila['price_include_override'] == 'tax_included',
                'incluir_base': _bool(fila['include_base_amount']),
                'descripcion': fila['description'],
                'grupo': id_grupo_imp.get(fila['tax_group_id'], ''), 'cuenta': '',
                'posiciones': [id_pos[p] for p in fila['fiscal_position_ids'].split(',') if p],
                'reemplaza_ids': [p for p in fila['original_tax_ids'].split(',') if p],
                'defecto': False,
            }
            impuestos.append(impuesto)
            id_imp[fila['id']] = impuesto
        if (fila['repartition_line_ids/repartition_type'] == 'tax'
                and fila['repartition_line_ids/document_type'] == 'invoice'):
            impuestos[-1]['cuenta'] = id_a_codigo.get(fila['repartition_line_ids/account_id'], '')
    for impuesto in impuestos:
        impuesto['reemplaza'] = [id_imp[i]['nombre'] for i in impuesto.pop('reemplaza_ids')]
        impuesto.pop('id')
    id_imp['tax_iva_10_ventas']['defecto'] = True
    id_imp['tax_iva_10_compras']['defecto'] = True
    datos['impuestos'] = impuestos

    plazos = []
    for fila in _leer_csv(ruta_modulo, 'account.payment.term-py.csv'):
        if fila['id']:
            plazos.append({'nombre': fila['name'], 'lineas': []})
        plazos[-1]['lineas'].append({
            'porcentaje': float(fila['line_ids/value_amount']),
            'dias': int(fila['line_ids/nb_days'])})
    datos['plazos_pago'] = plazos
    return datos


# ---------------------------------------------------------------------------
# datos -> Excel
# ---------------------------------------------------------------------------

def _si_no(valor):
    return 'SI' if valor else 'NO'


INSTRUCCIONES = [
    'PLANTILLA DEL PLAN DE CUENTAS — Paraguay - Contabilidad (l10n_py)',
    '',
    'Esta planilla trae cargado el plan estándar Paraguay como ejemplo. Reemplace los datos por los de su empresa y '
    'cárguela en Ajustes > Configuración l10n_py > Plan de cuentas del cliente.',
    '',
    'Reglas generales:',
    '• No cambie los nombres de las hojas ni los encabezados de la fila 1. Los datos empiezan en la fila 2.',
    '• Hoja «Cuentas»: el código solo puede tener letras, números y puntos, y no puede repetirse. El tipo de cuenta se elige de la lista (ver hoja «Tipos de cuenta»).',
    '• Hoja «Grupos»: cada grupo abarca un rango de códigos (desde/hasta, con igual cantidad de caracteres). Los grupos de rangos más cortos contienen a los más largos. Es opcional.',
    '• Hoja «Configuración»: indique, con el CÓDIGO de una cuenta de la hoja «Cuentas», qué cuenta cumple cada función. Los roles marcados como obligatorios no pueden quedar vacíos.',
    '• Hoja «Impuestos»: «Por defecto» = SI en un solo impuesto de venta y uno de compra. «Posiciones fiscales» y «Reemplaza a» se separan con «;» y usan nombres de las otras hojas.',
    '• Hoja «Plazos de pago»: un plazo puede tener varias cuotas; deje vacío el nombre en las filas siguientes para sumar cuotas al mismo plazo (los porcentajes deben sumar 100).',
    '• Impuestos, posiciones fiscales y plazos son sugerencias iniciales: después de la carga se administran desde el sistema.',
    '',
    'IMPORTANTE: la plantilla se usa SOLO para la carga inicial. Una vez cargado el plan, los cambios se hacen en el sistema, no en este archivo.',
]


def generar_libro(datos):
    """Devuelve el contenido (bytes) de un .xlsx con `datos` volcados en las hojas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    libro = Workbook()
    negrita = Font(bold=True, color='FFFFFF')
    relleno = PatternFill('solid', fgColor='4F6D8F')

    def hoja_nueva(nombre, anchos, codigo_texto=()):
        hoja = libro.create_sheet(nombre)
        hoja.append(ENCABEZADOS[nombre])
        for col, ancho in enumerate(anchos, start=1):
            hoja.column_dimensions[chr(64 + col)].width = ancho
            celda = hoja.cell(row=1, column=col)
            celda.font, celda.fill = negrita, relleno
            celda.alignment = Alignment(wrap_text=True, vertical='center')
        hoja.freeze_panes = 'A2'
        return hoja

    def formato_texto(hoja, columnas, hasta_fila):
        for fila in range(2, hasta_fila + 1):
            for col in columnas:
                hoja.cell(row=fila, column=col).number_format = '@'

    def lista(hoja, columna, opciones, hasta_fila):
        validacion = DataValidation(
            type='list', formula1='"%s"' % ','.join(opciones), allow_blank=True)
        hoja.add_data_validation(validacion)
        validacion.add('%s2:%s%d' % (columna, columna, hasta_fila))

    instrucciones = libro.active
    instrucciones.title = HOJA_INSTRUCCIONES
    instrucciones.column_dimensions['A'].width = 130
    for texto in INSTRUCCIONES:
        instrucciones.append([texto])
        instrucciones.cell(row=instrucciones.max_row, column=1).alignment = Alignment(wrap_text=True)
    instrucciones['A1'].font = Font(bold=True, size=14)

    hoja = hoja_nueva(HOJA_GRUPOS, [16, 16, 50])
    for g in datos['grupos']:
        hoja.append([g['desde'], g['hasta'], g['nombre']])
    formato_texto(hoja, (1, 2), max(len(datos['grupos']) + 1, 500))

    hoja = hoja_nueva(HOJA_CUENTAS, [20, 55, 22, 12, 10, 16])
    for c in datos['cuentas']:
        hoja.append([c['codigo'], c['nombre'], c['tipo'], _si_no(c['conciliable']),
                     c['moneda'], c['etiqueta']])
    limite = max(len(datos['cuentas']) + 1, 1000)
    formato_texto(hoja, (1,), limite)
    lista(hoja, 'C', list(TIPOS_CUENTA), limite)
    lista(hoja, 'D', ['SI', 'NO'], limite)
    lista(hoja, 'F', list(ETIQUETAS_IVA), limite)

    hoja = hoja_nueva(HOJA_CONFIG, [34, 70, 24])
    for clave, descripcion, obligatorio, _tipos, _std, _esp in ROLES:
        hoja.append([clave, descripcion + (' (OBLIGATORIO)' if obligatorio else ''),
                     datos['roles'].get(clave, '')])
    for clave, descripcion, _std in PARAMETROS:
        hoja.append([clave, descripcion, datos['parametros'].get(clave, '')])
    formato_texto(hoja, (3,), hoja.max_row)

    hoja = hoja_nueva(HOJA_GRUPOS_IMP, [30])
    for g in datos['grupos_impuestos']:
        hoja.append([g['nombre']])

    hoja = hoja_nueva(HOJA_IMPUESTOS, [26, 10, 10, 16, 16, 20, 28, 20, 20, 28, 30, 11])
    for i in datos['impuestos']:
        hoja.append([
            i['nombre'], i['uso'], i['importe'], i['tipo_importe'], _si_no(i['precio_incluido']),
            _si_no(i['incluir_base']), i['descripcion'], i['grupo'], i['cuenta'],
            ';'.join(i['posiciones']), ';'.join(i['reemplaza']), _si_no(i['defecto'])])
    limite = max(len(datos['impuestos']) + 1, 100)
    formato_texto(hoja, (9,), limite)
    lista(hoja, 'B', list(USOS), limite)
    lista(hoja, 'D', list(TIPOS_IMPORTE), limite)
    lista(hoja, 'E', ['SI', 'NO'], limite)
    lista(hoja, 'F', ['SI', 'NO'], limite)
    lista(hoja, 'L', ['SI', 'NO'], limite)

    hoja = hoja_nueva(HOJA_POSICIONES, [30, 22, 16])
    for p in datos['posiciones_fiscales']:
        hoja.append([p['nombre'], _si_no(p['automatica']), _si_no(p['ruc_requerido'])])
    lista(hoja, 'B', ['SI', 'NO'], 100)
    lista(hoja, 'C', ['SI', 'NO'], 100)

    hoja = hoja_nueva(HOJA_PLAZOS, [30, 12, 10])
    for plazo in datos['plazos_pago']:
        for indice, linea in enumerate(plazo['lineas']):
            hoja.append([plazo['nombre'] if indice == 0 else None, linea['porcentaje'], linea['dias']])

    hoja = libro.create_sheet(HOJA_TIPOS)
    hoja.append(['Tipo de cuenta (clave técnica)', 'Descripción'])
    hoja.column_dimensions['A'].width = 34
    hoja.column_dimensions['B'].width = 30
    for clave, descripcion in PLAN_ACCOUNT_TYPE_SELECTION:
        hoja.append([clave, descripcion])

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


def _filas(libro, nombre, lector):
    """Filas de datos (desde la 2) como (número_de_fila, [valores]) sin las vacías."""
    if nombre not in libro.sheetnames:
        lector.error(nombre, None, "no se encontró la hoja. No cambie los nombres de las hojas.")
        return []
    hoja = libro[nombre]
    esperado = ENCABEZADOS[nombre]
    actual = [_texto(c.value) for c in next(hoja.iter_rows(min_row=1, max_row=1, max_col=len(esperado)))]
    if actual != esperado:
        lector.error(nombre, 1, "los encabezados no coinciden con la plantilla (se esperaba: %s)." % ' | '.join(esperado))
        return []
    resultado = []
    for numero, fila in enumerate(hoja.iter_rows(min_row=2, max_col=len(esperado), values_only=True), start=2):
        if any(_texto(v) for v in fila):
            resultado.append((numero, list(fila)))
    return resultado


def leer_libro(contenido, monedas_validas=None):
    """Lee y valida un .xlsx. Devuelve (datos, errores, advertencias); si hay errores,
    `datos` no debe usarse. `monedas_validas`: códigos ISO existentes (None = no validar)."""
    from openpyxl import load_workbook

    lector = _Lector()
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True)
    except Exception as exc:  # archivo ilegible: no es un .xlsx válido
        return None, ["No se pudo abrir el archivo como Excel (.xlsx): %s" % exc], []

    datos = {}

    # --- Grupos ---------------------------------------------------------
    grupos, vistos = [], set()
    for n, f in _filas(libro, HOJA_GRUPOS, lector):
        desde, hasta, nombre = _texto(f[0]), _texto(f[1]) or _texto(f[0]), _texto(f[2])
        if not desde or not nombre:
            lector.error(HOJA_GRUPOS, n, "faltan el código o el nombre.")
            continue
        for c in (desde, hasta):
            if not CODIGO_CUENTA_REGEX.match(c):
                lector.error(HOJA_GRUPOS, n, "el código «%s» solo puede tener letras, números y puntos." % c)
        if len(desde) != len(hasta):
            lector.error(HOJA_GRUPOS, n, "«desde» y «hasta» deben tener la misma cantidad de caracteres.")
        elif desde > hasta:
            lector.error(HOJA_GRUPOS, n, "«desde» no puede ser mayor que «hasta».")
        if (desde, hasta) in vistos:
            lector.error(HOJA_GRUPOS, n, "el rango %s-%s está repetido." % (desde, hasta))
        vistos.add((desde, hasta))
        grupos.append({'desde': desde, 'hasta': hasta, 'nombre': nombre, '_fila': n})
    for i, a in enumerate(grupos):
        for b in grupos[i + 1:]:
            if len(a['desde']) == len(b['desde']) and a['desde'] <= b['hasta'] and b['desde'] <= a['hasta'] \
                    and (a['desde'], a['hasta']) != (b['desde'], b['hasta']):
                lector.error(HOJA_GRUPOS, b['_fila'],
                             "el rango %s-%s se superpone con %s-%s (los grupos del mismo largo no pueden superponerse)."
                             % (b['desde'], b['hasta'], a['desde'], a['hasta']))
    datos['grupos'] = [{k: v for k, v in g.items() if k != '_fila'} for g in grupos]

    # --- Cuentas --------------------------------------------------------
    cuentas, codigos = [], {}
    for n, f in _filas(libro, HOJA_CUENTAS, lector):
        codigo, nombre, tipo = _texto(f[0]), _texto(f[1]), _texto(f[2])
        conciliable, moneda, etiqueta = _flag(f[3]), _texto(f[4]).upper(), _texto(f[5])
        if isinstance(f[0], float):
            lector.error(HOJA_CUENTAS, n, "el código «%s» se leyó como número decimal; formatee la columna como texto." % f[0])
            continue
        if not codigo or not nombre:
            lector.error(HOJA_CUENTAS, n, "faltan el código o el nombre.")
            continue
        if not CODIGO_CUENTA_REGEX.match(codigo):
            lector.error(HOJA_CUENTAS, n, "el código «%s» solo puede tener letras, números y puntos." % codigo)
        if codigo.lower() in codigos:
            lector.error(HOJA_CUENTAS, n, "el código «%s» está repetido (también en la fila %s)." % (codigo, codigos[codigo.lower()]))
        codigos.setdefault(codigo.lower(), n)
        if tipo not in TIPOS_CUENTA:
            lector.error(HOJA_CUENTAS, n, "tipo de cuenta «%s» inválido (ver hoja «Tipos de cuenta»)." % tipo)
        if conciliable is None:
            lector.error(HOJA_CUENTAS, n, "«Conciliable» debe ser SI o NO.")
        if moneda and monedas_validas is not None and moneda not in monedas_validas:
            lector.error(HOJA_CUENTAS, n, "la moneda «%s» no existe." % moneda)
        if etiqueta and etiqueta not in ETIQUETAS_IVA:
            lector.error(HOJA_CUENTAS, n, "etiqueta IVA «%s» inválida (use «Crédito fiscal» o «Débito fiscal»)." % etiqueta)
        if tipo in ('asset_receivable', 'liability_payable') and conciliable is False:
            lector.aviso(HOJA_CUENTAS, n, "las cuentas por cobrar/pagar deberían ser conciliables.")
        cuentas.append({'codigo': codigo, 'nombre': nombre, 'tipo': tipo,
                        'conciliable': bool(conciliable), 'moneda': moneda, 'etiqueta': etiqueta})
    if not cuentas and not any('Cuentas' in e for e in lector.errores):
        lector.error(HOJA_CUENTAS, None, "no hay ninguna cuenta cargada.")
    datos['cuentas'] = cuentas
    cuenta_por_codigo = {c['codigo'].lower(): c for c in cuentas}
    nombres = {}
    for c in cuentas:
        nombres.setdefault(c['nombre'].lower(), []).append(c['codigo'])
    for nombre, lista_codigos in nombres.items():
        if len(lista_codigos) > 1:
            lector.aviso(HOJA_CUENTAS, None, "hay cuentas con el mismo nombre «%s»: %s." % (nombre, ', '.join(lista_codigos)))

    # --- Configuración (roles y parámetros) -----------------------------
    roles, parametros = {}, {}
    filas_config = _filas(libro, HOJA_CONFIG, lector)
    claves_roles = set(ROLES_POR_CLAVE)
    claves_param = {p[0] for p in PARAMETROS}
    vistas = set()
    for n, f in filas_config:
        clave, valor = _texto(f[0]), _texto(f[2])
        if clave in vistas:
            lector.error(HOJA_CONFIG, n, "la clave «%s» está repetida." % clave)
        vistas.add(clave)
        if clave in claves_roles:
            roles[clave] = valor
        elif clave in claves_param:
            parametros[clave] = valor
        else:
            lector.aviso(HOJA_CONFIG, n, "la clave «%s» no se reconoce y se ignora." % clave)
    for clave, _desc, obligatorio, tipos, _std, _esp in ROLES:
        valor = roles.get(clave, '')
        if not valor:
            if obligatorio:
                lector.error(HOJA_CONFIG, None, "falta la cuenta del rol obligatorio «%s»." % clave)
            else:
                lector.aviso(HOJA_CONFIG, None, "no se definió «%s»: Odoo creará su propia cuenta (con nombre en inglés) cuando la necesite." % clave)
            continue
        cuenta = cuenta_por_codigo.get(valor.lower())
        if not cuenta:
            lector.error(HOJA_CONFIG, None, "«%s»: el código «%s» no existe en la hoja «Cuentas»." % (clave, valor))
            continue
        roles[clave] = cuenta['codigo']
        if tipos and cuenta['tipo'] not in tipos:
            mensaje = "«%s»: la cuenta %s es de tipo «%s» y se esperaba: %s." % (
                clave, cuenta['codigo'], cuenta['tipo'], ', '.join(tipos))
            if obligatorio:
                lector.error(HOJA_CONFIG, None, mensaje)
            else:
                lector.aviso(HOJA_CONFIG, None, mensaje)
        if clave in ('cuenta_recibos_pendientes', 'cuenta_pagos_pendientes', 'cuenta_transferencia') \
                and not cuenta['conciliable']:
            lector.aviso(HOJA_CONFIG, None, "«%s»: la cuenta %s debería ser conciliable." % (clave, cuenta['codigo']))
    if roles.get('cuenta_recibos_pendientes') and roles.get('cuenta_recibos_pendientes') == roles.get('cuenta_pagos_pendientes'):
        lector.error(HOJA_CONFIG, None, "Recibos pendientes y Pagos pendientes deben ser cuentas distintas.")
    for clave, _desc, _std in PARAMETROS:
        if not parametros.get(clave):
            lector.aviso(HOJA_CONFIG, None, "no se definió «%s»: se usará el valor predeterminado de Odoo." % clave)
    datos['roles'] = roles
    datos['parametros'] = parametros

    # --- Grupos de impuestos / posiciones fiscales ----------------------
    grupos_imp = []
    for n, f in _filas(libro, HOJA_GRUPOS_IMP, lector):
        nombre = _texto(f[0])
        if nombre.lower() in [g['nombre'].lower() for g in grupos_imp]:
            lector.error(HOJA_GRUPOS_IMP, n, "el grupo «%s» está repetido." % nombre)
        grupos_imp.append({'nombre': nombre})
    datos['grupos_impuestos'] = grupos_imp
    nombres_grupos_imp = {g['nombre'].lower() for g in grupos_imp}

    posiciones = []
    for n, f in _filas(libro, HOJA_POSICIONES, lector):
        nombre, auto, ruc = _texto(f[0]), _flag(f[1]), _flag(f[2])
        if not nombre:
            lector.error(HOJA_POSICIONES, n, "falta el nombre.")
            continue
        if nombre.lower() in [p['nombre'].lower() for p in posiciones]:
            lector.error(HOJA_POSICIONES, n, "la posición fiscal «%s» está repetida." % nombre)
        if auto is None or ruc is None:
            lector.error(HOJA_POSICIONES, n, "«Aplicar automáticamente» y «RUC requerido» deben ser SI o NO.")
        posiciones.append({'nombre': nombre, 'automatica': bool(auto), 'ruc_requerido': bool(ruc)})
    datos['posiciones_fiscales'] = posiciones
    nombres_pos = {p['nombre'].lower() for p in posiciones}

    # --- Impuestos ------------------------------------------------------
    impuestos, claves_imp = [], {}
    for n, f in _filas(libro, HOJA_IMPUESTOS, lector):
        nombre, uso_txt, tipo_txt = _texto(f[0]), _texto(f[1]), _texto(f[3])
        if not nombre:
            lector.error(HOJA_IMPUESTOS, n, "falta el nombre.")
            continue
        if uso_txt not in USOS:
            lector.error(HOJA_IMPUESTOS, n, "«Uso» debe ser Venta o Compra.")
            continue
        if tipo_txt not in TIPOS_IMPORTE:
            lector.error(HOJA_IMPUESTOS, n, "«Tipo de importe» debe ser Porcentaje o Importe fijo.")
            continue
        try:
            importe = float(_texto(f[2]).replace(',', '.'))
        except ValueError:
            lector.error(HOJA_IMPUESTOS, n, "el importe «%s» no es un número." % _texto(f[2]))
            continue
        precio, base, defecto = _flag(f[4]), _flag(f[5]), _flag(f[11])
        if None in (precio, base, defecto):
            lector.error(HOJA_IMPUESTOS, n, "«Precio incluye», «Incluir en la base» y «Por defecto» deben ser SI o NO.")
            continue
        grupo = _texto(f[7])
        if not grupo or grupo.lower() not in nombres_grupos_imp:
            lector.error(HOJA_IMPUESTOS, n, "el grupo de impuestos «%s» no existe en la hoja «Grupos de impuestos»." % grupo)
        cuenta = _texto(f[8])
        if isinstance(f[8], float):
            lector.error(HOJA_IMPUESTOS, n, "el código de cuenta se leyó como número decimal; formatee la columna como texto.")
            continue
        if cuenta and cuenta.lower() not in cuenta_por_codigo:
            lector.error(HOJA_IMPUESTOS, n, "la cuenta «%s» no existe en la hoja «Cuentas»." % cuenta)
        elif not cuenta:
            lector.aviso(HOJA_IMPUESTOS, n, "el impuesto «%s» no tiene cuenta: el IVA no se contabilizará en una cuenta propia." % nombre)
        else:
            cuenta = cuenta_por_codigo[cuenta.lower()]['codigo']
        pos = [p.strip() for p in _texto(f[9]).split(';') if p.strip()]
        for p in pos:
            if p.lower() not in nombres_pos:
                lector.error(HOJA_IMPUESTOS, n, "la posición fiscal «%s» no existe en la hoja «Posiciones fiscales»." % p)
        reemplaza = [p.strip() for p in _texto(f[10]).split(';') if p.strip()]
        clave = (nombre.lower(), USOS[uso_txt])
        if clave in claves_imp:
            lector.error(HOJA_IMPUESTOS, n, "ya existe un impuesto «%s» de %s." % (nombre, uso_txt.lower()))
        claves_imp[clave] = n
        impuestos.append({
            'nombre': nombre, 'uso': uso_txt, 'importe': importe, 'tipo_importe': tipo_txt,
            'precio_incluido': bool(precio), 'incluir_base': bool(base),
            'descripcion': _texto(f[6]) or nombre, 'grupo': grupo, 'cuenta': cuenta,
            'posiciones': pos, 'reemplaza': reemplaza, 'defecto': bool(defecto), '_fila': n})
    nombres_imp = {i['nombre'].lower() for i in impuestos}
    for i in impuestos:
        for r in i['reemplaza']:
            if r.lower() not in nombres_imp:
                lector.error(HOJA_IMPUESTOS, i['_fila'], "«Reemplaza a»: el impuesto «%s» no existe." % r)
    for uso in ('Venta', 'Compra'):
        marcados = [i for i in impuestos if i['uso'] == uso and i['defecto']]
        if len(marcados) > 1:
            lector.error(HOJA_IMPUESTOS, marcados[1]['_fila'], "solo un impuesto de %s puede ser «Por defecto»." % uso.lower())
        if impuestos and not marcados:
            lector.aviso(HOJA_IMPUESTOS, None, "ningún impuesto de %s está marcado «Por defecto»." % uso.lower())
    datos['impuestos'] = [{k: v for k, v in i.items() if k != '_fila'} for i in impuestos]

    # --- Plazos de pago -------------------------------------------------
    plazos = []
    for n, f in _filas(libro, HOJA_PLAZOS, lector):
        nombre = _texto(f[0])
        try:
            porcentaje = float(_texto(f[1]).replace(',', '.'))
            dias = int(float(_texto(f[2]) or 0))
        except ValueError:
            lector.error(HOJA_PLAZOS, n, "el porcentaje y los días deben ser números.")
            continue
        if dias < 0:
            lector.error(HOJA_PLAZOS, n, "los días no pueden ser negativos.")
        if nombre:
            if nombre.lower() in [p['nombre'].lower() for p in plazos]:
                lector.error(HOJA_PLAZOS, n, "el plazo «%s» está repetido." % nombre)
            plazos.append({'nombre': nombre, 'lineas': [], '_fila': n})
        elif not plazos:
            lector.error(HOJA_PLAZOS, n, "la primera fila debe tener el nombre del plazo.")
            continue
        plazos[-1]['lineas'].append({'porcentaje': porcentaje, 'dias': dias})
    for p in plazos:
        if abs(sum(l['porcentaje'] for l in p['lineas']) - 100.0) > 0.001:
            lector.error(HOJA_PLAZOS, p['_fila'], "los porcentajes del plazo «%s» deben sumar 100." % p['nombre'])
    datos['plazos_pago'] = [{k: v for k, v in p.items() if k != '_fila'} for p in plazos]

    return datos, lector.errores, lector.advertencias


# ---------------------------------------------------------------------------
# datos -> registros para el motor de plantillas de Odoo (account.chart.template)
# ---------------------------------------------------------------------------

def id_cuenta(datos, codigo):
    """Id de plantilla de la cuenta con ese código. Las dos cuentas de Recibos/Pagos
    pendientes llevan el id especial que Odoo busca por nombre."""
    for clave in ('cuenta_recibos_pendientes', 'cuenta_pagos_pendientes'):
        if datos['roles'].get(clave) == codigo:
            return ROLES_POR_CLAVE[clave][5]
    return 'cli_' + slug(codigo)


def id_rol(datos, clave):
    """Id de plantilla de la cuenta del rol, o None si el rol quedó vacío."""
    codigo = datos['roles'].get(clave)
    return id_cuenta(datos, codigo) if codigo else None


def id_impuesto_defecto(datos, uso):
    for numero, impuesto in enumerate(datos['impuestos'], start=1):
        if impuesto['uso'] == uso and impuesto['defecto']:
            return 'cli_tax_%d' % numero
    return None


def code_digits(datos):
    """Largo del código más largo: así Odoo no rellena con ceros los códigos más cortos."""
    return max([len(c['codigo']) for c in datos['cuentas']] or [1])


def registros_odoo(datos):
    """{modelo: {id_plantilla: valores}} con el mismo formato que devuelve `_parse_csv`."""
    r = {}
    r['account.group'] = {
        'cli_grp_%s_%s' % (slug(g['desde']), slug(g['hasta'])): {
            'name': g['nombre'], 'code_prefix_start': g['desde'], 'code_prefix_end': g['hasta']}
        for g in datos['grupos']}

    cuentas = {}
    for c in datos['cuentas']:
        vals = {'name': c['nombre'], 'code': c['codigo'], 'account_type': c['tipo'],
                'reconcile': bool(c['conciliable'])}
        if c['moneda']:
            vals['currency_id'] = 'base.%s' % c['moneda']
        if c['etiqueta']:
            vals['tag_ids'] = ETIQUETAS_IVA[c['etiqueta']]
        cuentas[id_cuenta(datos, c['codigo'])] = vals
    r['account.account'] = cuentas

    id_grupo = {}
    r['account.tax.group'] = {}
    for n, g in enumerate(datos['grupos_impuestos'], start=1):
        id_grupo[g['nombre'].lower()] = 'cli_tg_%d' % n
        r['account.tax.group']['cli_tg_%d' % n] = {'name': g['nombre'], 'country_id': 'base.py'}

    id_pos = {}
    r['account.fiscal.position'] = {}
    for n, p in enumerate(datos['posiciones_fiscales'], start=1):
        id_pos[p['nombre'].lower()] = 'cli_fp_%d' % n
        r['account.fiscal.position']['cli_fp_%d' % n] = {
            'name': p['nombre'], 'auto_apply': bool(p['automatica']),
            'vat_required': bool(p['ruc_requerido'])}

    id_imp = {i['nombre'].lower(): 'cli_tax_%d' % n for n, i in enumerate(datos['impuestos'], start=1)}
    r['account.tax'] = {}
    for n, i in enumerate(datos['impuestos'], start=1):
        cuenta = id_cuenta(datos, i['cuenta']) if i['cuenta'] else None

        def linea(tipo, documento):
            vals = {'repartition_type': tipo, 'document_type': documento, 'factor_percent': 100.0}
            if tipo == 'tax' and cuenta:
                vals['account_id'] = cuenta
            return Command.create(vals)

        vals = {
            'name': i['nombre'], 'type_tax_use': USOS[i['uso']], 'amount': i['importe'],
            'amount_type': TIPOS_IMPORTE[i['tipo_importe']],
            'include_base_amount': bool(i['incluir_base']),
            'description': i['descripcion'], 'tax_group_id': id_grupo[i['grupo'].lower()],
            'repartition_line_ids': [
                linea('base', 'invoice'), linea('tax', 'invoice'),
                linea('base', 'refund'), linea('tax', 'refund')],
        }
        if i['precio_incluido']:
            vals['price_include_override'] = 'tax_included'
        if i['posiciones']:
            vals['fiscal_position_ids'] = ','.join(id_pos[p.lower()] for p in i['posiciones'])
        if i['reemplaza']:
            vals['original_tax_ids'] = ','.join(id_imp[x.lower()] for x in i['reemplaza'])
        r['account.tax']['cli_tax_%d' % n] = vals

    r['account.payment.term'] = {}
    for n, p in enumerate(datos['plazos_pago'], start=1):
        r['account.payment.term']['cli_pt_%d' % n] = {
            'name': p['nombre'],
            'line_ids': [Command.create({
                'value': 'percent', 'value_amount': l['porcentaje'], 'nb_days': l['dias'],
                'delay_type': 'days_after'}) for l in p['lineas']],
        }
    return r
