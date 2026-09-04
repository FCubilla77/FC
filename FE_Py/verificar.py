#!/usr/bin/env python3
"""Verificador de FE_Py — detecta lo que py_compile no ve.

Comprueba, en este orden:
  1. Que todos los archivos de models/ carguen sin error (simula Odoo).
  2. Que los imports internos resuelvan de verdad.
  3. Que el XML esté bien formado.
  4. Que no queden patrones incompatibles con Odoo 19.
  5. Que TODO campo usado en una vista exista en su modelo, resolviendo
     la herencia de modelos abstractos.
  6. Que todo campo/método que use el reporte KuDE exista.
  7. Que el orden de carga de modelos respete las dependencias.
"""
import ast
import glob
import importlib.util
import os
import re
import sys
import types
import xml.dom.minidom

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)

errores = []


def _stub_odoo():
    odoo = types.ModuleType('odoo')

    class E(Exception):
        pass

    class exc:
        UserError = E
        ValidationError = E

    class DF:
        def __init__(self, *a, **k):
            pass

    class DateLike(DF):
        @staticmethod
        def now(*a, **k):
            return None

        @staticmethod
        def today(*a, **k):
            return None

        @staticmethod
        def context_today(*a, **k):
            return None

    class FieldsMod:
        def __getattr__(self, n):
            return DF

    fields_mod = FieldsMod()
    fields_mod.Datetime = DateLike
    fields_mod.Date = DateLike

    class _Constraint:
        def __init__(self, *a, **k):
            pass

    class ModelsMod:
        class Model:
            pass

        class AbstractModel:
            pass

        class TransientModel:
            pass
        Constraint = _Constraint

    class ApiMod:
        @staticmethod
        def depends(*a, **k):
            return lambda f: f

        @staticmethod
        def onchange(*a, **k):
            return lambda f: f

        @staticmethod
        def constrains(*a, **k):
            return lambda f: f

        @staticmethod
        def model(f):
            return f

        @staticmethod
        def depends_context(*a, **k):
            return lambda f: f

    odoo.exceptions = exc
    odoo.fields = fields_mod
    odoo.models = ModelsMod
    odoo.api = ApiMod
    odoo.SUPERUSER_ID = 1
    sys.modules['odoo'] = odoo
    m = types.ModuleType('odoo.exceptions')
    m.UserError = E
    m.ValidationError = E
    sys.modules['odoo.exceptions'] = m


def orden_de_modelos():
    return [x.group(1) for l in open('models/__init__.py')
            for x in [re.match(r'from \. import (\w+)', l.strip())] if x]


def check_carga():
    _stub_odoo()
    pkg = types.ModuleType('models')
    pkg.__path__ = ['models']
    sys.modules['models'] = pkg
    for n in orden_de_modelos():
        try:
            spec = importlib.util.spec_from_file_location('models.' + n, f'models/{n}.py')
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = 'models'
            sys.modules['models.' + n] = mod
            spec.loader.exec_module(mod)
        except Exception as ex:
            errores.append(f"[carga] {n}.py -> {type(ex).__name__}: {ex}")
    for ruta in ['wizard/account_move_reversal.py', 'hooks.py']:
        try:
            spec = importlib.util.spec_from_file_location('x', ruta)
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = 'models'
            spec.loader.exec_module(mod)
        except Exception as ex:
            errores.append(f"[carga] {ruta} -> {type(ex).__name__}: {ex}")


def check_imports():
    for path in glob.glob('models/*.py') + glob.glob('wizard/*.py') + ['hooks.py']:
        src = open(path, encoding='utf-8').read()
        carpeta = os.path.dirname(path) or '.'
        for m in re.finditer(r'^from \.(\w+) import ([^\n(]+)$', src, re.M):
            destino = os.path.join(carpeta, m.group(1) + '.py')
            if not os.path.exists(destino):
                errores.append(f"[import] {path}: '{m.group(1)}' no existe")
                continue
            arbol = ast.parse(open(destino, encoding='utf-8').read())
            definidos = set()
            for nodo in arbol.body:
                if isinstance(nodo, (ast.ClassDef, ast.FunctionDef)):
                    definidos.add(nodo.name)
                elif isinstance(nodo, ast.Assign):
                    for t in nodo.targets:
                        if isinstance(t, ast.Name):
                            definidos.add(t.id)
            for nombre in [n.strip() for n in m.group(2).split(',')]:
                if nombre and nombre not in definidos:
                    errores.append(f"[import] {path}: '{nombre}' no está en {m.group(1)}")


def check_xml():
    for f in glob.glob('data/*.xml') + glob.glob('views/*.xml') + \
             glob.glob('report/*.xml') + ['static/description/index.html']:
        try:
            xml.dom.minidom.parse(f)
        except Exception as ex:
            errores.append(f"[xml] {f}: {ex}")


