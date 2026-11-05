#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificaciones estáticas de fe_py_recepcion_purchase (no necesita Odoo)."""
import glob
import os
import py_compile
import re
import sys

from lxml import etree

errores = []
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def leer(p):
    return open(p, encoding='utf-8').read()


def check_python_xml():
    for p in glob.glob('**/*.py', recursive=True):
        try:
            py_compile.compile(p, doraise=True)
        except py_compile.PyCompileError as e:
            errores.append(f"[python] {p}: {e.msg}")
    for p in glob.glob('**/*.xml', recursive=True):
        try:
            etree.parse(p)
        except etree.XMLSyntaxError as e:
            errores.append(f"[xml] {p}: {e}")


def check_manifest():
    m = eval(leer('__manifest__.py'))
    for f in m['data']:
        if not os.path.exists(f):
            errores.append(f"[manifest] no existe: {f}")
    for f in glob.glob('views/*.xml'):
        if f not in m['data']:
            errores.append(f"[manifest] no está listado: {f}")
    if not re.fullmatch(r'2026\.19\.\d{3}', m['version']):
        errores.append("[manifest] versión fuera de formato")
    if not m.get('auto_install'):
        errores.append("[manifest] debe ser auto_install")
    if set(m['depends']) != {'fe_py_recepcion', 'purchase'}:
        errores.append(f"[manifest] dependencias inesperadas: {m['depends']}")


def check_herencias():
    """Los ids de vista heredados y los campos propios deben existir en el módulo base."""
    base = '../fe_py_recepcion'
    if not os.path.isdir(base):
        return
    ids_base = set()
    for p in glob.glob(base + '/views/*.xml'):
        ids_base |= set(re.findall(r'<record id="(\w+)"', leer(p)))
    for p in glob.glob('views/*.xml'):
        for ref in re.findall(r'ref="fe_py_recepcion\.(\w+)"', leer(p)):
            if ref not in ids_base:
                errores.append(f"[herencia] {p}: la vista base '{ref}' no existe")
    campos = set()
    for p in glob.glob('models/*.py'):
        campos |= set(re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", leer(p), re.M))
    for p in glob.glob(base + '/models/*.py'):
        campos |= set(re.findall(r"^\s{4}(\w+)\s*=\s*fields\.", leer(p), re.M))
    for p in glob.glob('views/*.xml'):
        for c in re.findall(r'<field name="(\w+)"', leer(p)):
            if c not in campos and c not in ('model', 'inherit_id', 'arch', 'name'):
                errores.append(f"[vista] {p}: campo '{c}' no existe")


if __name__ == '__main__':
    for f in (check_python_xml, check_manifest, check_herencias):
        f()
    if errores:
        print("PROBLEMAS ENCONTRADOS:\n" + '\n'.join('  ' + e for e in errores))
        sys.exit(1)
    print("OK: las 3 verificaciones pasaron sin errores")
