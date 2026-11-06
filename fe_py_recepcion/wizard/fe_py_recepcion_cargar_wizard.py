# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class FePyRecepcionCargarWizard(models.TransientModel):
    """Carga de uno o varios XML recibidos de proveedores (sin ZIP)."""
    _name = 'fe_py_recepcion.cargar.wizard'
    _description = 'Cargar XML de facturas electrónicas recibidas'

    attachment_ids = fields.Many2many(
        'ir.attachment', 'fe_py_recepcion_cargar_wizard_attachment_rel', 'wizard_id',
        'attachment_id', string='Archivos XML')
    resultado = fields.Html(string='Resultado', readonly=True)
    documento_ids = fields.Many2many('fe_py_recepcion.documento', string='Recepciones creadas')
    state = fields.Selection([('inicio', 'Inicio'), ('fin', 'Fin')], default='inicio')

    def action_cargar(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_('Seleccione al menos un archivo XML.'))
        Documento = self.env['fe_py_recepcion.documento']
        creados = Documento
        filas = []
        for adjunto in self.attachment_ids:
            nombre = adjunto.name or _('(sin nombre)')
            try:
                with self.env.cr.savepoint():
                    doc, creado = Documento.crear_desde_xml(nombre, adjunto.raw or b'')
            except UserError as error:
                filas.append(('danger', nombre, str(error.args[0] if error.args else error)))
                continue
            if creado:
                creados |= doc
                if doc.state == 'confirmado':
                    filas.append(('success', nombre, _(
                        'Creada y confirmada automáticamente: %(doc)s (factura %(factura)s)',
                        doc=doc.name, factura=doc.move_id.display_name)))
                elif doc.confirmacion_auto_motivo:
                    filas.append(('warning', nombre, _(
                        'Creada: %(doc)s. No se confirmó automáticamente: %(motivo)s',
                        doc=doc.name, motivo=doc.confirmacion_auto_motivo)))
                else:
                    filas.append(('success', nombre, _('Creada: %s', doc.name)))
            elif doc.state == 'cancelado':
                filas.append(('warning', nombre, _(
                    'El CDC ya fue recibido y la recepción está Cancelada (%s). '
                    'Ábrala y use "Reabrir" si corresponde.', doc.name)))
            else:
                filas.append(('warning', nombre, _(
                    'El CDC ya fue recibido (%(doc)s, estado %(estado)s); no se vuelve a crear.',
                    doc=doc.name, estado=dict(doc._fields['state'].selection)[doc.state])))
        self.attachment_ids.unlink()
        self.write({
            'documento_ids': [(6, 0, creados.ids)],
            'resultado': self._armar_resultado(filas),
            'state': 'fin',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @staticmethod
    def _armar_resultado(filas):
        from markupsafe import Markup, escape
        items = Markup('').join(
            Markup('<li class="text-%s"><b>%s</b>: %s</li>') % (clase, escape(nombre), escape(texto))
            for clase, nombre, texto in filas)
        return Markup('<ul>%s</ul>') % items

    def action_ver_recepciones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas Electrónicas Recibidas'),
            'res_model': 'fe_py_recepcion.documento',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.documento_ids.ids)],
        }
