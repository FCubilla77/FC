# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models
from odoo.exceptions import UserError

LINEAS_POR_PAGINA = 40


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


class LocalPyLibroReportBuilder(models.AbstractModel):
    """Lógica compartida para armar el contenido paginado de Libro Diario y
    Libro Mayor, y para vincular la generación oficial en PDF con la
    Rúbrica correspondiente. No es un modelo con tabla propia: es un
    conjunto de métodos reutilizados por el wizard."""
    _name = 'local_py.libro_report.builder'
    _description = 'Armado de Libro Diario / Libro Mayor'

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

    def _build_mayor_rows(self, moves):
        """Devuelve una lista de "filas" para Libro Mayor: agrupado por
        cuenta contable, cada movimiento en orden cronológico con su saldo
        acumulado."""
        lines = self.env['account.move.line'].search([
            ('move_id', 'in', moves.ids),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ], order='account_id, date asc, move_id asc')

        rows = []
        cuenta_actual = None
        saldo = 0.0
        for line in lines:
            if line.account_id != cuenta_actual:
                cuenta_actual = line.account_id
                saldo = 0.0
                rows.append({
                    'tipo': 'cuenta',
                    'cuenta': cuenta_actual.code,
                    'nombre_cuenta': cuenta_actual.name,
                })
            saldo += line.debit - line.credit
            rows.append({
                'tipo': 'linea',
                'fecha': line.date,
                'nro_asiento': line.move_id.l10n_py_nro_asiento_libro,
                'comentario': line.move_id.l10n_py_comentario or '',
                'debe': line.debit,
                'haber': line.credit,
                'saldo': saldo,
            })
        return rows

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

    # ------------------------------------------------------------------
    # Generación oficial (PDF + consumo de Rúbrica)
    # ------------------------------------------------------------------
    def _generar_oficial(self, tipo_libro, company, fecha_desde, fecha_hasta):
        """Valida todo lo necesario, arma el PDF oficial, lo vincula a la
        Rúbrica correspondiente (consumiendo páginas), y devuelve el
        registro local.py.rubrica.generacion creado."""
        Rubrica = self.env['local_py.rubrica']
        uso = tipo_libro  # 'diario' o 'mayor', coincide con USO_SELECTION

        if fecha_hasta < fecha_desde:
            raise UserError('"Fecha hasta" no puede ser anterior a "Fecha desde".')

        rubrica = Rubrica._get_rubrica_disponible(company.id, uso)
        if not rubrica:
            raise UserError(
                'No hay una Rúbrica Confirmada con hojas disponibles para este libro en '
                'esta compañía. Cargue o complete una Rúbrica antes de continuar.'
            )

        ultima_gen = rubrica.generacion_ids.sorted('fecha_hasta')[-1:]
        if ultima_gen:
            esperado = ultima_gen.fecha_hasta + timedelta(days=1)
            if fecha_desde != esperado:
                raise UserError(
                    'La "Fecha desde" debe ser %s (el día siguiente a la última generación '
                    'oficial de esta Rúbrica). No se permiten huecos ni superposición.'
                    % esperado.strftime('%d/%m/%Y')
                )

        moves = self.env['account.move'].search(
            self._get_moves_domain(company, fecha_desde, fecha_hasta),
            order='date asc, id asc',
        )
        if not moves:
            raise UserError('No hay asientos confirmados en el rango de fechas elegido.')

        sin_numerar = moves.filtered(lambda m: not m.l10n_py_nro_fiscal)
        if sin_numerar:
            raise UserError(
                'Hay %s asiento(s) en el rango elegido sin "Nro. Fiscal" asignado. Corra '
                'primero la Renumeración Fiscal de Asientos para todo el período antes de '
                'generar el Libro Oficial.' % len(sin_numerar)
            )

        es_primera_generacion = not rubrica.generacion_ids
        if tipo_libro == 'diario':
            rows = self._build_diario_rows(moves)
        else:
            rows = self._build_mayor_rows(moves)
        paginas = self._paginar(rows)
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

        report_xmlid = (
            'local_py.action_report_libro_diario' if tipo_libro == 'diario'
            else 'local_py.action_report_libro_mayor'
        )
        report_action = self.env.ref(report_xmlid)
        render_context = {
            'company': company,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'paginas': paginas,
            'pagina_inicial': primera_pagina_contenido,
            'total_paginas_libro': pagina_hasta,
            'rubrica': rubrica,
        }
        pdf_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_pdf(report_action.report_name, [company.id])

        pdf_final = pdf_content
        if es_primera_generacion and rubrica.primera_hoja:
            pdf_final = self._merge_primera_hoja(rubrica, pdf_content)

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
                'Libro_Diario' if tipo_libro == 'diario' else 'Libro_Mayor',
                fecha_desde.strftime('%Y%m%d'), fecha_hasta.strftime('%Y%m%d'),
            ),
        })
        rubrica.utilizado_hasta = pagina_hasta
        return generacion

    def _merge_primera_hoja(self, rubrica, pdf_content):
        """Antepone el archivo "Primera hoja" de la Rúbrica como portada del
        PDF generado, usando pypdf. Si "Primera hoja" no es un PDF válido
        (por ejemplo, una imagen), la convierte a una página PDF primero."""
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
        except Exception:
            try:
                from PIL import Image
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.utils import ImageReader
                from reportlab.pdfgen import canvas
            except ImportError:
                raise UserError(
                    'El archivo "Primera hoja" no es un PDF válido, y falta instalar '
                    'Pillow/reportlab en el servidor para poder convertirlo desde imagen. '
                    'Pídale al administrador del servidor que ejecute: '
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

        contenido_reader = PdfReader(io.BytesIO(pdf_content))
        for page in contenido_reader.pages:
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
