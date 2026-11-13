#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificaciones estáticas de local_py — no necesita Odoo ni base de datos.

Uso, desde la carpeta del módulo:

    python3 verificar.py          # resumen (los primeros 25 avisos)
    python3 verificar.py -v       # todos los avisos

Para qué sirve: `py_compile` solo ve errores de sintaxis. Lo que rompe una
instalación de Odoo es otra cosa — un campo que una vista nombra y el modelo no
declara, un `model_id:id` de la ACL que no existe, un `env.ref()` a un id que se
renombró, sintaxis que Odoo 19 ya no acepta. Este script busca exactamente eso,
antes de subir el módulo a un servidor.

Qué NO hace: no reemplaza instalar. No ve errores de datos (una constraint que
choca con registros reales), ni de SQL, ni de lógica de negocio. Es un filtro
previo, no una garantía.

Termina con código 1 si encontró errores, 0 si no. Los AVISOS no son errores:
en su mayoría son campos nativos de Odoo que este script no puede conocer sin
tener Odoo delante.
"""
import ast
import csv
import io
import os
import pathlib
import py_compile
import re
import sys
import tempfile
from xml.etree import ElementTree as ET

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)

errores, avisos = [], []


def err(mensaje):
    errores.append(mensaje)


def avi(mensaje):
    avisos.append(mensaje)


def leer(ruta):
    return io.open(ruta, encoding='utf-8').read()


def _blanquear(match):
    """Reemplaza el texto por espacios, conservando los saltos de línea: así lo que se
    anula deja de analizarse pero los números de línea siguen siendo los reales."""
    return re.sub(r'[^\n]', ' ', match.group(0))


def sin_comentarios(ruta):
    """Contenido del archivo con los comentarios y los textos literales anulados.

    Hace falta para buscar nombres y sintaxis retirados: un comentario que EXPLICA
    que algo ya no se usa («antes esto era attrs=») no es un uso, y marcarlo como
    error entrena a ignorar al verificador. Se anulan los comentarios XML completos
    (incluidos los de varias líneas), los comentarios de Python y los docstrings.
    """
    texto = leer(ruta)
    if str(ruta).endswith(('.xml', '.html')):
        return re.sub(r'<!--.*?-->', _blanquear, texto, flags=re.S)
    if str(ruta).endswith('.py'):
        texto = re.sub(r'("""|\'\'\').*?\1', _blanquear, texto, flags=re.S)
        return re.sub(r'(?m)#[^\n]*', _blanquear, texto)
    return texto


ARCHIVOS_PY = [f for f in sorted(pathlib.Path('.').rglob('*.py'))
               if '__pycache__' not in str(f) and f.name != 'verificar.py']
ARCHIVOS_XML = [f for f in sorted(pathlib.Path('.').rglob('*.xml'))
                if '__pycache__' not in str(f)]
ARCHIVOS_CSV = sorted(pathlib.Path('.').rglob('*.csv'))

# Nombres retirados que no pueden volver a aparecer. Dos clases:
#   GLOBALES: no deben existir en el módulo bajo ninguna forma.
#   POR_MODELO: siguen siendo válidos en OTRO modelo, así que se controlan solo
#   dentro de las vistas del modelo del que se retiraron.
RETIRADOS_GLOBALES = [
    'l10n_py_',            # prefijo viejo: todo lo de local_py lleva local_py_
    'res.district', 'res_district', 'ResDistrict',
    'code_alpha3',         # ahora local_py_code_alpha3
    'omitir_validacion',   # ahora local_py_omitir_validacion
]
RETIRADOS_POR_MODELO = {
    'res.company': ['city_id'],           # sigue siendo nativo en res.partner
    'res.city': ['code', 'district_id'],  # 'code' sigue válido en modelos propios
}

# Sintaxis que Odoo 19 ya no acepta.
SINTAXIS_RETIRADA = [
    ('<tree', 'en Odoo 19 las vistas de lista son <list>'),
    ('attrs=', 'en Odoo 19 se reemplaza por invisible=/readonly=/required= con expresión'),
    ('states=', 'en Odoo 19 se reemplaza por una expresión sobre el campo de estado'),
    ('_sql_constraints', 'en Odoo 19 se declara con models.Constraint'),
]
TARGETS_VALIDOS = {'current', 'fullscreen', 'new', 'main'}
VIEW_MODES_VALIDOS = {'list', 'form', 'kanban', 'calendar', 'pivot', 'graph',
                      'activity', 'gantt', 'map', 'cohort', 'hierarchy', 'qweb'}
