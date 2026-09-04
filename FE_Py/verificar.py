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


def relaciones_por_modelo():
    """Mapa modelo -> {campo relacional: modelo destino}, para poder
    validar los sub-listados embebidos contra el modelo correcto y no
    contra el del formulario que los contiene."""
    rel = {}
    for path in glob.glob('models/*.py'):
        src = open(path, encoding='utf-8').read()
        for cm in re.finditer(r"class \w+\([^)]*\):(.*?)(?=\nclass |\Z)", src, re.S):
            cuerpo = cm.group(1)
            mm = re.search(r"_(?:name|inherit)\s*=\s*'([^']+)'", cuerpo)
            if not mm:
                continue
            for fm in re.finditer(
                r"^\s{4}(\w+)\s*=\s*fields\.(?:One2many|Many2many|Many2one)\(\s*\n?\s*'([^']+)'",
                cuerpo, re.M,
            ):
                rel.setdefault(mm.group(1), {})[fm.group(1)] = fm.group(2)
            # related: el destino se deduce del último tramo
            for fm in re.finditer(
                r"^\s{4}(\w+)\s*=\s*fields\.\w+\([^)]*related='([\w.]+)'", cuerpo, re.M | re.S,
            ):
                rel.setdefault(mm.group(1), {})[fm.group(1)] = '__related__'
    return rel


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


BASE_ODOO = {'display_name', 'id', 'create_date', 'write_date', 'create_uid',
             'write_uid', 'company_id', 'currency_id', 'active', 'sequence'}


def _validar_bloque(arch, modelo, propios, rel, path, errores):
    """Valida un bloque de vista contra su modelo, entrando en cada
    sub-listado embebido con el modelo que le corresponde."""
    # Sub-listados: <field name="x"> ... <list> ... </list> ... </field>
    for sub in re.finditer(
        r'<field name="(\w+)"[^>]*>\s*<list[^>]*>(.*?)</list>', arch, re.S
    ):
        campo, cuerpo = sub.group(1), sub.group(2)
        destino = rel.get(modelo, {}).get(campo)
        if destino and destino in propios:
            usados = set(re.findall(r'<field name="(\w+)"', cuerpo))
            falta = usados - propios[destino] - BASE_ODOO
            if falta:
                errores.append(
                    f"[vista] {os.path.basename(path)} [{modelo} > {campo} -> {destino}]: {sorted(falta)}"
                )
    # El resto del bloque, sin los sub-listados
    resto = re.sub(r'<field name="\w+"[^>]*>\s*<list[^>]*>.*?</list>\s*</field>', '',
                   arch, flags=re.S)
    resto = re.sub(r'<list[^>]*>.*?</list>', '', resto, flags=re.S)
    usados = set(re.findall(r'<field name="(\w+)"', resto))
    usados |= set(re.findall(r'invisible="[^"]*?\b(\w+)\s*(?:!=|==|not in| in )', resto))
    falta = usados - propios[modelo] - BASE_ODOO
    if falta:
        errores.append(f"[vista] {os.path.basename(path)} [{modelo}]: {sorted(falta)}")


def check_vistas():
    campos = campos_por_modelo()
    rel = relaciones_por_modelo()
    propios = {m: c for m, c in campos.items() if m.startswith('fe_py.')}
    for path in glob.glob('views/*.xml'):
        src = open(path, encoding='utf-8').read()
        for rec in re.finditer(r'<record id="[^"]+" model="ir\.ui\.view">(.*?)</record>', src, re.S):
            b = rec.group(1)
            mm = re.search(r'<field name="model">([^<]+)</field>', b)
            ar = re.search(r'<field name="arch" type="xml">(.*)</field>', b, re.S)
            if not (mm and ar) or mm.group(1) not in propios:
                continue
            _validar_bloque(ar.group(1), mm.group(1), propios, rel, path, errores)


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




