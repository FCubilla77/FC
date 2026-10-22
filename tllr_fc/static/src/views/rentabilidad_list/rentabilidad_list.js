import { registry } from "@web/core/registry";
import { formatFloat } from "@web/views/fields/formatters";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * Lista de «Rentabilidad de OT»: en la línea de totales el Margen % se calcula
 * como margen total / ingreso total (no como suma de porcentajes). Sin ingreso
 * y con pérdida, muestra -100 %.
 */
export class RentabilidadListRenderer extends ListRenderer {
    computeAggregates() {
        const aggregates = super.computeAggregates();
        const margen = aggregates.margen && aggregates.margen.rawValue;
        const ingreso = aggregates.ingreso && aggregates.ingreso.rawValue;
        if (margen === undefined) {
            return aggregates;
        }
        let porcentaje = 0;
        if (ingreso) {
            porcentaje = (margen / ingreso) * 100;
        } else if (margen < -0.005) {
            porcentaje = -100;
        }
        aggregates.porcentaje = {
            help: "",
            value: formatFloat(porcentaje, { digits: [16, 1] }),
            multiCurrency: false,
            rawValue: porcentaje,
        };
        return aggregates;
    }
}

registry.category("views").add("tllr_fc_rentabilidad_list", {
    ...listView,
    Renderer: RentabilidadListRenderer,
});
