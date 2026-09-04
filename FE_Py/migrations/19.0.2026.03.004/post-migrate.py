# -*- coding: utf-8 -*-
"""Post-migración a 2026.03.001.

Corre después de que el ORM creó los modelos y catálogos nuevos.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    _volcar_configuracion(cr, env)
    _asignar_afectacion_iva(env)
    _asignar_unidad_medida_productos(env)
    _asignar_descripcion_monedas(env)
    _asignar_codigos_tipo_fiscal(env)
    _asignar_codigos_tipo_identificacion(env)
    _convertir_datos_de_operaciones(cr, env)
    _logger.info("FE_Py 2026.03.001: post-migración completada.")


def _volcar_configuracion(cr, env):
    """Crea una Configuración FEPy por Compañía con lo que estaba cargado
    en Ajustes > Empresas."""
    cr.execute("SELECT to_regclass('fe_py_migracion_config')")
    if not cr.fetchone()[0]:
        return

    cr.execute("SELECT * FROM fe_py_migracion_config")
    columnas = [d[0] for d in cr.description]
    Config = env['fe_py.configuracion'].sudo()
    Regimen = env['fe_py.tipo_regimen'].sudo()
    Actividad = env['fe_py.actividad_economica'].sudo()

    creadas = 0
    for fila in cr.fetchall():
        datos = dict(zip(columnas, fila))
        company_id = datos.pop('company_id')
        if Config.search([('company_id', '=', company_id)], limit=1):
            continue

        vals = {'company_id': company_id}
        for campo in (
            'fe_py_habilitado', 'fe_py_ambiente', 'fe_py_tipo_contribuyente',
            'fe_py_certificado_filename', 'fe_py_certificado_password',
            'fe_py_cert_path', 'fe_py_private_key_path', 'fe_py_public_key_path',
            'fe_py_certificado_vencimiento', 'fe_py_idcsc', 'fe_py_csc',
            'fe_py_envio_automatico', 'fe_py_kude_automatico',
            'fe_py_email_automatico', 'fe_py_reintento_automatico',
        ):
            if datos.get(campo) is not None:
                vals[campo] = datos[campo]

        # El régimen era un código suelto; ahora apunta al catálogo.
        codigo_reg = datos.get('fe_py_tipo_regimen')
        if codigo_reg:
            regimen = Regimen.search([('codigo', '=', codigo_reg)], limit=1)
            if regimen:
                vals['fe_py_tipo_regimen_id'] = regimen.id

        # La actividad económica era texto libre; ahora es un catálogo.
        cod_act = datos.get('fe_py_actividad_economica_codigo')
        desc_act = datos.get('fe_py_actividad_economica_desc')
        if cod_act:
            actividad = Actividad.search([('codigo', '=', cod_act)], limit=1)
            if not actividad:
                actividad = Actividad.create({
                    'codigo': cod_act, 'name': desc_act or cod_act,
                })
            vals['fe_py_actividad_economica_ids'] = [(6, 0, [actividad.id])]

        # Valores por defecto de los catálogos recién creados.
        for campo, modelo, codigo in (
            ('fe_py_sistema_facturacion_id', 'fe_py.sistema_facturacion', '1'),
            ('fe_py_tipo_emision_id', 'fe_py.tipo_emision', '1'),
            ('fe_py_condicion_tipo_cambio_id', 'fe_py.condicion_tipo_cambio', '1'),
            ('fe_py_tipo_documento_asociado_id', 'fe_py.tipo_documento_asociado', '1'),
            ('fe_py_unidad_medida_id', 'fe_py.unidad_medida', '77'),
        ):
            registro = env[modelo].sudo().search([('codigo', '=', codigo)], limit=1)
            if registro:
                vals[campo] = registro.id

        Config.create(vals)
        creadas += 1

    cr.execute("DROP TABLE IF EXISTS fe_py_migracion_config")
    _logger.info("FE_Py: %s Configuración(es) Generales FEPy creadas.", creadas)


def _asignar_afectacion_iva(env):
    """Replica exactamente el comportamiento anterior del generador: los
    impuestos de 10% y 5% eran tratados como Gravado IVA; todo lo demás,
    como Exento. Sin esto, tras actualizar no se podría generar ningún
    XML porque los impuestos quedarían sin código."""
    Afec = env['fe_py.afectacion_iva'].sudo()
    gravado = Afec.search([('codigo', '=', '1')], limit=1)
    exento = Afec.search([('codigo', '=', '3')], limit=1)
    if not (gravado and exento):
        return

    impuestos = env['account.tax'].sudo().with_context(active_test=False).search([
        ('fe_py_afectacion_iva_id', '=', False),
    ])
    n_grav = n_exe = 0
    for tax in impuestos:
        if abs(tax.amount - 10) < 0.01 or abs(tax.amount - 5) < 0.01:
            tax.fe_py_afectacion_iva_id = gravado
            n_grav += 1
        else:
            tax.fe_py_afectacion_iva_id = exento
            n_exe += 1
    _logger.info(
        "FE_Py: Afectación IVA asignada a %s impuesto(s) como Gravado y %s como "
        "Exento — replicando el comportamiento anterior. Revisar y ajustar los "
        "que correspondan (Contabilidad > Impuestos).", n_grav, n_exe,
    )


def _asignar_unidad_medida_productos(env):
    """Antes toda línea salía como "Unidad (77)". Se migra a ese mismo
    valor para no cambiar el comportamiento de golpe; después se ajustan
    los productos que vendan kilos, litros o metros."""
    unidad = env['fe_py.unidad_medida'].sudo().search([('codigo', '=', '77')], limit=1)
    if not unidad:
        return
    productos = env['product.template'].sudo().with_context(active_test=False).search([
        ('fe_py_unidad_medida_id', '=', False),
    ])
    if productos:
        productos.write({'fe_py_unidad_medida_id': unidad.id})
    _logger.info(
        "FE_Py: %s producto(s) migrados a la unidad SIFEN 'Unidad (77)'. "
        "Ajustar los que usen otra unidad.", len(productos),
    )


def _asignar_descripcion_monedas(env):
    """Las 3 monedas que el generador conocía de memoria, más las que
    Odoo trae activas por defecto."""
    descripciones = {
        'PYG': 'Guarani', 'USD': 'Dolar americano', 'EUR': 'Euro',
        'BRL': 'Real brasileño', 'ARS': 'Peso argentino',
    }
    Currency = env['res.currency'].sudo().with_context(active_test=False)
    for nombre, descripcion in descripciones.items():
        moneda = Currency.search([('name', '=', nombre)], limit=1)
        if moneda and not moneda.fe_py_descripcion:
            moneda.fe_py_descripcion = descripcion


def _asignar_codigos_tipo_fiscal(env):
    """Reemplaza el mapeo por nombre de texto que hacía el generador."""
    mapeo = {
        'Factura Electronica': ('1', 'Factura electrónica'),
        'Nota de Credito Electronica': ('5', 'Nota de crédito electrónica'),
        'Nota de Debito Electronica': ('6', 'Nota de débito electrónica'),
    }
    TipoFiscal = env['local_py.tipo_fiscal'].sudo().with_context(active_test=False)
    for nombre, (codigo, descripcion) in mapeo.items():
        tipo = TipoFiscal.search([('name', '=', nombre)], limit=1)
        if tipo and not tipo.fe_py_itide:
            tipo.write({
                'fe_py_itide': codigo,
                'fe_py_itide_descripcion': descripcion,
            })


def _asignar_codigos_tipo_identificacion(env):
    """El mapeo a la tabla D208 de SIFEN, que antes era una lista fija."""
    mapeo = {
        'local_py.tipo_identificacion_ruc': (False, False, True),
        'local_py.tipo_identificacion_cedula': ('1', 'Cédula paraguaya', False),
        'local_py.tipo_identificacion_pasaporte': ('2', 'Pasaporte', False),
        'local_py.tipo_identificacion_cedula_extranjero': ('3', 'Cédula extranjera', False),
        'local_py.tipo_identificacion_sin_nombre': ('5', 'Innominado', False),
        'local_py.tipo_identificacion_diplomatico': ('6', 'Tarjeta Diplomática de exoneración fiscal', False),
        'local_py.tipo_identificacion_tributaria': ('9', 'Otro', False),
    }
    for xmlid, (codigo, descripcion, es_ruc) in mapeo.items():
        registro = env.ref(xmlid, raise_if_not_found=False)
        if not registro:
            continue
        vals = {'fe_py_es_ruc': es_ruc}
        if codigo and not registro.fe_py_itipidrec:
            vals['fe_py_itipidrec'] = codigo
            vals['fe_py_itipidrec_descripcion'] = descripcion
        registro.sudo().write(vals)


def _convertir_datos_de_operaciones(cr, env):
    """Traduce los códigos sueltos que quedaron en comprobantes ya
    cargados a los registros del catálogo correspondiente."""
    conversiones = [
        ('account_move', 'fe_py_tipo_operacion', 'fe_py_tipo_operacion_id', 'fe_py.tipo_operacion'),
        ('account_move', 'fe_py_indicador_presencia', 'fe_py_indicador_presencia_id', 'fe_py.indicador_presencia'),
        ('account_move', 'fe_py_itimp', 'fe_py_tipo_impuesto_id', 'fe_py.tipo_impuesto'),
        ('account_move', 'fe_py_motivo_emision', 'fe_py_motivo_emision_id', 'fe_py.motivo_emision'),
        ('res_partner', 'fe_py_itimp', 'fe_py_tipo_impuesto_id', 'fe_py.tipo_impuesto'),
        ('res_partner', 'fe_py_indicador_presencia', 'fe_py_indicador_presencia_id', 'fe_py.indicador_presencia'),
    ]
    for tabla, col_vieja, col_nueva, modelo in conversiones:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = %s AND column_name = %s
        """, (tabla, col_vieja))
        if not cr.fetchone():
            continue
        for registro in env[modelo].sudo().search([]):
            cr.execute(
                "UPDATE %s SET %s = %%s WHERE %s = %%s AND %s IS NULL"
                % (tabla, col_nueva, col_vieja, col_nueva),
                (registro.id, registro.codigo),
            )
        _logger.info("FE_Py: %s.%s convertido a catálogo.", tabla, col_vieja)