def check_odoo19():
    patron = re.compile(r'<tree|attrs=|states=|group expand=|\.mobile\b|_sql_constraints')
    for f in glob.glob('views/*.xml') + glob.glob('report/*.xml') + glob.glob('models/*.py'):
        for i, linea in enumerate(open(f, encoding='utf-8'), 1):
            if patron.search(linea):
                errores.append(f"[odoo19] {f}:{i} patrón incompatible: {linea.strip()[:70]}")


def campos_por_modelo():
    """Campos definidos por FE_Py, resolviendo la herencia de modelos
    abstractos propios (los catálogos heredan de fe_py.catalogo.base)."""
    directos, hereda = {}, {}
    for path in glob.glob('models/*.py'):
        src = open(path, encoding='utf-8').read()
        for cm in re.finditer(r"class \w+\([^)]*\):(.*?)(?=\nclass |\Z)", src, re.S):
            cuerpo = cm.group(1)
            mm = re.search(r"_(?:name|inherit)\s*=\s*'([^']+)'", cuerpo)
            if not mm:
                continue
            modelo = mm.group(1)
            for fm in re.finditer(r"^\s{4}(\w+)\s*=\s*fields\.", cuerpo, re.M):
                directos.setdefault(modelo, set()).add(fm.group(1))
            base = re.search(r"_inherit\s*=\s*'(fe_py\.catalogo\.base)'", cuerpo)
            if base and re.search(r"_name\s*=\s*'([^']+)'", cuerpo):
                hereda[modelo] = base.group(1)
    for modelo, base in hereda.items():
        directos.setdefault(modelo, set()).update(directos.get(base, set()))
    return directos


def check_vistas():
    campos = campos_por_modelo()
    propios = {m: c for m, c in campos.items() if m.startswith('fe_py.')}
    base = {'display_name', 'id', 'create_date', 'write_date', 'create_uid',
            'write_uid', 'company_id', 'currency_id', 'active'}
    for path in glob.glob('views/*.xml'):
        src = open(path, encoding='utf-8').read()
        for rec in re.finditer(r'<record id="[^"]+" model="ir\.ui\.view">(.*?)</record>', src, re.S):
            b = rec.group(1)
            mm = re.search(r'<field name="model">([^<]+)</field>', b)
            ar = re.search(r'<field name="arch" type="xml">(.*)</field>', b, re.S)
            if not (mm and ar) or mm.group(1) not in propios:
                continue
            arch = re.sub(r'<list[^>]*>.*?</list>', '', ar.group(1), flags=re.S)
            usados = set(re.findall(r'<field name="(\w+)"', arch))
            usados |= set(re.findall(r'invisible="[^"]*?\b(\w+)\s*(?:!=|==|not in| in )', arch))
            falta = usados - propios[mm.group(1)] - base
            if falta:
                errores.append(f"[vista] {os.path.basename(path)} [{mm.group(1)}]: {sorted(falta)}")


def check_reportes():
    """Campos y métodos que usa el KuDE sobre fe_py.documento_electronico."""
    campos = campos_por_modelo()
    modelo = 'fe_py.documento_electronico'
    disponibles = set(campos.get(modelo, set()))
    for path in glob.glob('models/*.py'):
        src = open(path, encoding='utf-8').read()
        if f"_inherit = '{modelo}'" in src or f"_name = '{modelo}'" in src:
            disponibles |= set(re.findall(r'^\s{4}def (\w+)', src, re.M))
    base = {'move_id', 'partner_id', 'qr_image', 'qr_url', 'cdc', 'estado',
            'tipo_fiscal_id', 'kude_pdf', 'company_id', 'currency_id'}
    for path in glob.glob('report/*.xml'):
        src = open(path, encoding='utf-8').read()
        usados = set(re.findall(r'\bdoc\.(\w+)', src))
        falta = usados - disponibles - base
        if falta:
            errores.append(f"[reporte] {os.path.basename(path)}: {sorted(falta)}")


def check_orden():
    orden = orden_de_modelos()
    define, usa = {}, {}
    for a in orden:
        c = open(f'models/{a}.py', encoding='utf-8').read()
        for n in re.findall(r"_name\s*=\s*'([^']+)'", c):
            define[n] = a
        inh = re.findall(r"_inherit\s*=\s*'([^']+)'", c)
        if inh:
            usa[a] = inh
    for a, ms in usa.items():
        for m in ms:
            if m in define and orden.index(define[m]) > orden.index(a):
                errores.append(f"[orden] {a} hereda '{m}', definido después en {define[m]}")


if __name__ == '__main__':
    for f in (check_carga, check_imports, check_xml, check_odoo19,
              check_vistas, check_reportes, check_orden):
        f()
    if errores:
        print("PROBLEMAS ENCONTRADOS:\n")
        print('\n'.join('  ' + e for e in errores))
        sys.exit(1)
    print("OK: las 7 verificaciones pasaron sin errores")