TIPOS_DIARIO = {'sale', 'purchase', 'cash', 'bank', 'credit', 'general'}
TIPOS_CUENTA = {
    'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
    'asset_prepayments', 'asset_fixed', 'liability_payable', 'liability_credit_card',
    'liability_current', 'liability_non_current', 'equity', 'equity_unaffected',
    'income', 'income_other', 'expense', 'expense_other', 'expense_depreciation',
    'expense_direct_cost', 'off_balance',
}


# ---------------------------------------------------------------------------
# 1. Python compila
# ---------------------------------------------------------------------------
def check_python():
    destino = os.path.join(tempfile.gettempdir(), '_local_py_verificar.pyc')
    for f in ARCHIVOS_PY:
        try:
            py_compile.compile(str(f), cfile=destino, doraise=True)
        except Exception as error:
            err("[python] %s: %s" % (f, error))
    if os.path.exists(destino):
        os.remove(destino)


# ---------------------------------------------------------------------------
# 2. XML bien formado
# ---------------------------------------------------------------------------
def check_xml():
    for f in ARCHIVOS_XML + [pathlib.Path('static/description/index.html')]:
        if not f.exists():
            continue
        try:
            ET.parse(str(f))
        except Exception as error:
            err("[xml] %s: %s" % (f, error))


# ---------------------------------------------------------------------------
# 3. Campos y métodos por modelo, leídos del AST
# ---------------------------------------------------------------------------
campos, metodos, modelos_propios, modelos_abstractos, decl = {}, {}, set(), set(), {}


def recolectar_modelos():
    for f in ARCHIVOS_PY:
        try:
            arbol = ast.parse(leer(f))
        except SyntaxError:
            continue
        for cls in [n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)]:
            modelo, propio = None, False
            for st in cls.body:
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)
                        and st.targets[0].id in ('_name', '_inherit')
                        and isinstance(st.value, ast.Constant)):
                    modelo = st.value.value
                    propio = propio or st.targets[0].id == '_name'
            if not modelo:
                continue
            if propio:
                modelos_propios.add(modelo)
                # Un AbstractModel no tiene tabla propia, así que no lleva ACL.
                if any(getattr(b, 'attr', '') == 'AbstractModel' for b in cls.bases):
                    modelos_abstractos.add(modelo)
            campos.setdefault(modelo, set())
            metodos.setdefault(modelo, set())
            for st in cls.body:
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)
                        and isinstance(st.value, ast.Call)
                        and isinstance(st.value.func, ast.Attribute)
                        and getattr(st.value.func.value, 'id', '') == 'fields'):
                    nombre = st.targets[0].id
                    campos[modelo].add(nombre)
                    decl[(modelo, nombre)] = {k.arg: k.value for k in st.value.keywords if k.arg}
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    metodos[modelo].add(st.name)
                    for d in st.decorator_list:
                        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                                and d.func.attr in ('depends', 'constrains', 'onchange')):
                            for a in d.args:
                                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                    decl.setdefault(('@' + d.func.attr, modelo), []).append(
                                        (a.value, st.name))


# ---------------------------------------------------------------------------
# 4. compute / inverse / search / related apuntan a algo que existe
# ---------------------------------------------------------------------------
def check_atributos_de_campo():
    for clave, kw in list(decl.items()):
        if not isinstance(kw, dict):
            continue
        modelo, campo = clave
        for atributo in ('compute', 'inverse', 'search'):
            valor = kw.get(atributo)
            if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                if valor.value not in metodos.get(modelo, set()):
                    err("[%s] %s.%s -> el método '%s' no existe"
                        % (atributo, modelo, campo, valor.value))
        valor = kw.get('related')
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            primero = valor.value.split('.')[0]
            if primero not in campos.get(modelo, set()):
                avi("[related] %s.%s -> '%s': el primer salto '%s' no se declara acá "
                    "(puede ser nativo)" % (modelo, campo, valor.value, primero))


