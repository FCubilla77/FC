# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LocalPyTesakaImportLinea(models.Model):
    _name = 'local_py.tesaka_import.linea'
    _description = 'Línea de Importación Tesaka'
    _order = 'id'

    import_id = fields.Many2one('local_py.tesaka_import', string='Importación', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='import_id.company_id', string='Compañía', store=True)

    # Datos tal cual vienen en el Excel de la DNIT, sin tocar.
    tipo = fields.Char(string='Tipo')
    estado_dnit = fields.Char(string='Estado (DNIT)')
    fecha_anulacion_dnit = fields.Date(string='Fecha de Anulación (DNIT)')
    comprobante = fields.Char(string='Comprobante (Nro. Retención)')
    ruc_informado = fields.Char(string='RUC Informado')
    identificacion = fields.Char(string='Identificación (exterior)')
    informado = fields.Char(string='Informado (Proveedor)')
    control = fields.Char(string='Control')
    fecha_emision_dnit = fields.Date(string='Fecha Emisión (DNIT)')
    comprobante_venta = fields.Char(string='Comprobante Venta (Nro. Factura)')
    concepto_iva = fields.Char(string='Concepto IVA')
    retenido_iva = fields.Float(string='Retenido IVA (Gs.)')

    retencion_emitida_id = fields.Many2one(
        'local_py.retencion_emitida', string='Retención emparejada', readonly=True,
    )
    resultado = fields.Selection(
        [('exito', 'Éxito'), ('error', 'Error')], string='Resultado', readonly=True,
    )
    observacion = fields.Text(string='Observación', readonly=True)

    def _buscar_retencion(self, estados):
        """Empareja esta línea del Excel contra una Retención Emitida
        nuestra, usando Factura + Monto + Fecha como clave principal (ya
        identifica el registro sin ambigüedad), y el RUC/Identificación
        del Proveedor como desempate adicional si hiciera falta (por
        ejemplo, dos proveedores distintos con el mismo número de
        factura)."""
        self.ensure_one()
        Retencion = self.env['local_py.retencion_emitida']
        domain = [
            ('company_id', '=', self.company_id.id),
            ('estado', 'in', estados),
            ('tipo_retencion', '=', 'iva'),
            ('factura_id.l10n_py_nro_documento', '=', self.comprobante_venta),
        ]
        candidatos = Retencion.search(domain)
        if self.fecha_emision_dnit:
            candidatos = candidatos.filtered(lambda r: r.fecha == self.fecha_emision_dnit)
        if self.retenido_iva:
            candidatos = candidatos.filtered(
                lambda r: abs(r.monto_gs - self.retenido_iva) <= 1
            )
        if len(candidatos) > 1:
            ruc_excel = (self.ruc_informado or self.identificacion or '').strip()
            if ruc_excel:
                candidatos_ruc = candidatos.filtered(lambda r: ruc_excel in (r.partner_id.vat or ''))
                if candidatos_ruc:
                    candidatos = candidatos_ruc
        return candidatos

    def _procesar_aceptada(self):
        self.ensure_one()
        if not self.comprobante_venta:
            self.write({'resultado': 'error', 'observacion': 'Falta el dato "Comprobante Venta" en el Excel.'})
            return
        candidatos = self._buscar_retencion(['pendiente'])
        if not candidatos:
            self.write({
                'resultado': 'error',
                'observacion': (
                    'No se encontró ninguna Retención Pendiente que coincida con la Factura "%s", '
                    'Monto %s Gs. y Fecha %s.' % (self.comprobante_venta, self.retenido_iva, self.fecha_emision_dnit)
                ),
            })
            return
        if len(candidatos) > 1:
            self.write({
                'resultado': 'error',
                'observacion': (
                    'Se encontró más de una Retención Pendiente que coincide con la Factura "%s" '
                    '— no se pudo desambiguar de forma automática. Revisar a mano.' % self.comprobante_venta
                ),
            })
            return
        candidatos.write({
            'estado': 'levantada',
            'numero_comprobante': self.comprobante,
            'control': self.control,
        })
        self.write({
            'resultado': 'exito', 'retencion_emitida_id': candidatos.id,
            'observacion': 'Marcada como Levantada correctamente.',
        })

    def _procesar_anulada(self):
        self.ensure_one()
        if not self.comprobante_venta:
            self.write({'resultado': 'error', 'observacion': 'Falta el dato "Comprobante Venta" en el Excel.'})
            return
        candidatos = self._buscar_retencion(['levantada'])
        if not candidatos:
            self.write({
                'resultado': 'error',
                'observacion': (
                    'No se encontró ninguna Retención Levantada que coincida con la Factura "%s", '
                    'Monto %s Gs. y Fecha %s — puede que ya esté Anulada, o que el Excel no traiga '
                    'primero su Aceptación.' % (self.comprobante_venta, self.retenido_iva, self.fecha_emision_dnit)
                ),
            })
            return
        if len(candidatos) > 1:
            self.write({
                'resultado': 'error',
                'observacion': (
                    'Se encontró más de una Retención Levantada que coincide con la Factura "%s" '
                    '— no se pudo desambiguar de forma automática. Revisar a mano.' % self.comprobante_venta
                ),
            })
            return
        candidatos.write({
            'estado': 'anulada',
            'fecha_anulacion': self.fecha_anulacion_dnit or fields.Date.context_today(self),
            'control': self.control or candidatos.control,
        })
        self.write({
            'resultado': 'exito', 'retencion_emitida_id': candidatos.id,
            'observacion': 'Marcada como Anulada — queda pendiente decidir si se Reprocesa o se '
                            'Anula la Orden de Pago (botón "Resolver Anulación" en la Retención).',
        })