def check_vistas_externas():
    """Vistas sobre modelos de Odoo/local_py: no conocemos sus campos
    nativos, pero SÍ los que agrega FE_Py. Se verifica que todo campo
    fe_py_* usado exista realmente en ese modelo."""
    campos = campos_por_modelo()
    rel = relaciones_por_modelo()
    for path in glob.glob('views/*.xml'):
        src = open(path, encoding='utf-8').read()
        for rec in re.finditer(r'<record id="[^"]+" model="ir\.ui\.view">(.*?)</record>', src, re.S):
            b = rec.group(1)
            mm = re.search(r'<field name="model">([^<]+)</field>', b)
            ar = re.search(r'<field name="arch" type="xml">(.*)</field>', b, re.S)
            if not (mm and ar) or mm.group(1).startswith('fe_py.'):
                continue
            modelo = mm.group(1)
            propios = campos.get(modelo, set())
            arch = ar.group(1)
            # sub-listados con su comodelo
            for sub in re.finditer(r'<field name="(\w+)"[^>]*>\s*<list[^>]*>(.*?)</list>', arch, re.S):
                destino = rel.get(modelo, {}).get(sub.group(1))
                if destino and destino in campos:
                    usados = {c for c in re.findall(r'<field name="(\w+)"', sub.group(2))
                              if c.startswith('fe_py_')}
                    falta = usados - campos[destino]
                    if falta:
                        errores.append(
                            f"[vista-ext] {os.path.basename(path)} "
                            f"[{modelo} > {sub.group(1)} -> {destino}]: {sorted(falta)}")
            resto = re.sub(r'<field name="\w+"[^>]*>\s*<list[^>]*>.*?</list>\s*</field>', '',
                           arch, flags=re.S)
            usados = {c for c in re.findall(r'<field name="(\w+)"', resto) if c.startswith('fe_py_')}
            usados |= {c for c in re.findall(r'invisible="[^"]*?\b(fe_py_\w+)', resto)}
            falta = usados - propios
            if falta:
                errores.append(f"[vista-ext] {os.path.basename(path)} [{modelo}]: {sorted(falta)}")


def check_botones():
    """Todo botón type=object debe tener su método en algún modelo."""
    metodos = set()
    for p in glob.glob('models/*.py') + glob.glob('wizard/*.py'):
        metodos |= set(re.findall(r'^\s+def (\w+)', open(p, encoding='utf-8').read(), re.M))
    for path in glob.glob('views/*.xml'):
        src = open(path, encoding='utf-8').read()
        for b in re.finditer(r'<button[^>]*name="(\w+)"[^>]*type="object"', src):
            if b.group(1) not in metodos:
                errores.append(f"[boton] {os.path.basename(path)}: método '{b.group(1)}' no existe")
        for b in re.finditer(r'<button[^>]*type="object"[^>]*name="(\w+)"', src):
            if b.group(1) not in metodos:
                errores.append(f"[boton] {os.path.basename(path)}: método '{b.group(1)}' no existe")


def check_datos():
    """Los archivos de datos no deben escribir campos inexistentes."""
    campos = campos_por_modelo()
    for path in glob.glob('data/*.xml'):
        src = open(path, encoding='utf-8').read()
        for rec in re.finditer(r'<record[^>]*model="([\w.]+)"[^>]*>(.*?)</record>', src, re.S):
            modelo, cuerpo = rec.group(1), rec.group(2)
            if modelo not in campos:
                continue
            usados = set(re.findall(r'<field name="(\w+)"', cuerpo))
            if not modelo.startswith('fe_py.'):
                # Modelo ajeno (Odoo/local_py): solo se pueden verificar los
                # campos que agrega FE_Py, los nativos no los conocemos.
                usados = {c for c in usados if c.startswith('fe_py_')}
            falta = usados - campos[modelo] - BASE_ODOO
            if falta:
                errores.append(f"[datos] {os.path.basename(path)} [{modelo}]: {sorted(falta)}")


def check_permisos():
    """Todo modelo propio debe tener permisos, y todo permiso referenciar
    un modelo que exista."""
    definidos = set()
    for p in glob.glob('models/*.py'):
        definidos |= set(re.findall(r"_name\s*=\s*'(fe_py\.[\w.]+)'", open(p, encoding='utf-8').read()))
    definidos = {m for m in definidos if m != 'fe_py.catalogo.base'}
    csv = open('security/ir.model.access.csv', encoding='utf-8').read()
    con_permiso = set(re.findall(r'model_(fe_py_[\w]+)', csv))
    for m in definidos:
        if m.replace('.', '_') not in con_permiso:
            errores.append(f"[permisos] el modelo '{m}' no tiene permisos definidos")
    for p in con_permiso:
        if p.replace('fe_py_', 'fe_py.', 1).replace('_', '.') not in \
           {m.replace('.', '_').replace('fe_py_', 'fe_py.', 1).replace('_', '.') for m in definidos}:
            esperado = {m.replace('.', '_') for m in definidos}
            if p not in esperado:
                errores.append(f"[permisos] permiso para 'model_{p}', que no corresponde a ningún modelo")