# ---------------------------------------------------------------------------
# 5. Argumentos de @api.depends / constrains / onchange
# ---------------------------------------------------------------------------
def check_decoradores():
    for clave, lista in list(decl.items()):
        if not (isinstance(clave, tuple) and str(clave[0]).startswith('@')):
            continue
        _, modelo = clave
        for ruta, metodo in lista:
            primero = ruta.split('.')[0]
            if primero not in campos.get(modelo, set()):
                avi("[%s] %s.%s('%s'): '%s' no se declara acá (puede ser nativo)"
                    % (clave[0], modelo, metodo, ruta, primero))


# ---------------------------------------------------------------------------
# 6. ACL: todo model_id:id tiene que resolver a un modelo propio
# ---------------------------------------------------------------------------
def check_acl():
    ruta = pathlib.Path('security/ir.model.access.csv')
    if not ruta.exists():
        err("[acl] falta security/ir.model.access.csv")
        return
    declarados = {'model_' + m.replace('.', '_') for m in modelos_propios}
    vistos = set()
    with io.open(ruta, encoding='utf-8') as fh:
        for fila in csv.DictReader(fh):
            if not fila.get('id'):
                continue
            if fila['id'] in vistos:
                err("[acl] la fila '%s' está repetida" % fila['id'])
            vistos.add(fila['id'])
            # local_py solo declara ACLs sobre sus PROPIOS modelos: un model_id:id
            # que no resuelva a uno de ellos aborta la instalación.
            if fila['model_id:id'] not in declarados:
                err("[acl] %s -> model_id:id '%s' no corresponde a ningún modelo "
                    "declarado por local_py" % (fila['id'], fila['model_id:id']))
    con_acl = {f['model_id:id'] for f in csv.DictReader(io.open(ruta, encoding='utf-8'))}
    for modelo in sorted(modelos_propios - modelos_abstractos):
        if 'model_' + modelo.replace('.', '_') not in con_acl:
            err("[acl] el modelo '%s' no tiene ninguna fila de permisos: ningún usuario "
                "va a poder usarlo" % modelo)


# ---------------------------------------------------------------------------
# 7. IDs XML: duplicados y referencias internas
# ---------------------------------------------------------------------------
ids = {}


def check_ids_xml():
    declarados = {'model_' + m.replace('.', '_') for m in modelos_propios}
    for f in ARCHIVOS_XML:
        for m in re.finditer(r'<(?:record|menuitem|template|report)[^>]*\bid="([^"]+)"', leer(f)):
            if m.group(1) in ids:
                err("[xmlid] '%s' duplicado (%s y %s)" % (m.group(1), ids[m.group(1)], f))
            ids[m.group(1)] = str(f)
    for f in ARCHIVOS_XML:
        texto = leer(f)
        for atributo in ('ref', 'parent', 'action', 'inherit_id'):
            for m in re.finditer(r'\b%s="([^"]+)"' % atributo, texto):
                valor = m.group(1)
                if valor.startswith('model_'):
                    if valor not in declarados:
                        err("[ref] %s: %s=\"%s\" no corresponde a ningún modelo "
                            "declarado por local_py" % (f, atributo, valor))
                    continue
                if valor.startswith('local_py.'):
                    if valor.split('.', 1)[1] not in ids:
                        err("[ref] %s: %s=\"%s\" no existe en local_py" % (f, atributo, valor))
                elif '.' not in valor and valor not in ids:
                    err("[ref] %s: %s=\"%s\" no existe en local_py" % (f, atributo, valor))


def _en_sublista(nodo, padres):
    """True si el <field> está dentro de un <list>/<form>/<kanban> embebido en otro
    <field>: ahí el modelo es el de la relación, no el de la vista."""
    n = padres.get(nodo)
    while n is not None:
        if n.tag in ('list', 'form', 'kanban') and padres.get(n) is not None \
                and padres[n].tag == 'field':
            return True
        n = padres.get(n)
    return False


