# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


# Códigos reales de las dos cuentas de Patrimonio que este proceso usa.
# Se buscan por xmlid (definidos en account.account-py.csv al instalar el
# paquete de Localización Fiscal) — si el usuario los cambió de código no
# importa, lo que se busca es el registro, no el string de código.
XMLID_RESULTADO_EJERCICIO = 'l10n_py.py_3_03_01_01_002'
XMLID_RESULTADOS_ACUMULADOS = 'l10n_py.py_3_03_01_01_001'


class L10nPyCierreEjercicio(models.Model):
    """Registro de cada Cierre de Ejercicio ejecutado (uno por compañía y
    año). Guarda los dos asientos generados (Cierre al 31/12 y Apertura al
    1/1 siguiente) para poder consultarlos y, si hace falta, deshacerlos.

    No depende de local_py: usa únicamente modelos nativos de 'account'."""
    _name = 'l10n_py.cierre_ejercicio'
    _description = 'Cierre de Ejercicio (Paraguay)'
    _order = 'anio desc'
    _rec_name = 'display_name'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, readonly=True)
    anio = fields.Integer(string='Ejercicio', required=True, readonly=True)
    fecha_cierre = fields.Date(string='Fecha de Cierre', required=True, readonly=True)
    fecha_apertura = fields.Date(string='Fecha de Apertura', required=True, readonly=True)
    move_cierre_id = fields.Many2one('account.move', string='Asiento de Cierre', readonly=True)
    move_apertura_id = fields.Many2one('account.move', string='Asiento de Apertura', readonly=True)
    resultado_ejercicio = fields.Monetary(string='Resultado del Ejercicio', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    state = fields.Selection(
        [('cerrado', 'Cerrado'), ('deshecho', 'Deshecho')],
        string='Estado', default='cerrado', readonly=True,
    )
    display_name = fields.Char(compute='_compute_display_name')

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'Cierre %s - %s' % (rec.anio, rec.company_id.name)

    def action_ver_cierre(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_cierre_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_ver_apertura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_apertura_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_deshacer(self):
        """Revierte (anula) el asiento de Apertura y el de Cierre, y
        retrocede el fiscalyear_lock_date de la compañía al día anterior
        al cierre deshecho (si no hay otro cierre posterior vigente)."""
        for rec in self:
            if rec.state == 'deshecho':
                raise UserError('Este Cierre ya fue deshecho.')
            moves = (rec.move_apertura_id | rec.move_cierre_id).filtered(
                lambda m: m.state == 'posted'
            )
            if moves:
                moves._reverse_moves(cancel=True)
            otros_cierres_posteriores = self.search([
                ('company_id', '=', rec.company_id.id),
                ('anio', '>', rec.anio),
                ('state', '=', 'cerrado'),
            ])
            if not otros_cierres_posteriores:
                rec.company_id.sudo().write({
                    'fiscalyear_lock_date': False,
                })
            rec.write({'state': 'deshecho'})

    def _get_cuenta(self, xmlid):
        cuenta = self.env.ref(xmlid, raise_if_not_found=False)
        if not cuenta:
            raise UserError(
                'No se encontró la cuenta %s. Verifique que el módulo l10n_py esté '
                'instalado y que la cuenta no haya sido eliminada.' % xmlid
            )
        return cuenta

    def _get_diario_miscelanea(self, company):
        diario = self.env['account.journal'].search([
            ('company_id', '=', company.id), ('type', '=', 'general'),
        ], limit=1)
        if not diario:
            raise UserError(
                'No se encontró un Diario de tipo "Miscelánea" en %s para postear los '
                'asientos de Cierre/Apertura.' % company.name
            )
        return diario

    @api.model
    def action_cerrar_ejercicio(self, company, anio):
        """Punto de entrada único: valida, genera y postea el Asiento de
        Cierre (31/12 de 'anio') y el Asiento de Apertura (1/1 de 'anio'+1),
        y deja el fiscalyear_lock_date de la compañía en la fecha de
        cierre. Devuelve el registro l10n_py.cierre_ejercicio creado."""
        Report = self.env['l10n_py.balance_general.report']

        fecha_referencia = fields.Date.from_string('%s-12-31' % anio)
        fy = company.compute_fiscalyear_dates(fecha_referencia)
        fecha_cierre = fy['date_to']
        fecha_apertura = fecha_cierre + timedelta(days=1)

        if self.search_count([
            ('company_id', '=', company.id), ('anio', '=', anio), ('state', '=', 'cerrado'),
        ]):
            raise UserError(
                'El ejercicio %s de %s ya tiene un Cierre vigente. Deshágalo primero si '
                'necesita regenerarlo.' % (anio, company.name)
            )

        borradores = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            ('date', '>=', fy['date_from']),
            ('date', '<=', fecha_cierre),
        ])
        if borradores:
            raise UserError(
                'Hay %s asiento(s) en borrador dentro del ejercicio %s. Confírmelos o '
                'elimínelos antes de cerrar.' % (len(borradores), anio)
            )

        diario = self._get_diario_miscelanea(company)
        cuenta_resultado_ejercicio = self._get_cuenta(XMLID_RESULTADO_EJERCICIO)

        # ------------------------------------------------------------
        # 1) Asiento de Cierre: zanja cada cuenta imputable de Ingresos/
        #    Costos/Gastos (prefijos 4,5,6,7) con movimiento en el año, y
        #    lleva el neto a "RESULTADO DEL EJERCICIO" (se ACUMULA sobre
        #    el saldo que ya tuviera esa cuenta de años anteriores todavía
        #    sin asignar — por decisión explícita: no se mueve a
        #    Resultados Acumulados automáticamente, eso queda para un
        #    futuro proceso de Asignación de Resultados).
        # ------------------------------------------------------------
        saldo_resultado = Report._compute_saldo_cuentas(
            company, fy['date_from'], fecha_cierre, prefijos=('4', '5', '6', '7'),
            prefijos_signo_invertido=('4', '6'),
        )
        if not saldo_resultado:
            raise UserError(
                'No hay movimientos en cuentas de Ingresos/Costos/Gastos en el ejercicio '
                '%s. No corresponde generar un Cierre vacío.' % anio
            )

        resultado_neto = sum(saldo_resultado.values())
        lineas_cierre = []
        for account, saldo in saldo_resultado.items():
            # 'saldo' ya viene con el signo de exposición (Ingresos
            # invertidos). Para llevar la cuenta a 0 hace falta el
            # movimiento contrario a su saldo contable real (Débito-
            # Crédito real), que es -saldo si es Ingreso (invertido) o
            # +saldo si es Costo/Gasto (no invertido). Se recalcula el
            # signo real para no arrastrar la inversión de exposición
            # al asiento contable.
            segmento = (account.code or '').split('.')[0]
            saldo_real = -saldo if segmento in ('4', '6') else saldo
            if saldo_real > 0:
                lineas_cierre.append((0, 0, {
                    'account_id': account.id,
                    'credit': saldo_real,
                    'debit': 0.0,
                    'name': 'Cierre de Ejercicio %s' % anio,
                }))
            elif saldo_real < 0:
                lineas_cierre.append((0, 0, {
                    'account_id': account.id,
                    'debit': -saldo_real,
                    'credit': 0.0,
                    'name': 'Cierre de Ejercicio %s' % anio,
                }))

        if resultado_neto > 0:
            lineas_cierre.append((0, 0, {
                'account_id': cuenta_resultado_ejercicio.id,
                'debit': resultado_neto,
                'credit': 0.0,
                'name': 'Resultado del Ejercicio %s' % anio,
            }))
        elif resultado_neto < 0:
            lineas_cierre.append((0, 0, {
                'account_id': cuenta_resultado_ejercicio.id,
                'credit': -resultado_neto,
                'debit': 0.0,
                'name': 'Resultado del Ejercicio %s' % anio,
            }))

        move_cierre = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': diario.id,
            'company_id': company.id,
            'date': fecha_cierre,
            'ref': 'Asiento de Cierre del Ejercicio %s' % anio,
            'line_ids': lineas_cierre,
        })
        move_cierre.action_post()

        # ------------------------------------------------------------
        # 2) Asiento de Apertura: reabre, al 1° de enero siguiente, el
        #    saldo de cada cuenta de Activo/Pasivo/Patrimonio (prefijos
        #    1,2,3) tal como queda luego del Cierre (incluye ya el nuevo
        #    saldo de "RESULTADO DEL EJERCICIO").
        # ------------------------------------------------------------
        saldo_balance = Report._compute_saldo_cuentas(company, fy['date_from'], fecha_cierre, prefijos=('1', '2', '3'))
        lineas_apertura = []
        for account, saldo in saldo_balance.items():
            if saldo > 0:
                lineas_apertura.append((0, 0, {
                    'account_id': account.id,
                    'debit': saldo,
                    'credit': 0.0,
                    'name': 'Apertura del Ejercicio %s' % (anio + 1),
                }))
            elif saldo < 0:
                lineas_apertura.append((0, 0, {
                    'account_id': account.id,
                    'credit': -saldo,
                    'debit': 0.0,
                    'name': 'Apertura del Ejercicio %s' % (anio + 1),
                }))

        move_apertura = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': diario.id,
            'company_id': company.id,
            'date': fecha_apertura,
            'ref': 'Asiento de Apertura del Ejercicio %s' % (anio + 1),
            'line_ids': lineas_apertura,
        })
        move_apertura.action_post()

        company.sudo().write({'fiscalyear_lock_date': fecha_cierre})

        return self.create({
            'company_id': company.id,
            'anio': anio,
            'fecha_cierre': fecha_cierre,
            'fecha_apertura': fecha_apertura,
            'move_cierre_id': move_cierre.id,
            'move_apertura_id': move_apertura.id,
            'resultado_ejercicio': resultado_neto,
        })