def check_referencias_internas():
    """compute=, related= e inverse_name deben apuntar a algo que exista."""
    campos = campos_por_modelo()
    for path in glob.glob('models/*.py'):
        src = open(path, encoding='utf-8').read()
        metodos = set(re.findall(r'^\s+def (\w+)', src, re.M))
        for cm in re.finditer(r"class \w+\([^)]*\):(.*?)(?=\nclass |\Z)", src, re.S):
            cuerpo = cm.group(1)
            mm = re.search(r"_(?:name|inherit)\s*=\s*'([^']+)'", cuerpo)
            if not mm:
                continue
            for c in re.findall(r"compute='(\w+)'", cuerpo):
                if c not in metodos:
                    errores.append(f"[compute] {os.path.basename(path)}: '{c}' no está definido")
            # related: el primer tramo debe existir en el mismo modelo
            for r in re.findall(r"related='([\w.]+)'", cuerpo):
                primero = r.split('.')[0]
                propios = campos.get(mm.group(1), set())
                if propios and primero not in propios and primero not in BASE_ODOO and \
                   not primero.startswith(('move', 'partner', 'invoice', 'journal', 'property',
                                           'l10n', 'local', 'product', 'uom', 'tax')):
                    errores.append(
                        f"[related] {os.path.basename(path)} [{mm.group(1)}]: "
                        f"'{r}' arranca por '{primero}', que no existe en el modelo")


def check_menus():
    """Todo menuitem con parent local debe apuntar a un menú definido antes."""
    definidos, orden_archivos = {}, []
    manifest = open('__manifest__.py', encoding='utf-8').read()
    for m in re.finditer(r'"(views/[\w.]+\.xml)"', manifest):
        orden_archivos.append(m.group(1))
    for idx, f in enumerate(orden_archivos):
        if not os.path.exists(f):
            errores.append(f"[manifest] '{f}' está en el manifest pero no existe")
            continue
        for m in re.finditer(r'<menuitem\s+id="(\w+)"', open(f, encoding='utf-8').read()):
            definidos.setdefault(m.group(1), idx)
    for idx, f in enumerate(orden_archivos):
        if not os.path.exists(f):
            continue
        src = open(f, encoding='utf-8').read()
        for m in re.finditer(r'<menuitem\s+id="(\w+)"[^>]*?parent="([\w.]+)"', src, re.S):
            padre = m.group(2)
            if '.' in padre:
                continue
            if padre not in definidos:
                errores.append(f"[menu] {f}: parent '{padre}' no está definido en el módulo")
            elif definidos[padre] > idx:
                errores.append(f"[menu] {f}: parent '{padre}' se carga después")


def check_archivos_manifest():
    """Todo archivo del manifest debe existir, y todo XML debe estar listado."""
    manifest = open('__manifest__.py', encoding='utf-8').read()
    listados = set(re.findall(r'"((?:data|views|report|security)/[\w./]+)"', manifest))
    for f in listados:
        if not os.path.exists(f):
            errores.append(f"[manifest] listado pero no existe: {f}")
    for f in glob.glob('data/*.xml') + glob.glob('views/*.xml') + glob.glob('report/*.xml'):
        if f not in listados:
            errores.append(f"[manifest] existe pero NO está listado: {f}")


if __name__ == '__main__':
    for f in (check_carga, check_imports, check_xml, check_odoo19,
              check_vistas, check_vistas_externas, check_reportes, check_orden,
              check_botones, check_datos, check_permisos,
              check_referencias_internas, check_menus, check_archivos_manifest):
        f()
    if errores:
        print("PROBLEMAS ENCONTRADOS:\n")
        print('\n'.join('  ' + e for e in errores))
        sys.exit(1)
    print("OK: las 14 verificaciones pasaron sin errores")