# ---------------------------------------------------------------------------
# 8. Campos usados en vistas
# ---------------------------------------------------------------------------
def check_campos_en_vistas():
    for f in ARCHIVOS_XML:
        try:
            arbol = ET.parse(str(f))
        except Exception:
            continue
        for rec in arbol.iter('record'):
            if rec.get('model') != 'ir.ui.view':
                continue
            nodo_modelo = rec.find("field[@name='model']")
            arch = rec.find("field[@name='arch']")
            if nodo_modelo is None or arch is None:
                continue
            modelo = (nodo_modelo.text or '').strip()
            conocidos = campos.get(modelo, set())
            padres = {h: n for n in arch.iter() for h in n}
            if conocidos:
                for campo in arch.iter('field'):
                    nombre = campo.get('name')
                    if not nombre or not nombre.startswith('local_py_'):
                        continue
                    if _en_sublista(campo, padres):
                        continue
                    if nombre not in conocidos:
                        err("[vista] %s [%s]: el campo '%s' no existe"
                            % (f.name, modelo, nombre))
            prohibidos = RETIRADOS_POR_MODELO.get(modelo)
            if prohibidos:
                for campo in arch.iter('field'):
                    nombre = campo.get('name')
                    if nombre in prohibidos and not _en_sublista(campo, padres):
                        err("[retirado] %s [%s]: el campo '%s' fue renombrado a "
                            "'local_py_%s'" % (f.name, modelo, nombre, nombre))


# ---------------------------------------------------------------------------
# 9. env.ref('local_py.X') y ref() dentro de eval=
# ---------------------------------------------------------------------------
def check_referencias_python():
    for f in ARCHIVOS_PY:
        for m in re.finditer(r"""env\.ref\(\s*['"]local_py\.([A-Za-z0-9_.]+)['"]""", leer(f)):
            if m.group(1) not in ids:
                err("[env.ref] %s: 'local_py.%s' no existe en los datos del módulo"
                    % (f, m.group(1)))
    for f in ARCHIVOS_XML:
        for m in re.finditer(r"""ref\(\s*['"]([A-Za-z0-9_.]+)['"]\s*\)""", leer(f)):
            valor = m.group(1)
            objetivo = (valor.split('.', 1)[1] if valor.startswith('local_py.')
                        else (valor if '.' not in valor else None))
            if objetivo is not None and objetivo not in ids:
                err("[eval ref] %s: '%s' no existe en local_py" % (f, valor))


# ---------------------------------------------------------------------------
# 10. Nombres retirados
# ---------------------------------------------------------------------------
def check_nombres_retirados():
    for f in ARCHIVOS_PY + ARCHIVOS_XML + ARCHIVOS_CSV:
        for i, linea in enumerate(sin_comentarios(f).splitlines(), 1):
            for token in RETIRADOS_GLOBALES:
                if token not in linea:
                    continue
                if token == 'omitir_validacion' and 'local_py_omitir_validacion' in linea:
                    continue
                if token == 'code_alpha3' and 'local_py_code_alpha3' in linea:
                    continue
                err("[retirado] %s:%d usa el nombre retirado '%s'" % (f, i, token))


# ---------------------------------------------------------------------------
# 11. Sintaxis incompatible con Odoo 19
# ---------------------------------------------------------------------------
def check_odoo19():
    for f in ARCHIVOS_PY + ARCHIVOS_XML:
        for i, linea in enumerate(sin_comentarios(f).splitlines(), 1):
            for token, motivo in SINTAXIS_RETIRADA:
                if token in linea:
                    err("[odoo19] %s:%d usa '%s' — %s" % (f, i, token, motivo))
    for f in ARCHIVOS_XML:
        try:
            arbol = ET.parse(str(f))
        except Exception:
            continue
        for rec in arbol.iter('record'):
            if rec.get('model') != 'ir.actions.act_window':
                continue
            for campo in rec.findall('field'):
                valor = (campo.text or '').strip()
                if campo.get('name') == 'target' and valor not in TARGETS_VALIDOS:
                    err("[odoo19] %s [%s]: target=\"%s\" no es válido (use %s)"
                        % (f.name, rec.get('id'), valor, ', '.join(sorted(TARGETS_VALIDOS))))
                if campo.get('name') == 'view_mode':
                    for modo in valor.split(','):
                        if modo.strip() and modo.strip() not in VIEW_MODES_VALIDOS:
                            err("[odoo19] %s [%s]: view_mode '%s' no es válido"
                                % (f.name, rec.get('id'), modo.strip()))


