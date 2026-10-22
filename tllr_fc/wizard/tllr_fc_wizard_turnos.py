# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")
ESTADOS = ('agendado', 'confirmado', 'recibido', 'no_asistio', 'cancelado')


def porcentaje_asistencia(recibidos, no_asistio):
    """Recibidos ÷ (recibidos + no asistió); los pendientes y cancelados no cuentan."""
    base = recibidos + no_asistio
    return (recibidos / base * 100.0) if base else 0.0


class TllrFcWizardRepTurnos(models.TransientModel):
    """Informe de turnos: estados y asistencia, por mes o por cliente."""
    _name = 'tllr_fc.wizard.rep_turnos'
    _description = "Informe de turnos"

    fecha_desde = fields.Date(
        string="Desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    fecha_hasta = fields.Date(
        string="Hasta", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, default=lambda self: self.env.company)
    agrupar_por = fields.Selection(
        [('mes', "Mes"), ('cliente', "Cliente (solo administrador)")],
        string="Agrupar por", required=True, default='mes')
    puesto_ids = fields.Many2many(
        'tllr_fc.puesto', 'tllr_fc_rep_turnos_puesto_rel', 'wizard_id', 'puesto_id',
        string="Puestos sugeridos", help="Vacío = todos.")
    linea_ids = fields.One2many('tllr_fc.rep.turnos.linea', 'wizard_id', string="Líneas")

    def get_filtros(self):
        self.ensure_one()
        return ("puestos %s" % ', '.join(self.puesto_ids.mapped('name'))) if self.puesto_ids else ''

    def _generar_lineas(self):
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError("La fecha final no puede ser anterior a la inicial.")
        if self.agrupar_por == 'cliente' and not self.env.user.has_group(
                'tllr_fc.group_administrador'):
            raise AccessError("El detalle por cliente solo lo ve el administrador de taller.")
        self.linea_ids.unlink()
        dominio = [
            ('company_id', '=', self.company_id.id),
            ('fecha_hora', '>=', datetime.combine(self.fecha_desde, time.min)),
            ('fecha_hora', '<=', datetime.combine(self.fecha_hasta, time.max))]
        if self.puesto_ids:
            dominio.append(('puesto_id', 'in', self.puesto_ids.ids))
        turnos = self.env['tllr_fc.turno'].sudo().search(dominio)
        grupos = defaultdict(lambda: dict.fromkeys(ESTADOS, 0))
        etiquetas = {}
        for turno in turnos:
            if self.agrupar_por == 'mes':
                fecha = fields.Datetime.context_timestamp(self, turno.fecha_hora)
                k = (fecha.year, fecha.month)
                etiquetas[k] = "%s %s" % (MESES[fecha.month - 1].capitalize(), fecha.year)
            else:
                k = (turno.partner_id.name or '', turno.partner_id.id)
                etiquetas[k] = turno.partner_id.display_name
            grupos[k][turno.state] += 1
        valores = []
        total = dict.fromkeys(ESTADOS, 0)
        for orden, k in enumerate(sorted(grupos), start=1):
            conteos = grupos[k]
            for estado in ESTADOS:
                total[estado] += conteos[estado]
            valores.append(self._valores_linea(orden, etiquetas[k], conteos))
        if valores:
            valores.append(dict(
                self._valores_linea(10 ** 6, "TOTAL", total), es_total=True))
        return self.env['tllr_fc.rep.turnos.linea'].create(valores)

    def _valores_linea(self, orden, grupo, conteos):
        return {
            'wizard_id': self.id, 'sequence': orden, 'grupo': grupo,
            'agendados': conteos['agendado'], 'confirmados': conteos['confirmado'],
            'recibidos': conteos['recibido'], 'no_asistio': conteos['no_asistio'],
            'cancelados': conteos['cancelado'], 'total': sum(conteos.values()),
            'asistencia': porcentaje_asistencia(conteos['recibido'], conteos['no_asistio'])}

    def action_ver(self):
        self.ensure_one()
        self._generar_lineas()
        return {
            'type': 'ir.actions.act_window', 'name': "Turnos",
            'res_model': 'tllr_fc.rep.turnos.linea', 'view_mode': 'list',
            'views': [(False, 'list')], 'target': 'current',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False}}

    def action_imprimir(self):
        self.ensure_one()
        lineas = self._generar_lineas()
        if not lineas:
            raise UserError("No hay turnos en el período elegido.")
        return self.env.ref('tllr_fc.action_report_rep_turnos').report_action(lineas)


class TllrFcRepTurnosLinea(models.TransientModel):
    _name = 'tllr_fc.rep.turnos.linea'
    _description = "Línea del informe de turnos"
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.rep_turnos', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='wizard_id.company_id')
    sequence = fields.Integer()
    grupo = fields.Char(string="Detalle")
    es_total = fields.Boolean(string="Es total")
    agendados = fields.Integer(string="Agendados")
    confirmados = fields.Integer(string="Confirmados")
    recibidos = fields.Integer(string="Recibidos")
    no_asistio = fields.Integer(string="No asistió")
    cancelados = fields.Integer(string="Cancelados")
    total = fields.Integer(string="Total")
    asistencia = fields.Float(
        string="Asistencia %", digits=(16, 1),
        help="Recibidos ÷ (recibidos + no asistió).")
