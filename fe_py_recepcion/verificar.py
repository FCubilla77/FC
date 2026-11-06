#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificaciones estáticas de fe_py_recepcion (no necesita Odoo).

Uso, desde la carpeta del módulo:  python3 verificar.py
"""
import glob
import os
import py_compile
import re
import subprocess
import sys

from lxml import etree

errores = []
RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
BASE_ODOO = {'display_name', 'id', 'create_date', 'write_date', 'create_uid', 'write_uid'}


def leer(path):
    return open(path, encoding='utf-8').read()


def check_python():
    for path in glob.glob('**/*.py', recursive=True):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as error:
            errores.append(f"[python] {path}: {error.msg}")


def check_imports():
    for init in glob.glob('**/__init__.py', recursive=True):
        carpeta = os.path.dirname(init)
        if carpeta.startswith('tests'):
            continue
        importados = set(re.findall(r'^from \. import (\w+)', leer(init), re.M))
        for modulo in importados:
            if not os.path.exists(os.path.join(carpeta, modulo + '.py')) and \
               not os.path.isdir(os.path.join(carpeta, modulo)):
                errores.append(f"[imports] {init}: '{modulo}' no existe")
        for archivo in glob.glob(os.path.join(carpeta, '*.py')):
            nombre = os.path.basename(archivo)[:-3]
            if nombre not in ('__init__', '__manifest__', 'hooks', 'verificar') and nombre not in importados \
                    and carpeta in ('models', 'wizard'):
                errores.append(f"[imports] {archivo} no se importa en {init}")


def check_xml():
    for path in glob.glob('**/*.xml', recursive=True):
        if path.startswith('tests'):
            continue
        try:
            etree.parse(path)
        except etree.XMLSyntaxError as error:
            errores.append(f"[xml] {path}: {error}")


def check_odoo19():
    prohibido = [(r'<tree[\s>]', 'usar <list>'), (r'\battrs\s*=', 'usar invisible=/readonly= con expresión'),
                 (r'\bstates\s*=\s*"', 'usar invisible= con state'), (r'_sql_constraints', 'usar models.Constraint'),
                 (r'<chatter>|<div class="oe_chatter"', 'usar <chatter/>')]
    for path in glob.glob('**/*.xml', recursive=True) + glob.glob('**/*.py', recursive=True):
        if path.startswith('tests') or path == 'verificar.py':
            continue
        src = leer(path)
        for patron, ayuda in prohibido:
            if re.search(patron, src):
                errores.append(f"[odoo19] {path}: {patron} -> {ayuda}")


def modelos_propios():
    """{modelo: set(campos)} resolviendo solo los campos declarados en cada clase."""
    campos = {}
    for path in glob.glob('models/*.py') + glob.glob('wizard/*.py'):
        src = leer(path)
        for cm in re.finditer(r"class \w+\([^)]*\):(.*?)(?=\nclass |\Z)", src, re.S):
            cuerpo = cm.group(1)
            m = re.search(r"^\s{4}_name\s*=\s*'([^']+)'", cuerpo, re.M)
            if not m:
                continue
            campos.setdefault(m.group(1), set()).update(
                re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", cuerpo, re.M))
    for modelo in campos:
        campos[modelo] |= BASE_ODOO
    return campos


def modelos_abstractos():
    """Modelos declarados con models.AbstractModel (no llevan permisos ni reglas)."""
    abstractos = set()
    for path in glob.glob('models/*.py'):
        for cm in re.finditer(r"class \w+\(([^)]*)\):(.*?)(?=\nclass |\Z)", leer(path), re.S):
            if 'AbstractModel' in cm.group(1):
                m = re.search(r"^\s{4}_name\s*=\s*'([^']+)'", cm.group(2), re.M)
                if m:
                    abstractos.add(m.group(1))
    return abstractos


def metodos_de(modelo):
    resultado = set()
    for path in glob.glob('models/*.py') + glob.glob('wizard/*.py'):
        src = leer(path)
        for cm in re.finditer(r"class \w+\([^)]*\):(.*?)(?=\nclass |\Z)", src, re.S):
            cuerpo = cm.group(1)
            m = re.search(r"^\s{4}_(?:name|inherit)\s*=\s*'([^']+)'", cuerpo, re.M)
            if m and m.group(1) == modelo:
                resultado |= set(re.findall(r'^\s{4}def (\w+)', cuerpo, re.M))
    return resultado


def check_vistas():
    propios = modelos_propios()
    for path in glob.glob('views/*.xml') + glob.glob('wizard/*.xml'):
        arbol = etree.parse(path)
        for vista in arbol.iter('record'):
            if vista.get('model') != 'ir.ui.view':
                continue
            modelo = (vista.xpath("field[@name='model']/text()") or [''])[0]
            if modelo not in propios:
                continue
            arch = vista.find("field[@name='arch']")
            for campo in arch.iter('field'):
                if campo is arch:
                    continue
                nombre = campo.get('name')
                # campo dentro de un sub-listado: se valida contra el modelo de la relación
                en_sublista = any(a.tag in ('list', 'form') and a.getparent() is not None
                                  and a.getparent().tag == 'field' for a in campo.iterancestors())
                if en_sublista:
                    continue
                if nombre not in propios[modelo]:
                    errores.append(f"[vista] {path} [{modelo}]: el campo '{nombre}' no existe")
            for boton in arch.iter('button'):
                nombre, tipo = boton.get('name'), boton.get('type')
                if tipo == 'object' and nombre not in metodos_de(modelo):
                    errores.append(f"[botones] {path}: el método '{nombre}' no existe en {modelo}")
        # sub-listados: líneas y cuotas
    sub = {('fe_py_recepcion.documento', 'line_ids'): 'fe_py_recepcion.documento.linea',
           ('fe_py_recepcion.documento', 'cuota_ids'): 'fe_py_recepcion.documento.cuota'}
    arbol = etree.parse('views/fe_py_recepcion_documento_views.xml')
    for campo in arbol.iter('field'):
        destino = sub.get(('fe_py_recepcion.documento', campo.get('name')))
        if destino:
            for hijo in campo.iter('field'):
                if hijo is not campo and hijo.get('name') not in propios[destino]:
                    errores.append(f"[vista] sublistado {campo.get('name')}: '{hijo.get('name')}' no existe en {destino}")
    # vista heredada de account.move: campos propios agregados
    for campo in etree.parse('views/account_move_views.xml').iter('field'):
        if campo.get('name', '').startswith('fe_py_') and campo.get('name') not in \
                re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", leer('models/account_move.py'), re.M):
            errores.append(f"[vista] account_move_views: '{campo.get('name')}' no existe")


def check_referencias_internas():
    propios = modelos_propios()
    for path in glob.glob('models/*.py'):
        src = leer(path)
        metodos = set(re.findall(r'^\s+def (\w+)', src, re.M))
        for c in re.findall(r"compute='(\w+)'", src):
            if c not in metodos:
                errores.append(f"[compute] {path}: '{c}' no está definido")
        for modelo, inverso in re.findall(r"One2many\(\s*'([\w.]+)',\s*'(\w+)'", src):
            if modelo in propios and inverso not in propios[modelo]:
                errores.append(f"[one2many] {path}: {modelo}.{inverso} no existe")
        for r in re.findall(r"related='(\w+)", src):
            pass


def check_permisos():
    definidos = set(modelos_propios()) - modelos_abstractos()
    csv = leer('security/ir.model.access.csv')
    con_permiso = {m.replace('_', '.') for m in re.findall(r'model_(fe_py_recepcion_[\w]+)', csv)}
    normal = lambda m: m.replace('.', '_')
    for m in definidos:
        if normal(m) not in {normal(x) for x in con_permiso}:
            errores.append(f"[permisos] '{m}' sin permisos")
    for m in re.findall(r'model_(fe_py_recepcion_[\w]+)', csv):
        if m not in {normal(x) for x in definidos}:
            errores.append(f"[permisos] model_{m} no corresponde a ningún modelo")
    for linea in csv.strip().splitlines()[1:]:
        if len(linea.split(',')) != 8:
            errores.append(f"[permisos] fila mal formada: {linea[:60]}")
    sec = leer('security/security.xml')
    for m in definidos:
        if m in ('fe_py_recepcion.documento', 'fe_py_recepcion.documento.linea',
                 'fe_py_recepcion.equivalencia') and 'model_' + normal(m) not in sec:
            errores.append(f"[reglas] '{m}' sin regla multicompañía")


def check_manifest():
    src = leer('__manifest__.py')
    manifest = eval(src)
    for f in manifest['data']:
        if not os.path.exists(f):
            errores.append(f"[manifest] no existe: {f}")
    for f in glob.glob('views/*.xml') + glob.glob('wizard/*.xml') + glob.glob('security/*.xml'):
        if f not in manifest['data']:
            errores.append(f"[manifest] no está listado: {f}")
    if not re.fullmatch(r'2026\.19\.\d{3}', manifest['version']):
        errores.append(f"[manifest] versión fuera de formato: {manifest['version']}")
    if manifest.get('license') != 'OPL-1':
        errores.append(f"[manifest] la licencia debe ser OPL-1: {manifest.get('license')}")
    if 'cryptography' not in manifest.get('external_dependencies', {}).get('python', []):
        errores.append("[manifest] falta cryptography en external_dependencies")
    for archivo in ('LICENSE',):
        if not os.path.exists(archivo):
            errores.append(f"[manifest] falta el archivo {archivo}")
    if manifest.get('post_init_hook') and 'post_init_hook' not in leer('__init__.py'):
        errores.append("[manifest] post_init_hook no se importa en __init__.py")
    if 'FE_Py' in manifest['depends'] or 'fe_py' in manifest['depends']:
        errores.append("[manifest] no debe depender de FE_Py")


def check_acciones_menus():
    xml_ids = set()
    for path in glob.glob('views/*.xml') + glob.glob('wizard/*.xml'):
        xml_ids |= set(re.findall(r'<(?:record|menuitem)[^>]*\bid="(\w+)"', leer(path)))
    for path in glob.glob('views/*.xml') + glob.glob('wizard/*.xml'):
        src = leer(path)
        for a in re.findall(r'action="(\w+)"', src) + re.findall(r'%\((\w+)\)d', src):
            if '.' not in a and a not in xml_ids:
                errores.append(f"[acciones] {path}: '{a}' no está definido")


def check_pruebas():
    for prueba in ('tests/test_xml_parser.py', 'tests/test_licencia_sin_odoo.py'):
        r = subprocess.run([sys.executable, '-I', prueba], capture_output=True, text=True)
        if r.returncode != 0:
            errores.append(f"[pruebas] {prueba} falló:\n" + r.stderr[-800:])


def check_ajustes():
    """Los campos de la vista de Ajustes deben existir en res_config_settings.py y sus
    related deben apuntar a un campo de res.company que exista."""
    ajustes = leer('models/res_config_settings.py')
    campos_ajustes = set(re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", ajustes, re.M))
    campos_company = set(re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", leer('models/res_company.py'), re.M))
    for campo in re.findall(r'<field name="(fe_py_\w+)"', leer('views/res_config_settings_views.xml')):
        if campo not in campos_ajustes:
            errores.append(f"[ajustes] la vista usa '{campo}', que no está en res_config_settings.py")
    for campo, destino in re.findall(r"^\s{4}(\w+)\s*=\s*fields\.\w+\(\s*related='company_id\.(\w+)'", ajustes, re.M):
        if destino not in campos_company:
            errores.append(f"[ajustes] {campo}: res.company no tiene '{destino}'")
    for destino in campos_company:
        if destino.startswith('fe_py_recepcion_licencia_') and destino not in ajustes:
            errores.append(f"[ajustes] falta exponer '{destino}' en Ajustes")


def check_sin_modelo_configuracion():
    """La configuración ya no es un modelo: nada debe referenciarlo."""
    for path in glob.glob('**/*.py', recursive=True) + glob.glob('**/*.xml', recursive=True) + \
            glob.glob('security/*.csv'):
        if path in ('verificar.py',) or path.startswith('migrations'):
            continue
        if re.search(r"fe_py_recepcion[._]configuracion", leer(path)):
            errores.append(f"[config] {path} todavía referencia el modelo configuracion")


def check_migracion():
    carpetas = glob.glob('migrations/*')
    for c in carpetas:
        nombre = os.path.basename(c)
        if not nombre.startswith('19.0.'):
            errores.append(f"[migracion] '{nombre}' debe empezar con 19.0. (si no, Odoo no la ejecuta)")
        if not (os.path.exists(os.path.join(c, 'pre-migration.py'))
                or os.path.exists(os.path.join(c, 'post-migration.py'))):
            errores.append(f"[migracion] {c} sin pre-migration.py ni post-migration.py")


if __name__ == '__main__':
    pruebas = (check_python, check_imports, check_xml, check_odoo19, check_vistas,
               check_referencias_internas, check_permisos, check_manifest, check_acciones_menus,
               check_ajustes, check_sin_modelo_configuracion, check_migracion, check_pruebas)
    for f in pruebas:
        f()
    if errores:
        print("PROBLEMAS ENCONTRADOS:\n")
        print('\n'.join('  ' + e for e in errores))
        sys.exit(1)
    print(f"OK: las {len(pruebas)} verificaciones pasaron sin errores")