# ---------------------------------------------------------------------------
# 12. Manifest e imports
# ---------------------------------------------------------------------------
def check_manifest():
    manifest = ast.literal_eval(leer('__manifest__.py'))
    for dato in manifest['data']:
        if not pathlib.Path(dato).exists():
            err("[manifest] el archivo '%s' está en el manifest y no existe" % dato)
    en_disco = []
    for carpeta in ('views', 'data', 'security', 'report', 'wizard'):
        if os.path.isdir(carpeta):
            en_disco += [carpeta + '/' + n for n in os.listdir(carpeta)
                         if n.endswith(('.xml', '.csv'))]
    for suelto in sorted(set(en_disco) - set(manifest['data'])):
        err("[manifest] '%s' existe y no está en el manifest: no se va a cargar" % suelto)
    version = str(manifest.get('version', ''))
    if not re.match(r'^\d{4}\.\d+\.\d{3}$', version):
        avi("[manifest] la versión '%s' no sigue el formato AAAA.19.NNN" % version)
    return manifest


def check_imports():
    for carpeta in ('models', 'wizard', 'report', 'tests'):
        init = os.path.join(carpeta, '__init__.py')
        if not os.path.exists(init):
            continue
        importados = re.findall(r'^from \. import (\w+)', leer(init), re.M)
        for nombre in importados:
            if not os.path.exists(os.path.join(carpeta, nombre + '.py')):
                err("[import] %s importa '%s' y ese archivo no existe" % (init, nombre))
        archivos = {n[:-3] for n in os.listdir(carpeta)
                    if n.endswith('.py') and n != '__init__.py'}
        for suelto in sorted(archivos - set(importados)):
            err("[import] %s/%s.py existe y %s no lo importa: no se va a cargar"
                % (carpeta, suelto, init))


# ---------------------------------------------------------------------------
# 13. Cabeceras de los CSV de datos
# ---------------------------------------------------------------------------
def check_csv_de_datos():
    for ruta, modelo in (('data/res.city.csv', 'res.city'),
                         ('data/local_py.district.csv', 'local_py.district')):
        p = pathlib.Path(ruta)
        if not p.exists():
            err("[csv] falta %s" % ruta)
            continue
        for columna in leer(p).split('\n')[0].split(','):
            base = columna.split('/')[0].strip('"')
            if base in ('id',) or not base:
                continue
            if base.startswith('local_py_') and base not in campos.get(modelo, set()):
                err("[csv] %s: la columna '%s' no es un campo de %s" % (ruta, base, modelo))


# ---------------------------------------------------------------------------
# 14. report.local_py.* tienen su plantilla QWeb
# ---------------------------------------------------------------------------
def check_reportes():
    plantillas = set()
    for f in ARCHIVOS_XML:
        for m in re.finditer(r'<template id="([^"]+)"', leer(f)):
            plantillas.add(m.group(1))
    for modelo in sorted(m for m in modelos_propios if m.startswith('report.local_py.')):
        nombre = modelo.split('report.local_py.', 1)[1]
        if nombre not in plantillas:
            avi("[reporte] %s: no encontré la plantilla '%s'" % (modelo, nombre))


# ---------------------------------------------------------------------------
# 15. Constraints de res.partner: exención durante la instalación
# ---------------------------------------------------------------------------
def check_exencion_instalacion():
    """local_py escribe sobre contactos PREEXISTENTES en el post_init_hook (backfill
    del Tipo de Identificación Fiscal). Si alguna constraint de res.partner no se
    exime mientras el registro no está listo, esos datos previos incompletos abortan
    la instalación del módulo."""
    ruta = 'models/res_partner.py'
    if not os.path.exists(ruta):
        return
    patron = r"    def (_check_\w+)\(self\):\n(        \"\"\".*?\"\"\"\n)?(.*?)(?=\n    @|\n    def |\Z)"
    for m in re.finditer(patron, leer(ruta), re.S):
        nombre, cuerpo = m.group(1), m.group(3)
        if '_local_py_validaciones_exentas' not in cuerpo:
            err("[instalación] res.partner.%s no se exime mientras el registro no está "
                "listo: puede abortar la instalación sobre datos preexistentes" % nombre)


