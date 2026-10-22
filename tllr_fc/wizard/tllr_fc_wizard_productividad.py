# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time

from odoo import fields, models
from odoo.exceptions import UserError


class TllrFcWizardRepProductividad(models.TransientModel):
    """Informe de productividad: horas estándar contra horas reales.

    Horas estándar: las de los servicios propios terminados en el período. Al agrupar por
    persona se reparten entre quienes cargaron horas en el servicio, en proporción a sus horas.
    Horas reales: las horas cargadas en el período.
    """
    _name = 'tllr_fc.wizard.rep_productividad'
    _description = "Informe de productividad"

    fecha_desde = fields.Date(
        string="Desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    fecha_hasta = fields.Date(
        string="Hasta", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, default=lambda self: self.env.company)
    agrupar_por = fields.Selection(
        [('personal', "Personal de taller"), ('puesto', "Puesto"), ('servicio', "Servicio")],
        string="Agrupar por", required=True, default='personal')
    tipo_ot = fields.Selection(
        [('todos', "Todos"), ('cliente', "Cliente"), ('garantia', "Garantía"),
         ('interno', "Interno")], string="Tipo de OT", required=True, default='todos')
    personal_ids = fields.Many2many(
        'tllr_fc.personal', 'tllr_fc_rep_prod_personal_rel', 'wizard_id', 'personal_id',
        string="Personal", help="Vacío = todo el personal.")
    puesto_ids = fields.Many2many(
        'tllr_fc.puesto', 'tllr_fc_rep_prod_puesto_rel', 'wizard_id', 'puesto_id',
        string="Puestos", help="Vacío = todos.")
    servicio_ids = fields.Many2many(
        'product.product', 'tllr_fc_rep_prod_servicio_rel', 'wizard_id', 'product_id',
        string="Servicios", domain="[('type', '=', 'service')]", help="Vacío = todos.")
    linea_ids = fields.One2many(
        'tllr_fc.rep.productividad.linea', 'wizard_id', string="Líneas")

    def get_filtros(self):
        self.ensure_one()
        partes = []
        if self.tipo_ot != 'todos':
            partes.append("tipo %s" % dict(self._fields['tipo_ot'].selection)[self.tipo_ot])
        if self.personal_ids:
            partes.append("personal %s" % ', '.join(self.personal_ids.mapped('name')))
        if self.puesto_ids:
            partes.append("puestos %s" % ', '.join(self.puesto_ids.mapped('name')))
        if self.servicio_ids:
            partes.append("servicios %s" % ', '.join(self.servicio_ids.mapped('display_name')))
        return '; '.join(partes)

    def _generar_lineas(self):
        """Calcula el informe y lo deja en líneas, con una línea final de total."""
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError("La fecha final no puede ser anterior a la inicial.")
        self.linea_ids.unlink()
        modo = self.agrupar_por
        inicio = datetime.combine(self.fecha_desde, time.min)
        fin = datetime.combine(self.fecha_hasta, time.max)
        Servicio = self.env['tllr_fc.ot.servicio'].sudo()
        Hora = self.env['tllr_fc.ot.hora'].sudo()

        dom_servicio = [
            ('ot_id.company_id', '=', self.company_id.id), ('estado', '=', 'terminado'),
            ('fecha_terminado', '>=', inicio), ('fecha_terminado', '<=', fin)]
        dom_hora = [
            ('ot_id.company_id', '=', self.company_id.id),
            ('fecha', '>=', self.fecha_desde), ('fecha', '<=', self.fecha_hasta)]
        if self.tipo_ot != 'todos':
            dom_servicio.append(('ot_id.tipo', '=', self.tipo_ot))
            dom_hora.append(('ot_id.tipo', '=', self.tipo_ot))
        if self.puesto_ids:
            dom_servicio.append(('puesto_line_id.puesto_id', 'in', self.puesto_ids.ids))
            dom_hora.append(('puesto_line_id.puesto_id', 'in', self.puesto_ids.ids))
        if self.servicio_ids:
            dom_servicio.append(('product_id', 'in', self.servicio_ids.ids))
            dom_hora.append(('servicio_id.product_id', 'in', self.servicio_ids.ids))
        if self.personal_ids:
            dom_hora.append(('personal_id', 'in', self.personal_ids.ids))

        def clave(puesto, producto, persona):
            if modo == 'personal':
                return persona.id if persona else 0
            if modo == 'puesto':
                return puesto.id if puesto else 0
            return producto.id if producto else 0

        acumulado = defaultdict(lambda: {'std': 0.0, 'real': 0.0, 'ots': set()})
        ots_total = set()

        # Horas reales: las cargadas en el período.
        for hora in Hora.search(dom_hora):
            puesto = hora.puesto_line_id.puesto_id
            producto = hora.servicio_id.product_id
            acumulado[clave(puesto, producto, hora.personal_id)]['real'] += hora.horas

        # Horas estándar: servicios propios terminados en el período.
        servicios = Servicio.search(dom_servicio)
        horas_servicio = defaultdict(lambda: defaultdict(float))
        for servicio_id, personal_id, horas in Hora._read_group(
                [('servicio_id', 'in', servicios.ids)], ['servicio_id', 'personal_id'],
                ['horas:sum']):
            horas_servicio[servicio_id.id][personal_id.id] += horas
        personal_cache = {p.id: p for p in self.env['tllr_fc.personal'].sudo().browse(
            {pid for d in horas_servicio.values() for pid in d})}
        filtro_personal = set(self.personal_ids.ids)
        for servicio in servicios:
            estandar = servicio.horas_estandar
            puesto = servicio.puesto_line_id.puesto_id
            producto = servicio.product_id
            reparto = horas_servicio.get(servicio.id) or {}
            total_horas = sum(reparto.values())
            if modo == 'personal':
                if total_horas:
                    for persona_id, horas in reparto.items():
                        if filtro_personal and persona_id not in filtro_personal:
                            continue
                        registro = acumulado[persona_id]
                        registro['std'] += estandar * horas / total_horas
                        registro['ots'].add(servicio.ot_id.id)
                        ots_total.add(servicio.ot_id.id)
                elif not filtro_personal:
                    acumulado[0]['std'] += estandar
                    acumulado[0]['ots'].add(servicio.ot_id.id)
                    ots_total.add(servicio.ot_id.id)
            else:
                if filtro_personal:
                    parte = (sum(h for p, h in reparto.items() if p in filtro_personal)
                             / total_horas) if total_horas else 0.0
                else:
                    parte = 1.0
                if not parte:
                    continue
                registro = acumulado[clave(puesto, producto, False)]
                registro['std'] += estandar * parte
                registro['ots'].add(servicio.ot_id.id)
                ots_total.add(servicio.ot_id.id)

        def nombre(k):
            if modo == 'personal':
                return personal_cache.get(k, self.env['tllr_fc.personal'].sudo().browse(k)).name \
                    if k else "Sin horas registradas"
            if modo == 'puesto':
                return self.env['tllr_fc.puesto'].sudo().browse(k).name if k else "Sin puesto"
            return self.env['product.product'].sudo().browse(k).display_name if k else "Sin servicio"

        def eficiencia(estandar, real):
            return (estandar / real * 100.0) if real else 0.0

        valores = []
        filas = sorted(acumulado.items(), key=lambda kv: nombre(kv[0]).lower())
        for orden, (k, d) in enumerate(filas, start=1):
            valores.append({
                'wizard_id': self.id, 'sequence': orden, 'grupo': nombre(k),
                'horas_estandar': d['std'], 'horas_reales': d['real'],
                'eficiencia': eficiencia(d['std'], d['real']), 'ot_count': len(d['ots'])})
        if valores:
            std = sum(v['horas_estandar'] for v in valores)
            real = sum(v['horas_reales'] for v in valores)
            valores.append({
                'wizard_id': self.id, 'sequence': 10 ** 6, 'grupo': "TOTAL", 'es_total': True,
                'horas_estandar': std, 'horas_reales': real,
                'eficiencia': eficiencia(std, real), 'ot_count': len(ots_total)})
        return self.env['tllr_fc.rep.productividad.linea'].create(valores)

    def action_ver(self):
        self.ensure_one()
        self._generar_lineas()
        return {
            'type': 'ir.actions.act_window', 'name': "Productividad",
            'res_model': 'tllr_fc.rep.productividad.linea', 'view_mode': 'list',
            'views': [(False, 'list')], 'target': 'current',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False}}

    def action_imprimir(self):
        self.ensure_one()
        lineas = self._generar_lineas()
        if not lineas:
            raise UserError("No hay horas ni servicios terminados con esos filtros.")
        return self.env.ref('tllr_fc.action_report_rep_productividad').report_action(lineas)


class TllrFcRepProductividadLinea(models.TransientModel):
    _name = 'tllr_fc.rep.productividad.linea'
    _description = "Línea del informe de productividad"
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.rep_productividad', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='wizard_id.company_id')
    sequence = fields.Integer()
    grupo = fields.Char(string="Detalle")
    es_total = fields.Boolean(string="Es total")
    horas_estandar = fields.Float(string="Horas estándar", digits=(16, 2))
    horas_reales = fields.Float(string="Horas reales", digits=(16, 2))
    eficiencia = fields.Float(
        string="Eficiencia %", digits=(16, 1), help="Horas estándar ÷ horas reales.")
    ot_count = fields.Integer(string="OT terminadas")
