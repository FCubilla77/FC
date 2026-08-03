# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

LINEAS_POR_PAGINA = 40


def fmt_pyg(valor, decimales=0):
    """Formatea un número al estilo guaraní: punto como separador de miles,
    coma como separador decimal (al revés de la convención en inglés que
    usa Python por defecto)."""
    if valor is False or valor is None:
        return ''
    texto = '{:,.{}f}'.format(valor, decimales)
    return texto.replace(',', '\ufffc').replace('.', ',').replace('\ufffc', '.')


class ReportLibroDiario(models.AbstractModel):
    _name = 'report.local_py.report_libro_diario_document'
    _description = 'Reporte Libro Diario'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportLibroMayor(models.AbstractModel):
    _name = 'report.local_py.report_libro_mayor_document'
    _description = 'Reporte Libro Mayor'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportLibroInventario(models.AbstractModel):
    _name = 'report.local_py.report_libro_inventario_document'
    _description = 'Reporte Libro Inventario'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportEstadoResultado(models.AbstractModel):
    _name = 'report.local_py.report_estado_resultado_document'
    _description = 'Reporte Estado de Resultado'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportStockValorizado(models.AbstractModel):
    _name = 'report.local_py.report_stock_valorizado_document'
    _description = 'Reporte Movimiento de Stock Valorizado'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportOrdenPago(models.AbstractModel):
    _name = 'report.local_py.report_orden_pago_document'
    _description = 'Reporte Orden de Pago'

    def _get_report_values(self, docids, data=None):
        docs = self.env['local_py.orden_pago'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'local_py.orden_pago',
            'docs': docs,
            'fmt_pyg': fmt_pyg,
        }


class ReportOrdenPagoListado(models.AbstractModel):
    _name = 'report.local_py.report_orden_pago_listado_document'
    _description = 'Reporte de Orden de Pago (listado)'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class ReportChequesEmitidos(models.AbstractModel):
    _name = 'report.local_py.report_cheques_listado_document'
    _description = 'Reporte de Cheques Emitidos (listado)'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('local_py_libro_render_data', {})


