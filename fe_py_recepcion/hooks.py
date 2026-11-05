# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Crea la configuración de cada compañía y, solo si no hay dudas, propone
    el diario de compra y los impuestos de IVA 10%, 5% y exento.

    Es una ayuda para no empezar con la pantalla vacía: queda todo editable en
    Contabilidad > Configuración > Facturas Electrónicas Recibidas. Si hay más
    de una opción posible, no se elige ninguna.
    """
    Config = env['fe_py_recepcion.configuracion'].sudo()
    Tax = env['account.tax'].sudo()
    Journal = env['account.journal'].sudo()
    for company in env['res.company'].sudo().search([]):
        if Config.search_count([('company_id', '=', company.id)]):
            continue
        vals = {'company_id': company.id}
        diarios = Journal.search([('type', '=', 'purchase'), ('company_id', '=', company.id)])
        if len(diarios) == 1:
            vals['diario_id'] = diarios.id
        for campo, tasa in (('impuesto_iva10_id', 10.0), ('impuesto_iva5_id', 5.0),
                            ('impuesto_exento_id', 0.0)):
            impuestos = Tax.search([
                ('company_id', '=', company.id), ('type_tax_use', '=', 'purchase'),
                ('amount_type', '=', 'percent'), ('amount', '=', tasa),
            ])
            if tasa:
                impuestos = impuestos.filtered('price_include')
            if len(impuestos) == 1:
                vals[campo] = impuestos.id
        Config.create(vals)
        _logger.info("FE_Py Recepción: configuración creada para la compañía %s.", company.display_name)