# ---------------------------------------------------------------------------
# 16. Plantilla Excel de configuración
# ---------------------------------------------------------------------------
def check_plantilla():
    """Un typo en los nombres de campo de la plantilla no se vería hasta APLICARLA,
    con la configuración a medio escribir. Se controlan acá, contra los modelos."""
    ruta = 'models/local_py_plantilla_excel.py'
    if not os.path.exists(ruta):
        return
    # El archivo se carga como módulo suelto: no importa nada de Odoo justamente para
    # poder probarlo sin base de datos, así que acá también se puede leer tal cual.
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location('_local_py_plantilla_excel', ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    except Exception as error:
        avi("[plantilla] no pude cargar %s para controlar sus tablas (%s: %s)"
            % (ruta, type(error).__name__, error))
        return
    tablas = {nombre: getattr(modulo, nombre, None)
              for nombre in ('CUENTAS', 'DIARIOS', 'PARAMETROS')}
    for nombre, tabla in tablas.items():
        if not tabla:
            err("[plantilla] no encontré la tabla %s en %s" % (nombre, ruta))

    config = campos.get('local_py.configuracion_localizacion', set())
    if not config:
        err("[plantilla] no pude leer los campos de local_py.configuracion_localizacion")
        return
    for fila in tablas.get('CUENTAS') or []:
        if fila[5] not in config:
            err("[plantilla] CUENTAS['%s'] apunta al campo '%s', que no existe en "
                "Configuraciones Localización Py" % (fila[0], fila[5]))
    for fila in tablas.get('DIARIOS') or []:
        if fila[6] not in config:
            err("[plantilla] DIARIOS['%s'] apunta al campo '%s', que no existe en "
                "Configuraciones Localización Py" % (fila[0], fila[6]))
        if fila[2] not in TIPOS_DIARIO:
            err("[plantilla] DIARIOS['%s'] declara el tipo de diario '%s', que no existe"
                % (fila[0], fila[2]))
    for fila in tablas.get('PARAMETROS') or []:
        if fila[4] is None:
            if fila[0] != 'imputacion_tributaria':
                err("[plantilla] PARAMETROS['%s'] no declara campo y no es el caso "
                    "especial previsto" % fila[0])
            continue
        if fila[4] not in config:
            err("[plantilla] PARAMETROS['%s'] apunta al campo '%s', que no existe en "
                "Configuraciones Localización Py" % (fila[0], fila[4]))

    # Los campos que escribe cada _aplicar_*, contra los modelos de destino.
    aplicar = leer('models/local_py_plantilla.py') if os.path.exists(
        'models/local_py_plantilla.py') else ''
    por_modelo = {
        'local_py.recibo.serie': ['name', 'company_id', 'user_id', 'numero_inicial',
                                  'numero_final'],
        'local_py.rubrica': ['company_id', 'idrubrica', 'fecha', 'uso', 'cantidad_hojas',
                             'nro_entrada', 'fecha_entrada', 'numero_inicial', 'numero_final'],
        'local_py.chequera': ['name', 'company_id', 'bank_id', 'cuenta_bancaria_id',
                              'currency_id', 'tipo', 'numero_inicial', 'numero_final',
                              'diario_id'],
        'local_py.no_retencion': ['config_id', 'partner_id', 'tipo_retencion',
                                  'nro_resolucion', 'fecha_desde', 'fecha_hasta'],
        'local_py.concepto_renta_no_residente': ['porcentaje_imputacion', 'porcentaje',
                                                 'porcentaje_absorcion'],
    }
    for modelo, esperados in por_modelo.items():
        reales = campos.get(modelo, set())
        if not reales:
            continue
        for campo in esperados:
            if campo not in reales:
                err("[plantilla] escribe '%s' en %s y ese campo no existe"
                    % (campo, modelo))
            # Se busca como CLAVE escrita ("'campo':"), no en cualquier parte: si solo
            # se buscara el nombre, un {'nroentrada': r['nro_entrada']} pasaría igual.
            elif aplicar and "'%s':" % campo not in aplicar:
                avi("[plantilla] %s.%s no se escribe al aplicar la plantilla"
                    % (modelo, campo))

    # Todos los pasos de aplicación declarados se llaman, y al revés.
    if aplicar:
        llamados = set(re.findall(r'hechos \+= self\.(_aplicar_[a-z_]+)\(', aplicar))
        declarados = set(re.findall(r'def (_aplicar_[a-z_]+)\(', aplicar))
        for sobrante in sorted(declarados - llamados):
            err("[plantilla] el paso '%s' está declarado y nunca se llama" % sobrante)
        for faltante in sorted(llamados - declarados):
            err("[plantilla] se llama al paso '%s' y no está declarado" % faltante)


# ---------------------------------------------------------------------------
# 17. Tipos de cuenta de Libro Inventario y Estado de Resultados
# ---------------------------------------------------------------------------
def check_tipos_de_cuenta():
    ruta = 'models/local_py_libro_report.py'
    if not os.path.exists(ruta):
        return
    fuente = leer(ruta)
    grupos = {}
    for nombre in ('TIPOS_BALANCE', 'TIPOS_INGRESO', 'TIPOS_RESULTADO'):
        m = re.search(nombre + r'\s*=\s*(?:TIPOS_INGRESO \+ )?\(([^)]*)\)', fuente, re.S)
        grupos[nombre] = set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else set()
    grupos['TIPOS_RESULTADO'] |= grupos['TIPOS_INGRESO']
    for nombre, valores in grupos.items():
        if not valores:
            err("[reportes] no encontré %s en %s" % (nombre, ruta))
            continue
        for tipo in sorted(valores - TIPOS_CUENTA):
            err("[reportes] %s declara el tipo de cuenta '%s', que no existe" % (nombre, tipo))
    solapados = grupos['TIPOS_BALANCE'] & grupos['TIPOS_RESULTADO']
    if solapados:
        err("[reportes] estos tipos entran en Libro Inventario Y en Estado de "
            "Resultados a la vez: %s" % ', '.join(sorted(solapados)))
    faltantes = TIPOS_CUENTA - {'off_balance'} - grupos['TIPOS_BALANCE'] - grupos['TIPOS_RESULTADO']
    if faltantes:
        avi("[reportes] estos tipos de cuenta no entran en ningún reporte: %s"
            % ', '.join(sorted(faltantes)))
    if "split('.')[0]" in fuente:
        err("[reportes] los reportes volvieron a segmentar el código de cuenta por "
            "puntos: con un plan de numeración libre eso no funciona")
    if "count('.')" in fuente:
        err("[reportes] el nivel de sangría volvió a derivarse del código de cuenta: "
            "tiene que salir de la jerarquía de Grupos (_nivel_grupo)")


# ---------------------------------------------------------------------------
def main():
    check_python()
    check_xml()
    recolectar_modelos()
    check_atributos_de_campo()
    check_decoradores()
    check_acl()
    check_ids_xml()
    check_campos_en_vistas()
    check_referencias_python()
    check_nombres_retirados()
    check_odoo19()
    manifest = check_manifest()
    check_imports()
    check_csv_de_datos()
    check_reportes()
    check_exencion_instalacion()
    check_plantilla()
    check_tipos_de_cuenta()

    todos = '-v' in sys.argv or '--avisos' in sys.argv
    print("local_py %s" % manifest.get('version', '?'))
    print("Modelos propios: %d   |   modelos con campos: %d   |   IDs XML: %d"
          % (len(modelos_propios), len(campos), len(ids)))
    print("\nERRORES: %d" % len(errores))
    for e in errores:
        print("  " + e)
    print("\nAVISOS: %d%s" % (len(avisos), "" if todos else "  (use -v para verlos todos)"))
    for a in (avisos if todos else avisos[:25]):
        print("  " + a)
    if not todos and len(avisos) > 25:
        print("  ... y %d más" % (len(avisos) - 25))
    print("\n%s" % ("HAY ERRORES: no subir el módulo hasta corregirlos." if errores
                    else "Sin errores. Los avisos no impiden instalar."))
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main())