class LocalPyLibroReportBuilder(models.AbstractModel):
    """Lógica compartida para armar el contenido paginado de Libro Diario,
    Libro Mayor y Libro Inventario, y para vincular la generación oficial
    en PDF con la Rúbrica correspondiente. No es un modelo con tabla
    propia: es un conjunto de métodos reutilizados por los wizards."""
    _name = 'local_py.libro_report.builder'
    _description = 'Armado de Libro Diario / Libro Mayor / Libro Inventario'

    # ------------------------------------------------------------------
    # Armado del contenido (independiente de si es vista en pantalla o PDF)
    # ------------------------------------------------------------------
    def _get_moves_domain(self, company, fecha_desde, fecha_hasta):
        return [
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', fecha_desde),
            ('date', '<=', fecha_hasta),
        ]

    def _build_diario_rows(self, moves):
        """Devuelve una lista de "filas" para Libro Diario: por cada asiento,
        una fila por línea contable, y al final una fila de Comentario con
        los totales de esa asiento. Nro. Asiento y Fecha solo se muestran en
        la primera línea de cada asiento (las siguientes quedan en blanco)."""
        rows = []
        for move in moves:
            # Todas las líneas contables reales (excluye separadores visuales
            # de sección/nota, que no tienen importe). Se incluyen las líneas
            # de impuestos y la de cliente/proveedor (payment_term), que son
            # justamente las que balancean el asiento en partida doble.
            lines = move.line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
            total_debe = sum(lines.mapped('debit'))
            total_haber = sum(lines.mapped('credit'))
            for index, line in enumerate(lines):
                rows.append({
                    'tipo': 'linea',
                    'nro_asiento': move.l10n_py_nro_asiento_libro if index == 0 else '',
                    'fecha': move.date if index == 0 else None,
                    'cuenta': line.account_id.code,
                    'nombre_cuenta': line.account_id.name,
                    'debe': line.debit,
                    'haber': line.credit,
                })
            rows.append({
                'tipo': 'comentario',
                'comentario': move.l10n_py_comentario or '',
                'total_debe': total_debe,
                'total_haber': total_haber,
            })
        return rows

    def _build_mayor_groups(self, moves):
        """Devuelve una lista de GRUPOS de filas para Libro Mayor: un grupo
        por cuenta contable (en orden), cada uno con su fila de encabezado
        de cuenta y sus movimientos en orden cronológico con saldo
        acumulado. Cada grupo se pagina de forma independiente (ver
        _generar_oficial), para que ninguna hoja mezcle el detalle de más
        de una cuenta — cada cuenta nueva arranca siempre en página propia."""
        lines = self.env['account.move.line'].search([
            ('move_id', 'in', moves.ids),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ], order='account_id, date asc, move_id asc')

        groups = []
        grupo_actual = None
        cuenta_actual = None
        saldo = 0.0
        for line in lines:
            if line.account_id != cuenta_actual:
                cuenta_actual = line.account_id
                saldo = 0.0
                grupo_actual = [{
                    'tipo': 'cuenta',
                    'cuenta': cuenta_actual.code,
                    'nombre_cuenta': cuenta_actual.name,
                }]
                groups.append(grupo_actual)
            saldo += line.debit - line.credit
            grupo_actual.append({
                'tipo': 'linea',
                'fecha': line.date,
                'nro_asiento': line.move_id.l10n_py_nro_asiento_libro,
                'comentario': line.move_id.l10n_py_comentario or '',
                'debe': line.debit,
                'haber': line.credit,
                'saldo': saldo,
            })
        return groups

    def _build_balance_style_rows(self, company, fecha, config, detalle_ids, prefijos,
                                   prefijos_signo_invertido=(), fila_total_label=None):
        """Arma una lista de "filas" con el mismo formato jerárquico de
        Título/Imputable que usa Plan de Cuentas: cada Título muestra la
        suma de los saldos de las cuentas imputables que contiene
        (incluyendo las de sus Títulos hijos), y cada cuenta imputable
        muestra su propio saldo acumulado desde el 1° de enero del año de
        "fecha" hasta "fecha". Método genérico usado tanto por Libro
        Inventario (prefijos 1/2/3, formato Balance) como por Estado de
        Resultados (prefijos 4/5/6/7, con signo invertido en Ingresos para
        mostrarlos en positivo, y una fila de Resultado del Ejercicio al
        final).

        - prefijos: primeros segmentos de código a incluir (ej. ('1','2','3')).
        - prefijos_signo_invertido: de esos, cuáles se muestran como
          Crédito-Débito en vez de Débito-Crédito (ej. Ingresos).
        - fila_total_label: si se pasa, se agrega una fila final con la
          suma de todo lo relevado (ej. "Resultado del Ejercicio").
        - detalle_ids: registros de configuración de detalle (Contacto/
          Producto) a aplicar sobre las cuentas que correspondan.
        """
        fecha_inicio = fecha.replace(month=1, day=1)
        domain_base = [
            ('move_id.company_id', '=', company.id),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', fecha_inicio),
            ('date', '<=', fecha),
        ]

        detalle_por_cuenta = {det.account_id.id: det for det in detalle_ids} if detalle_ids else {}

        accounts = self.env['account.account'].search([
            ('company_ids', 'in', company.id),
        ], order='code')

        # 1) Saldo de cada cuenta imputable relevante
        saldo_por_cuenta = {}
        lines_por_cuenta = {}
        for account in accounts:
            segmento = (account.code or '').split('.')[0] if account.code else False
            if segmento not in prefijos:
                continue
            lines = self.env['account.move.line'].search(domain_base + [('account_id', '=', account.id)])
            if segmento in prefijos_signo_invertido:
                saldo = sum(lines.mapped('credit')) - sum(lines.mapped('debit'))
            else:
                saldo = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
            if not saldo and not lines:
                continue  # sin ningún movimiento en el período: se omite para no alargar el reporte
            saldo_por_cuenta[account.id] = saldo
            lines_por_cuenta[account.id] = lines

        if not saldo_por_cuenta:
            return []

        cuentas_relevantes = self.env['account.account'].browse(list(saldo_por_cuenta.keys()))

        # 2) "Subir" el saldo de cada cuenta a todos sus Títulos ancestros
        saldo_por_grupo = {}
        for account in cuentas_relevantes:
            grupo = account.group_id
            vistos = set()
            while grupo and grupo.id not in vistos:
                vistos.add(grupo.id)
                saldo_por_grupo[grupo.id] = saldo_por_grupo.get(grupo.id, 0.0) + saldo_por_cuenta[account.id]
                grupo = grupo.parent_id

        # 3) Armar nodos combinados (Títulos + Imputables), en el mismo orden
        # jerárquico que Plan de Cuentas (por código)
        nodos = []
        if saldo_por_grupo:
            for grupo in self.env['account.group'].browse(list(saldo_por_grupo.keys())):
                nodos.append({
                    'code': grupo.code_prefix_start or '',
                    'tipo': 'titulo',
                    'cuenta': grupo.code_prefix_start or '',
                    'nombre_cuenta': grupo.name,
                    'saldo': saldo_por_grupo[grupo.id],
                })
        for account in cuentas_relevantes:
            nodos.append({
                'code': account.code or '',
                'tipo': 'cuenta_balance',
                'cuenta': account.code,
                'nombre_cuenta': account.name,
                'saldo': saldo_por_cuenta[account.id],
                '_account_id': account.id,
            })
        nodos.sort(key=lambda n: n['code'])

        rows = []
        for nodo in nodos:
            nivel = nodo['code'].count('.') + 1 if nodo['code'] else 0
            rows.append({
                'tipo': nodo['tipo'],
                'cuenta': nodo['cuenta'],
                'nombre_cuenta': nodo['nombre_cuenta'],
                'saldo': nodo['saldo'],
                'nivel': nivel,
            })
            if nodo['tipo'] == 'cuenta_balance':
                detalle = detalle_por_cuenta.get(nodo['_account_id'])
                if detalle:
                    rows.extend(self._build_inventario_detalle(lines_por_cuenta[nodo['_account_id']], detalle))

        if fila_total_label:
            total = sum(saldo_por_cuenta.values())
            rows.append({
                'tipo': 'titulo',
                'cuenta': '',
                'nombre_cuenta': fila_total_label,
                'saldo': total,
                'nivel': 0,
            })

        return rows

    def _build_inventario_rows(self, company, fecha, config):
        """Devuelve las filas de Libro Inventario (Activo/Pasivo/Patrimonio,
        formato Balance). Para las cuentas configuradas en la pestaña
        "Detalle Libro Inventario", además se agrega el detalle por
        Contacto o por Producto debajo (con "Otros" si el nivel es "Top X")."""
        detalle_ids = config.libro_inventario_detalle_ids if config else self.env['local_py.libro_inventario.detalle_cuenta']
        return self._build_balance_style_rows(
            company, fecha, config, detalle_ids, prefijos=('1', '2', '3'),
        )

    def _build_estado_resultado_rows(self, company, fecha, config):
        """Devuelve las filas de Estado de Resultados (Ingresos: prefijos 4
        y 6; Costos/Gastos: prefijos 5 y 7), con Ingresos mostrados en
        positivo (Crédito - Débito) y una fila final de "Resultado del
        Ejercicio". Reutiliza la misma configuración de detalle por cuenta
        que Libro Inventario (Contacto/Producto), por si alguna cuenta de
        Ingresos o Gastos también necesitara detallarse."""
        detalle_ids = config.libro_inventario_detalle_ids if config else self.env['local_py.libro_inventario.detalle_cuenta']
        return self._build_balance_style_rows(
            company, fecha, config, detalle_ids, prefijos=('4', '5', '6', '7'),
            prefijos_signo_invertido=('4', '6'),
            fila_total_label='Resultado del Ejercicio',
        )

    def _build_inventario_detalle(self, lines, detalle):
        """Arma las filas de detalle (por Contacto o por Producto) de una
        cuenta configurada, aplicando el recorte "Top X" si corresponde."""
        campo = 'partner_id' if detalle.criterio == 'contacto' else 'product_id'
        etiqueta = 'Contacto' if detalle.criterio == 'contacto' else 'Producto'

        acumulado = {}
        for line in lines:
            registro = line[campo]
            clave = registro.id if registro else False
            nombre = registro.display_name if registro else 'Sin %s' % etiqueta.lower()
            if clave not in acumulado:
                acumulado[clave] = {'nombre': nombre, 'saldo': 0.0}
            acumulado[clave]['saldo'] += line.debit - line.credit

        items = sorted(acumulado.values(), key=lambda x: abs(x['saldo']), reverse=True)

        filas = [{'tipo': 'detalle_header', 'etiqueta': etiqueta}]
        if detalle.nivel == 'top_n' and detalle.cantidad_top and len(items) > detalle.cantidad_top:
            principales = items[:detalle.cantidad_top]
            resto = items[detalle.cantidad_top:]
            for item in principales:
                filas.append({'tipo': 'detalle_linea', 'nombre': item['nombre'], 'saldo': item['saldo']})
            filas.append({
                'tipo': 'detalle_linea',
                'nombre': 'Otros',
                'saldo': sum(x['saldo'] for x in resto),
            })
        else:
            for item in items:
                filas.append({'tipo': 'detalle_linea', 'nombre': item['nombre'], 'saldo': item['saldo']})
        filas.append({
            'tipo': 'detalle_subtotal',
            'saldo': sum(x['saldo'] for x in items),
        })
        return filas

    def _paginar(self, rows, lineas_por_pagina=LINEAS_POR_PAGINA):
        """Divide la lista de filas en páginas de tamaño fijo, agregando
        filas de arrastre "Viene de la página anterior" / "Pasa a la
        página siguiente" con los subtotales de Debe/Haber acumulados."""
        paginas = []
        pagina_actual = []
        acumulado_debe = 0.0
        acumulado_haber = 0.0

        def cerrar_pagina(es_ultima):
            nonlocal pagina_actual
            if not es_ultima:
                pagina_actual.append({
                    'tipo': 'arrastre',
                    'texto': 'Pasa a la página siguiente',
                    'total_debe': acumulado_debe,
                    'total_haber': acumulado_haber,
                })
            paginas.append(pagina_actual)
            pagina_actual = []

        for row in rows:
            if len(pagina_actual) >= lineas_por_pagina:
                cerrar_pagina(es_ultima=False)
                pagina_actual.append({
                    'tipo': 'arrastre',
                    'texto': 'Viene de la página anterior',
                    'total_debe': acumulado_debe,
                    'total_haber': acumulado_haber,
                })
            pagina_actual.append(row)
            if row.get('debe'):
                acumulado_debe += row['debe']
            if row.get('haber'):
                acumulado_haber += row['haber']

        paginas.append(pagina_actual)
        return paginas

    def _paginar_simple(self, rows, lineas_por_pagina=LINEAS_POR_PAGINA):
        """Pagina una lista de filas en tramos de tamaño fijo, sin agregar
        filas de arrastre de Débito/Crédito (no aplica a un reporte de
        formato balance, donde lo que se acumula es el Saldo, no un
        movimiento de período)."""
        return [
            rows[i:i + lineas_por_pagina]
            for i in range(0, len(rows), lineas_por_pagina)
        ] or [[]]

    # ------------------------------------------------------------------
    # Movimiento de Stock Valorizado (solo de control, sin PDF)
    # ------------------------------------------------------------------
    def _saldo_inicial_producto(self, company, producto, fecha_desde_dt):
        """Suma agregada (sin traer el detalle línea por línea, para no
        afectar el rendimiento) de valor y cantidad de todos los
        movimientos de un producto ANTERIORES a "fecha_desde_dt" — el punto
        de partida cuando el reporte no arranca desde el principio de la
        historia del producto."""
        Move = self.env['stock.move']
        base_domain = [
            ('product_id', '=', producto.id),
            ('company_id', '=', company.id),
            ('state', '=', 'done'),
            ('date', '<', fecha_desde_dt),
        ]
        entradas = Move._read_group(
            base_domain + [('is_in', '=', True)], aggregates=['value:sum', 'quantity:sum'],
        )
        salidas = Move._read_group(
            base_domain + [('is_out', '=', True)], aggregates=['value:sum', 'quantity:sum'],
        )
        valor_entrada, cantidad_entrada = entradas[0] if entradas else (0.0, 0.0)
        valor_salida, cantidad_salida = salidas[0] if salidas else (0.0, 0.0)
        valor_inicial = abs(valor_entrada or 0.0) - abs(valor_salida or 0.0)
        cantidad_inicial = (cantidad_entrada or 0.0) - (cantidad_salida or 0.0)
        return valor_inicial, cantidad_inicial

    def _build_stock_valorizado_lineas_planas(self, company, fecha_desde, fecha_hasta, product_ids=None):
        """Versión "plana" de Movimiento de Stock Valorizado: una lista de
        diccionarios, uno por fila real (incluyendo el Saldo Inicial de
        cada Cuenta como una línea más, que también participa de los
        totales de Débito/Crédito/Cantidad) — pensada para volcarse en la
        tabla temporal local_py.stock_valorizado.linea y mostrarse como
        lista nativa de Odoo, agrupada por Producto y Cuenta (Odoo arma
        los encabezados de grupo y subtotales solo)."""
        fecha_desde_dt = datetime.combine(fecha_desde, time.min)
        fecha_hasta_dt = datetime.combine(fecha_hasta, time.max)
        domain = [
            ('company_id', '=', company.id),
            ('state', '=', 'done'),
            ('date', '>=', fecha_desde_dt),
            ('date', '<=', fecha_hasta_dt),
            '|', ('is_in', '=', True), ('is_out', '=', True),
        ]
        if product_ids:
            domain.append(('product_id', 'in', product_ids.ids))

        moves = self.env['stock.move'].search(domain, order='product_id, create_date, id')

        def costo_promedio(valor_acum, cantidad_acum):
            if not cantidad_acum:
                return False
            return valor_acum / cantidad_acum

        lineas = []
        secuencia = 0
        producto_actual = None
        cuenta_actual = None
        saldo = 0.0
        saldo_cantidad = 0.0

        for move in moves:
            producto = move.product_id
            cuenta = producto.categ_id.property_stock_valuation_account_id

            if producto != producto_actual or cuenta != cuenta_actual:
                producto_actual = producto
                cuenta_actual = cuenta
                saldo, saldo_cantidad = self._saldo_inicial_producto(company, producto, fecha_desde_dt)
                if saldo or saldo_cantidad:
                    secuencia += 1
                    lineas.append({
                        'sequence': secuencia,
                        'producto_id': producto.id,
                        'cuenta_id': cuenta.id if cuenta else False,
                        'referencia': 'Saldo Inicial',
                        'nro_fiscal': False,
                        'cantidad': saldo_cantidad,
                        'costo_unitario': 0.0,
                        'costo_total': saldo,
                        'debe': saldo if saldo > 0 else 0.0,
                        'haber': -saldo if saldo < 0 else 0.0,
                        'fecha_real': False,
                        'fecha_sistema_real': False,
                        'valor_acumulado_real': saldo,
                        'cantidad_acumulada_real': saldo_cantidad,
                        'costo_promedio_real': costo_promedio(saldo, saldo_cantidad) or 0.0,
                    })

            valor = abs(move.value)
            debe = valor if move.is_in else 0.0
            haber = valor if move.is_out else 0.0
            cantidad_con_signo = move.quantity if move.is_in else -move.quantity
            saldo += debe - haber
            saldo_cantidad += cantidad_con_signo

            asiento = move.account_move_id
            secuencia += 1
            lineas.append({
                'sequence': secuencia,
                'producto_id': producto.id,
                'cuenta_id': cuenta.id if cuenta else False,
                'referencia': move.reference or move.name or '',
                'nro_fiscal': asiento.l10n_py_nro_fiscal if asiento else False,
                'cantidad': cantidad_con_signo,
                'costo_unitario': move.price_unit or move.standard_price,
                'costo_total': move.value,
                'debe': debe,
                'haber': haber,
                'fecha_real': move.date,
                'fecha_sistema_real': move.create_date,
                'valor_acumulado_real': saldo,
                'cantidad_acumulada_real': saldo_cantidad,
                'costo_promedio_real': costo_promedio(saldo, saldo_cantidad) or 0.0,
            })

        return lineas

    def _build_stock_valorizado_rows(self, company, fecha_desde, fecha_hasta, product_ids=None):
        """Arma las filas de "Movimiento de Stock Valorizado": agrupado por
        Producto (cada uno arranca en página nueva) y, dentro de cada
        Producto, por Cuenta (la de valoración de inventario configurada en
        su Categoría), con cada movimiento en el orden real en que ingresó
        al sistema (create_date del movimiento, sin posibilidad de
        reordenar), su Saldo (valor acumulado), Saldo Cantidad (cantidad
        acumulada) y Costo Promedio (Saldo / Saldo Cantidad) en cada línea.
        El rango de fechas filtra por la fecha del movimiento de stock
        (campo "date"), no por cuándo se cargó el registro. Si el rango no
        arranca desde el principio de la historia del producto, la primera
        línea de cada Cuenta es un "Saldo Inicial" con el acumulado de todo
        lo anterior a "Fecha desde" (calculado por agregación, sin traer el
        detalle histórico completo).

        Nota técnica: Odoo 19 eliminó el modelo stock.valuation.layer — el
        detalle de valoración de cada movimiento ahora vive directo en
        stock.move (campos value/is_in/is_out/quantity/price_unit)."""
        fecha_desde_dt = datetime.combine(fecha_desde, time.min)
        fecha_hasta_dt = datetime.combine(fecha_hasta, time.max)
        domain = [
            ('company_id', '=', company.id),
            ('state', '=', 'done'),
            ('date', '>=', fecha_desde_dt),
            ('date', '<=', fecha_hasta_dt),
            '|', ('is_in', '=', True), ('is_out', '=', True),
        ]
        if product_ids:
            domain.append(('product_id', 'in', product_ids.ids))

        moves = self.env['stock.move'].search(domain, order='product_id, create_date, id')

        def costo_promedio(valor_acum, cantidad_acum):
            if not cantidad_acum:
                return False
            return valor_acum / cantidad_acum

        rows = []
        producto_actual = None
        cuenta_actual = None
        saldo = 0.0
        saldo_cantidad = 0.0
        saldo_producto = 0.0
        saldo_cantidad_producto = 0.0
        total_cuenta_debe = total_cuenta_haber = total_cuenta_cantidad = 0.0
        total_producto_debe = total_producto_haber = total_producto_cantidad = 0.0

        def cerrar_cuenta():
            nonlocal saldo_producto, saldo_cantidad_producto
            if cuenta_actual is not None:
                rows.append({
                    'tipo': 'total_cuenta', 'total_debe': total_cuenta_debe,
                    'total_haber': total_cuenta_haber, 'total_cantidad': total_cuenta_cantidad,
                    'saldo': saldo, 'saldo_cantidad': saldo_cantidad,
                    'costo_promedio': costo_promedio(saldo, saldo_cantidad),
                })
                saldo_producto += saldo
                saldo_cantidad_producto += saldo_cantidad

        def cerrar_producto():
            if producto_actual is not None:
                rows.append({
                    'tipo': 'total_producto', 'total_debe': total_producto_debe,
                    'total_haber': total_producto_haber, 'total_cantidad': total_producto_cantidad,
                    'saldo': saldo_producto, 'saldo_cantidad': saldo_cantidad_producto,
                    'costo_promedio': costo_promedio(saldo_producto, saldo_cantidad_producto),
                })

        for move in moves:
            producto = move.product_id
            cuenta = producto.categ_id.property_stock_valuation_account_id

            if producto != producto_actual:
                cerrar_cuenta()
                cerrar_producto()
                producto_actual = producto
                cuenta_actual = None
                saldo_producto = 0.0
                saldo_cantidad_producto = 0.0
                total_producto_debe = total_producto_haber = total_producto_cantidad = 0.0
                rows.append({'tipo': 'producto', 'nombre': producto.display_name})

            if cuenta != cuenta_actual:
                cerrar_cuenta()
                cuenta_actual = cuenta
                total_cuenta_debe = total_cuenta_haber = total_cuenta_cantidad = 0.0
                rows.append({
                    'tipo': 'cuenta', 'cuenta': cuenta.code if cuenta else '',
                    'nombre_cuenta': cuenta.name if cuenta else 'Sin cuenta configurada',
                })
                saldo, saldo_cantidad = self._saldo_inicial_producto(company, producto, fecha_desde_dt)
                rows.append({
                    'tipo': 'saldo_inicial',
                    'referencia': 'Saldo Inicial',
                    'saldo': saldo,
                    'saldo_cantidad': saldo_cantidad,
                    'costo_promedio': costo_promedio(saldo, saldo_cantidad),
                })

            valor = abs(move.value)
            debe = valor if move.is_in else 0.0
            haber = valor if move.is_out else 0.0
            cantidad_con_signo = move.quantity if move.is_in else -move.quantity
            saldo += debe - haber
            saldo_cantidad += cantidad_con_signo
            total_cuenta_debe += debe
            total_cuenta_haber += haber
            total_cuenta_cantidad += cantidad_con_signo
            total_producto_debe += debe
            total_producto_haber += haber
            total_producto_cantidad += cantidad_con_signo

            asiento = move.account_move_id
            rows.append({
                'tipo': 'linea',
                'fecha': move.date,
                'fecha_sistema': move.create_date,
                'referencia': move.reference or move.name or '',
                'nro_fiscal': asiento.l10n_py_nro_fiscal if asiento else False,
                'cantidad': cantidad_con_signo,
                'costo_unitario': move.price_unit or move.standard_price,
                'costo_total': move.value,
                'debe': debe,
                'haber': haber,
                'saldo': saldo,
                'saldo_cantidad': saldo_cantidad,
                'costo_promedio': costo_promedio(saldo, saldo_cantidad),
            })

        cerrar_cuenta()
        cerrar_producto()
        return rows

    # ------------------------------------------------------------------
    # Generación oficial (PDF + consumo de Rúbrica)
    # ------------------------------------------------------------------
    def _generar_oficial(self, tipo_libro, company, fecha_desde, fecha_hasta, config=None):
        """Valida todo lo necesario, arma el PDF oficial, lo vincula a la
        Rúbrica correspondiente (consumiendo páginas), y devuelve el
        registro local.py.rubrica.generacion creado.

        Para Libro Inventario (tipo_libro='inventario'), "fecha_desde" es
        siempre el 1° de enero del año de "fecha_hasta" (armado por el
        wizard) — es un reporte de saldo acumulado, no de un tramo de
        asientos, por eso no aplican las mismas validaciones de "sin
        huecos" ni de Nro. Fiscal completo que sí aplican a Diario/Mayor."""
        Rubrica = self.env['local_py.rubrica']
        # Estado de Resultados comparte la misma Rúbrica ("L. Inventario") que
        # Libro Inventario — juntos forman los Estados Financieros Clasificados
        # de DNIT (Obligación 948), no tienen un Uso propio en el catálogo.
        uso = 'inventario' if tipo_libro in ('inventario', 'estado_resultado') else tipo_libro

        if fecha_hasta < fecha_desde:
            raise UserError('"Fecha hasta" no puede ser anterior a "Fecha desde".')

        rubrica = Rubrica._get_rubrica_disponible(company.id, uso)
        if not rubrica:
            raise UserError(
                'No hay una Rúbrica Confirmada con hojas disponibles para este libro en '
                'esta compañía. Cargue o complete una Rúbrica antes de continuar.'
            )

        ultima_gen = rubrica.generacion_ids.sorted('fecha_hasta')[-1:]
        if tipo_libro in ('diario', 'mayor'):
            if ultima_gen:
                esperado = ultima_gen.fecha_hasta + timedelta(days=1)
                if fecha_desde != esperado:
                    raise UserError(
                        'La "Fecha desde" debe ser %s (el día siguiente a la última '
                        'generación oficial de esta Rúbrica). No se permiten huecos ni '
                        'superposición.' % esperado.strftime('%d/%m/%Y')
                    )
        else:
            # Libro Inventario y Estado de Resultados: son reportes de saldo
            # acumulado (siempre desde el 1° de enero), no un tramo de asientos
            # — no corresponde exigir continuidad sin huecos. Comparten la misma
            # Rúbrica y suelen generarse juntos para la misma fecha (por eso se
            # permite fecha IGUAL a la última, y solo se bloquea una fecha
            # anterior a una ya generada).
            if ultima_gen and fecha_hasta < ultima_gen.fecha_hasta:
                raise UserError(
                    'Ya existe una generación oficial de este libro (o de su libro '
                    'complementario) con fecha %s. La nueva "Fecha" no puede ser '
                    'anterior a esa.' % ultima_gen.fecha_hasta.strftime('%d/%m/%Y')
                )

        es_primera_generacion = not rubrica.generacion_ids

        if tipo_libro in ('diario', 'mayor'):
            moves = self.env['account.move'].search(
                self._get_moves_domain(company, fecha_desde, fecha_hasta),
                order='date asc, id asc',
            )
            if not moves:
                raise UserError('No hay asientos confirmados en el rango de fechas elegido.')
            sin_numerar = moves.filtered(lambda m: not m.l10n_py_nro_fiscal)
            if sin_numerar:
                raise UserError(
                    'Hay %s asiento(s) en el rango elegido sin "Nro. Fiscal" asignado. '
                    'Corra primero la Renumeración Fiscal de Asientos para todo el '
                    'período antes de generar el Libro Oficial.' % len(sin_numerar)
                )
            if tipo_libro == 'diario':
                rows = self._build_diario_rows(moves)
                paginas = self._paginar(rows)
            else:
                grupos = self._build_mayor_groups(moves)
                paginas = []
                for grupo in grupos:
                    paginas.extend(self._paginar(grupo))
        elif tipo_libro == 'inventario':
            rows = self._build_inventario_rows(company, fecha_hasta, config)
            if not rows:
                raise UserError('No hay cuentas con movimientos en el período para mostrar.')
            paginas = self._paginar_simple(rows)
        else:
            rows = self._build_estado_resultado_rows(company, fecha_hasta, config)
            if not rows:
                raise UserError('No hay cuentas con movimientos en el período para mostrar.')
            paginas = self._paginar_simple(rows)

        cantidad_paginas_contenido = len(paginas)

        if es_primera_generacion:
            pagina_desde = rubrica.numero_inicial
            primera_pagina_contenido = rubrica.numero_inicial + 1
        else:
            pagina_desde = rubrica.utilizado_hasta + 1
            primera_pagina_contenido = pagina_desde
        pagina_hasta = primera_pagina_contenido + cantidad_paginas_contenido - 1

        if pagina_hasta > rubrica.numero_final:
            disponibles = rubrica.numero_final - (rubrica.utilizado_hasta or rubrica.numero_inicial - 1)
            raise UserError(
                'No hay suficientes hojas disponibles en la Rúbrica vigente: se necesitan '
                '%s y quedan %s. Complete/cargue una nueva Rúbrica para continuar.'
                % (cantidad_paginas_contenido + (1 if es_primera_generacion else 0), disponibles)
            )

        report_xmlid = {
            'diario': 'local_py.action_report_libro_diario',
            'mayor': 'local_py.action_report_libro_mayor',
            'inventario': 'local_py.action_report_libro_inventario',
            'estado_resultado': 'local_py.action_report_estado_resultado',
        }[tipo_libro]
        report_action = self.env.ref(report_xmlid)
        render_context = {
            'company': company,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'paginas': paginas,
            'pagina_inicial': primera_pagina_contenido,
            'total_paginas_libro': pagina_hasta,
            'rubrica': rubrica,
            'fmt_pyg': fmt_pyg,
        }
        pdf_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_pdf(report_action.report_name, [company.id])

        pdf_final = pdf_content
        _logger.info(
            'Libro Oficial (%s): es_primera_generacion=%s, primera_hoja cargada=%s, '
            'generaciones previas de esta Rúbrica=%s',
            tipo_libro, es_primera_generacion, bool(rubrica.primera_hoja),
            rubrica.generacion_ids.ids,
        )
        if es_primera_generacion and rubrica.primera_hoja:
            pdf_final = self._merge_primera_hoja(rubrica, pdf_content)
            _logger.info(
                'Primera hoja fusionada: PDF de contenido %s bytes -> PDF final %s bytes',
                len(pdf_content), len(pdf_final),
            )

        import base64
        pdf_final_b64 = base64.b64encode(pdf_final)

        generacion = self.env['local_py.rubrica.generacion'].create({
            'rubrica_id': rubrica.id,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'pagina_desde': pagina_desde,
            'pagina_hasta': pagina_hasta,
            'pdf_file': pdf_final_b64,
            'pdf_filename': '%s_%s_%s.pdf' % (
                {
                    'diario': 'Libro_Diario', 'mayor': 'Libro_Mayor',
                    'inventario': 'Libro_Inventario', 'estado_resultado': 'Estado_Resultado',
                }[tipo_libro],
                fecha_desde.strftime('%Y%m%d'), fecha_hasta.strftime('%Y%m%d'),
            ),
        })
        rubrica.utilizado_hasta = pagina_hasta
        return generacion

    def _try_repair_pdf(self, pdf_bytes):
        """Intenta reconstruir un PDF con problemas menores de estructura
        (xref dañado, objetos mal referenciados, etc.) usando pikepdf, que
        es más tolerante que pypdf para este tipo de casos. Es una mejora
        opcional: si pikepdf no está instalado en el servidor, devuelve
        None sin generar ningún error, y el proceso sigue con el
        comportamiento anterior (probar como imagen)."""
        import io as _io

        try:
            import pikepdf
        except ImportError:
            _logger.info('Primera hoja: pikepdf no está instalado, se omite el intento de reparación.')
            return None
        try:
            pdf = pikepdf.open(_io.BytesIO(pdf_bytes))
            output = _io.BytesIO()
            pdf.save(output)
            return output.getvalue()
        except Exception as exc:
            _logger.info('Primera hoja: pikepdf no pudo reparar el archivo (%s).', exc)
            return None

    def _append_primera_hoja_como_imagen(self, primera_hoja_bytes, writer, PdfReader):
        """Último recurso: si "Primera hoja" no se pudo leer como PDF ni
        reparar, la trata como una imagen y la convierte a una página PDF
        tamaño A4, centrada y escalada con margen."""
        import io

        try:
            from PIL import Image
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfgen import canvas
        except ImportError:
            raise UserError(
                'El archivo "Primera hoja" no es un PDF válido (ni se pudo reparar), y '
                'falta instalar Pillow/reportlab en el servidor para poder convertirlo '
                'desde imagen. Pídale al administrador del servidor que ejecute: '
                'pip install Pillow reportlab --break-system-packages'
            )
        image = Image.open(io.BytesIO(primera_hoja_bytes))
        page_width, page_height = A4
        img_width, img_height = image.size
        margen = 0.9  # deja un margen alrededor de la imagen dentro de la hoja
        escala = min(page_width / img_width, page_height / img_height) * margen
        draw_width = img_width * escala
        draw_height = img_height * escala
        x = (page_width - draw_width) / 2
        y = (page_height - draw_height) / 2
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.drawImage(
            ImageReader(image), x, y, width=draw_width, height=draw_height,
            preserveAspectRatio=True, mask='auto',
        )
        c.save()
        buffer.seek(0)
        portada_reader = PdfReader(buffer)
        for page in portada_reader.pages:
            writer.add_page(page)
        _logger.info('Primera hoja: convertida desde imagen (%s x %s px).', img_width, img_height)

    def _merge_primera_hoja(self, rubrica, pdf_content):
        """Antepone el archivo "Primera hoja" de la Rúbrica como portada del
        PDF generado, usando pypdf. Si no se puede leer directo (estructura
        dañada), intenta repararlo con pikepdf (si está instalado); si
        tampoco es un PDF válido (por ejemplo, es una imagen), la convierte
        a una página PDF como último recurso."""
        import base64
        import io

        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            raise UserError(
                'Falta instalar el paquete "pypdf" en el servidor para poder anteponer '
                '"Primera hoja" como portada del PDF. Pídale al administrador del servidor '
                'que ejecute: pip install pypdf --break-system-packages'
            )

        primera_hoja_bytes = base64.b64decode(rubrica.primera_hoja)
        writer = PdfWriter()

        try:
            portada_reader = PdfReader(io.BytesIO(primera_hoja_bytes))
            for page in portada_reader.pages:
                writer.add_page(page)
            _logger.info(
                'Primera hoja: se leyó como PDF directo (%s página(s)).',
                len(portada_reader.pages),
            )
        except Exception as exc:
            _logger.info(
                'Primera hoja: no se pudo leer como PDF directo (%s). Se intenta reparar.',
                exc,
            )
            reparado = self._try_repair_pdf(primera_hoja_bytes)
            if reparado:
                try:
                    portada_reader = PdfReader(io.BytesIO(reparado))
                    for page in portada_reader.pages:
                        writer.add_page(page)
                    _logger.info(
                        'Primera hoja: reparada con pikepdf y leída como PDF (%s página(s)).',
                        len(portada_reader.pages),
                    )
                except Exception as exc2:
                    _logger.info(
                        'Primera hoja: la reparación no funcionó (%s). Se intenta como imagen.',
                        exc2,
                    )
                    reparado = None
            if not reparado:
                self._append_primera_hoja_como_imagen(primera_hoja_bytes, writer, PdfReader)

        contenido_reader = PdfReader(io.BytesIO(pdf_content))
        for page in contenido_reader.pages:
            writer.add_page(page)
        _logger.info('PDF final: %s página(s) en total (portada + contenido).', len(writer.pages))

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    # ------------------------------------------------------------------
    # Reporte de Orden de Pago
    # ------------------------------------------------------------------
    def _build_reporte_orden_pago_rows(self, company, fecha_desde, fecha_hasta, currency_ids=None, partner_ids=None):
        """Arma las filas del Reporte de Orden de Pago: agrupado por
        Moneda y, dentro de cada Moneda, por Orden de Pago (ordenado por
        número), con el detalle de sus Medios y Facturas. Las Órdenes de
        Pago Archivadas (operaciones canceladas, nunca ejecutadas)
        aparecen solo a efectos de control numérico de la secuencia —
        con importe en cero y sin sumar a ningún total. Devuelve además
        el resumen cruzado de Medios por Moneda (por tipo de Diario)."""
        domain = [
            ('company_id', '=', company.id),
            ('fecha', '>=', fecha_desde),
            ('fecha', '<=', fecha_hasta),
        ]
        if currency_ids:
            domain.append(('currency_id', 'in', currency_ids.ids))
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids.ids))

        ordenes = self.env['local_py.orden_pago'].with_context(active_test=False).search(
            domain, order='currency_id, name',
        )

        rows = []
        resumen = {}  # {(currency, diario_name): total}
        moneda_actual = None
        total_moneda_medios = total_moneda_facturas = total_moneda_op = 0.0

        def cerrar_moneda():
            if moneda_actual is not None:
                rows.append({
                    'tipo': 'total_moneda', 'moneda': moneda_actual.name,
                    'total_medios': total_moneda_medios, 'total_facturas': total_moneda_facturas,
                    'total_op': total_moneda_op,
                })

        for orden in ordenes:
            if orden.currency_id != moneda_actual:
                cerrar_moneda()
                moneda_actual = orden.currency_id
                total_moneda_medios = total_moneda_facturas = total_moneda_op = 0.0
                rows.append({'tipo': 'moneda', 'moneda': moneda_actual.name})

            es_archivada = not orden.active
            total_op = 0.0 if es_archivada else orden.total_medios

            rows.append({
                'tipo': 'orden_pago',
                'name': orden.name,
                'estado': 'Archivado' if es_archivada else dict(orden._fields['state'].selection).get(orden.state),
                'fecha': orden.fecha,
                'proveedor': orden.partner_id.display_name,
                'total': total_op,
            })

            if not es_archivada:
                for medio in orden.medio_ids:
                    rows.append({
                        'tipo': 'medio',
                        'referencia': medio.payment_ids[:1].name if medio.payment_ids else '',
                        'diario': medio.journal_id.name,
                        'importe': medio.importe,
                        'nro_documento': medio.nro_documento or '',
                        'banco': medio.banco or '',
                        'fecha_emision': medio.fecha_emision,
                    })
                    clave = (moneda_actual, medio.journal_id.name)
                    resumen[clave] = resumen.get(clave, 0.0) + medio.importe
                for factura in orden.factura_ids:
                    rows.append({
                        'tipo': 'factura',
                        'factura': factura.move_id.name,
                        'nro_documento': factura.move_line_id.move_id.l10n_py_nro_documento or '',
                        'importe_aplicado': factura.importe_a_pagar,
                    })

                rows.append({
                    'tipo': 'total_op', 'total_medios': orden.total_medios,
                    'total_facturas': sum(orden.factura_ids.mapped('importe_a_pagar')),
                    'total_op': orden.total_medios,
                })
                total_moneda_medios += orden.total_medios
                total_moneda_facturas += sum(orden.factura_ids.mapped('importe_a_pagar'))
                total_moneda_op += orden.total_medios
            else:
                rows.append({'tipo': 'total_op', 'total_medios': 0.0, 'total_facturas': 0.0, 'total_op': 0.0})

        cerrar_moneda()

        resumen_por_moneda = {}
        for (moneda, diario), total in resumen.items():
            resumen_por_moneda.setdefault(moneda, {})[diario] = total

        return rows, resumen_por_moneda

    # ------------------------------------------------------------------
    # Reporte de Cheques Emitidos
    # ------------------------------------------------------------------
    def _build_reporte_cheques_rows(self, company, fecha_desde, fecha_hasta, chequera_ids=None):
        """Arma las filas del Reporte de Cheques Emitidos: agrupado por
        Chequera (con su Diario, Banco y Tipo), con el detalle de cada
        Cheque y su subtotal por Chequera."""
        domain = [
            ('chequera_id.company_id', '=', company.id),
            ('fecha_emision', '>=', fecha_desde),
            ('fecha_emision', '<=', fecha_hasta),
        ]
        if chequera_ids:
            domain.append(('chequera_id', 'in', chequera_ids.ids))

        cheques = self.env['local_py.chequera.cheque'].search(domain, order='chequera_id, numero')

        rows = []
        chequera_actual = None
        total_chequera = 0.0

        def cerrar_chequera():
            if chequera_actual is not None:
                rows.append({'tipo': 'total_chequera', 'total': total_chequera})

        for cheque in cheques:
            if cheque.chequera_id != chequera_actual:
                cerrar_chequera()
                chequera_actual = cheque.chequera_id
                total_chequera = 0.0
                rows.append({
                    'tipo': 'chequera',
                    'diario': chequera_actual.diario_id.name,
                    'chequera': chequera_actual.name,
                    'banco': chequera_actual.bank_id.name,
                    'tipo_chequera': dict(chequera_actual._fields['tipo'].selection).get(chequera_actual.tipo),
                })

            importe = cheque.payment_id.amount if cheque.payment_id else 0.0
            rows.append({
                'tipo': 'cheque',
                'numero': cheque.numero,
                'orden_pago': cheque.orden_pago_id.name or '',
                'estado': dict(cheque._fields['estado'].selection).get(cheque.estado),
                'fecha_emision': cheque.fecha_emision,
                'fecha_vencimiento': cheque.fecha_vencimiento,
                'importe': importe,
                'proveedor': cheque.payment_id.partner_id.display_name if cheque.payment_id else '',
            })
            if cheque.estado != 'anulado':
                total_chequera += importe

        cerrar_chequera()
        return rows
