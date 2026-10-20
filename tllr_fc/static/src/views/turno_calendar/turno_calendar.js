import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { calendarView } from "@web/views/calendar/calendar_view";
import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { CalendarCommonPopover } from "@web/views/calendar/calendar_common/calendar_common_popover";

/**
 * Calendario de turnos del taller: al hacer clic en un turno vencido, el
 * popover agrega los botones «Marcar no asistió» y «Reprogramar».
 */
export class TurnoCalendarPopover extends CalendarCommonPopover {
    static subTemplates = {
        ...CalendarCommonPopover.subTemplates,
        footer: "tllr_fc.TurnoCalendarPopover.footer",
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
    }

    get esVencido() {
        return Boolean(this.props.record.rawRecord.vencido);
    }

    async onNoAsistio() {
        await this.orm.call(this.props.model.resModel, "action_no_asistio", [
            [this.props.record.id],
        ]);
        this.props.close();
        await this.props.model.load();
    }

    async onReprogramar() {
        const accion = await this.orm.call(this.props.model.resModel, "action_reprogramar", [
            [this.props.record.id],
        ]);
        this.props.close();
        if (accion) {
            await this.actionService.doAction(accion);
        }
    }
}

export class TurnoCalendarCommonRenderer extends CalendarCommonRenderer {
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: TurnoCalendarPopover,
    };
}

export class TurnoCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: TurnoCalendarCommonRenderer,
        week: TurnoCalendarCommonRenderer,
        month: TurnoCalendarCommonRenderer,
    };
}

registry.category("views").add("tllr_fc_turno_calendar", {
    ...calendarView,
    Renderer: TurnoCalendarRenderer,
});
