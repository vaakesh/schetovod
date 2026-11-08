from datetime import date
from decimal import Decimal
from functools import partial
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.enums import LedgerKind
from core.schema_types import format_invoice_date
from reports.schemas import PeriodReport, PrintedInvoice, ReportDay, ReportMovement

# fonts-dejavu-core in the image, the built-in PDF fonts have no cyrillic
FONT_DIR = Path(
    "/usr/share/fonts/truetype/dejavu",
)
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
FONT_SIZE = 7.5
PAGE_SIZE = landscape(
    pagesize=A4,
)
MARGIN = 10 * mm
GRID = colors.HexColor(
    val="#b0b0b0",
)
SHADE = colors.HexColor(
    val="#eeeeee",
)
MUTED = "#555555"

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MOVEMENT_LABELS = {
    LedgerKind.INVOICE: "накладные",
    LedgerKind.SALE: "продажа",
    LedgerKind.WRITE_OFF: "списание",
    LedgerKind.STOCK_IN: "приход товара",
    LedgerKind.STOCKTAKE: "переучёт",
    LedgerKind.REVALUATION: "переоценка",
    LedgerKind.CASH_IN: "внесение",
    LedgerKind.CASH_OUT: "выдача",
    LedgerKind.CASH_COUNT: "сверка кассы",
}
HEADER = (
    "Дата",
    "Фирма, №",
    "Закупка",
    "Оплачено",
    "Приход",
    "Нал",
    "Безнал",
    "Выручка",
    "Касса",
    "Товар",
)
# millimetres, the frame of the landscape page is about 272 wide inside its padding
WIDTHS = (15, 44, 22, 22, 22, 22, 22, 22, 40, 40)
DEBT_HEADER = (
    "Фирма",
    "№",
    "Дата",
    "Закупка",
    "Оплачено",
    "Долг",
)
DEBT_WIDTHS = (70, 30, 22, 26, 26, 26)
INVOICE_FONT_SIZE = 8.5
HEAD_SHADE = colors.HexColor(
    val="#e2e2e2",
)
STRIPE = colors.HexColor(
    val="#f6f6f6",
)
INVOICE_HEADER = (
    "№",
    "Название",
    "Кол-во",
    "Ед.",
    # two lines, the columns stay as narrow as their numbers
    "Цена\nрозн.",
    "Сумма\nрозн.",
)
# millimetres, the portrait page is 190 wide inside the margins,
# the 35 left on the right are for the sums written by hand
INVOICE_WIDTHS = (7, 85, 15, 10, 18, 20)


def report_pdf_filename(report: PeriodReport) -> str:
    date_from = format_invoice_date(
        value=report.date_from,
    )
    date_to = format_invoice_date(
        value=report.date_to,
    )
    return f"otchet_{date_from}_{date_to}.pdf"


def report_pdf(report: PeriodReport) -> bytes:
    """daily invoices and balance movements, then the debts to the suppliers"""
    _register_fonts()
    styles = _Styles()
    date_from = _full_date(
        value=report.date_from,
    )
    date_to = _full_date(
        value=report.date_to,
    )
    story: list[Flowable] = [
        Paragraph(
            text=f"Отчёт с {date_from} по {date_to}",
            style=styles.title,
        ),
        Spacer(
            width=0,
            height=3 * mm,
        ),
        _days_table(
            report=report,
            styles=styles,
        ),
        Spacer(
            width=0,
            height=2 * mm,
        ),
        Paragraph(
            text=(
                "Касса и Товар — жирным остатки на начало и конец дня, "
                "между ними изменения со знаком. Сторнированные операции не показаны. "
                "Приход и Товар — в розничных ценах, "
                "Закупка — сколько должны поставщику, Оплачено — по накладной на конец периода."
            ),
            style=styles.note,
        ),
        Spacer(
            width=0,
            height=5 * mm,
        ),
        Paragraph(
            text=f"Оплачено поставщикам за период: {_money(value=report.paid_in_period)}",
            style=styles.heading,
        ),
        Spacer(
            width=0,
            height=3 * mm,
        ),
    ]
    if report.debts:
        story += [
            Paragraph(
                text=f"Долги поставщикам на {date_to}",
                style=styles.heading,
            ),
            Spacer(
                width=0,
                height=2 * mm,
            ),
            _debts_table(
                report=report,
                styles=styles,
            ),
        ]
    else:
        story.append(
            Paragraph(
                text=f"Долгов поставщикам на {date_to} нет",
                style=styles.heading,
            ),
        )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        filename=buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=12 * mm,
        title=f"Отчёт с {date_from} по {date_to}",
    )
    page_number = partial(
        _page_number,
        page_width=PAGE_SIZE[0],
    )
    document.build(
        flowables=story,
        onFirstPage=page_number,
        onLaterPages=page_number,
    )
    return buffer.getvalue()


class _Styles:
    def __init__(self) -> None:
        self.title = ParagraphStyle(
            name="title",
            fontName=FONT_BOLD,
            fontSize=12,
            leading=15,
        )
        self.heading = ParagraphStyle(
            name="heading",
            fontName=FONT_BOLD,
            fontSize=9,
            leading=11,
        )
        self.cell = ParagraphStyle(
            name="cell",
            fontName=FONT,
            fontSize=FONT_SIZE,
            leading=FONT_SIZE + 1.5,
        )
        self.movement = ParagraphStyle(
            name="movement",
            parent=self.cell,
            alignment=TA_RIGHT,
        )
        # the printed invoices have fewer columns and room for a larger font
        self.invoice_cell = ParagraphStyle(
            name="invoice_cell",
            parent=self.cell,
            fontSize=INVOICE_FONT_SIZE,
            leading=INVOICE_FONT_SIZE + 1.5,
        )
        # a paragraph ignores the ALIGN of its cell
        self.invoice_unit = ParagraphStyle(
            name="invoice_unit",
            parent=self.invoice_cell,
            alignment=TA_CENTER,
        )
        self.invoice_title = ParagraphStyle(
            name="invoice_title",
            fontName=FONT,
            fontSize=10,
            leading=13,
        )
        self.note = ParagraphStyle(
            name="note",
            parent=self.cell,
            fontSize=FONT_SIZE - 1,
            leading=FONT_SIZE,
            textColor=MUTED,
        )


def _days_table(
    report: PeriodReport,
    styles: _Styles,
) -> Table:
    zero = Decimal(
        value=0,
    )
    rows: list[list[object]] = [
        list(
            HEADER,
        ),
        [
            "На начало периода",
            *[""] * (len(HEADER) - 3),
            _money(
                value=report.cash_opening,
            ),
            _money(
                value=report.opening,
            ),
        ],
    ]
    # the first and the last row of each day
    day_spans: list[tuple[int, int]] = []
    for day in report.days:
        start = len(
            rows,
        )
        rows += _day_rows(
            day=day,
            styles=styles,
        )
        day_spans.append(
            (
                start,
                len(
                    rows,
                )
                - 1,
            ),
        )
    last = report.days[-1] if report.days else None
    invoices = [invoice for day in report.days for invoice in day.invoices]
    sales_cash = sum(
        (day.sales_cash for day in report.days),
        start=zero,
    )
    sales_card = sum(
        (day.sales_card for day in report.days),
        start=zero,
    )
    # the index of the totals row appended next
    total = len(
        rows,
    )
    rows.append(
        [
            "Итого",
            "",
            _money(
                value=sum(
                    (invoice.cost_total for invoice in invoices),
                    start=zero,
                ),
            ),
            _money(
                value=sum(
                    (invoice.paid for invoice in invoices),
                    start=zero,
                ),
            ),
            _money(
                value=sum(
                    (invoice.retail_total for invoice in invoices),
                    start=zero,
                ),
            ),
            _money(
                value=sales_cash,
            ),
            _money(
                value=sales_card,
            ),
            _money(
                value=sales_cash + sales_card,
            ),
            _money(
                value=last.cash_after if last else report.cash_opening,
            ),
            _money(
                value=last.balance_after if last else report.opening,
            ),
        ],
    )
    table = Table(
        data=rows,
        colWidths=[width * mm for width in WIDTHS],
        repeatRows=1,
    )
    commands: list[tuple] = [
        ("FONT", (0, 0), (-1, -1), FONT, FONT_SIZE),
        ("FONT", (0, 0), (-1, 0), FONT_BOLD, FONT_SIZE),
        ("FONT", (-2, 1), (-1, 1), FONT_BOLD, FONT_SIZE),
        ("FONT", (0, total), (-1, total), FONT_BOLD, FONT_SIZE),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("BACKGROUND", (0, 1), (-1, 1), SHADE),
        ("BACKGROUND", (0, total), (-1, total), SHADE),
        ("SPAN", (0, 1), (-3, 1)),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEABOVE", (0, total), (-1, total), 0.6, colors.black),
        ("LINEAFTER", (0, 0), (-2, -1), 0.3, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    for start, end in day_spans:
        commands.extend(
            [
                ("LINEABOVE", (0, start), (-1, start), 0.3, GRID),
                ("FONT", (-2, start), (-1, start), FONT_BOLD, FONT_SIZE),
                ("FONT", (-2, end), (-1, end), FONT_BOLD, FONT_SIZE),
            ],
        )
    table.setStyle(
        tblstyle=TableStyle(
            cmds=commands,
        ),
    )
    return table


def _day_rows(
    day: ReportDay,
    styles: _Styles,
) -> list[list[object]]:
    """independent movement columns between shared opening and closing rows,
    no day spans so a long day can continue on the next page"""
    date_text = _short_date(
        value=day.day,
    )
    rows: list[list[object]] = [
        [
            f"{date_text}\n{WEEKDAYS[day.day.weekday()]}",
            "",
            "",
            "",
            "",
            _money(
                value=day.sales_cash,
                blank_zero=True,
            ),
            _money(
                value=day.sales_card,
                blank_zero=True,
            ),
            _money(
                value=day.sales_cash + day.sales_card,
                blank_zero=True,
            ),
            _money(
                value=day.cash_opening,
            ),
            _money(
                value=day.opening,
            ),
        ],
    ]
    # each movement gets its own row between the opening and closing balances
    rows += [
        [""] * len(HEADER)
        for _ in range(
            max(
                len(
                    day.invoices,
                ),
                len(
                    day.cash_movements,
                )
                + 2,
                len(
                    day.stock_movements,
                )
                + 2,
            )
            - 1,
        )
    ]
    rows[-1][-2] = _money(
        value=day.cash_after,
    )
    rows[-1][-1] = _money(
        value=day.balance_after,
    )
    for row, movement in zip(
        rows[1:],
        day.cash_movements,
        strict=False,
    ):
        row[-2] = _movement_cell(
            movement=movement,
            styles=styles,
        )
    for row, movement in zip(
        rows[1:],
        day.stock_movements,
        strict=False,
    ):
        row[-1] = _movement_cell(
            movement=movement,
            styles=styles,
        )
    for row, invoice in zip(
        rows,
        day.invoices,
        strict=False,
    ):
        row[1] = Paragraph(
            text=_escape(
                text=f"{invoice.supplier_name} №{invoice.invoice_number}",
            ),
            style=styles.cell,
        )
        row[2] = _money(
            value=invoice.cost_total,
        )
        row[3] = _money(
            value=invoice.paid,
        )
        row[4] = _money(
            value=invoice.retail_total,
        )
    return rows


def _movement_cell(
    movement: ReportMovement,
    styles: _Styles,
) -> Paragraph:
    amount = _money(
        value=movement.amount,
        signed=True,
    )
    label = MOVEMENT_LABELS[movement.kind]
    if movement.comment:
        label = f"{label} ({movement.comment})"
    label = _escape(
        text=label,
    )
    return Paragraph(
        text=(
            f'{amount}<br/><font size="{FONT_SIZE - 1}" color="{MUTED}">{label}</font>'
        ),
        style=styles.movement,
    )


def _debts_table(
    report: PeriodReport,
    styles: _Styles,
) -> Table:
    zero = Decimal(
        value=0,
    )
    rows: list[list[object]] = [
        list(
            DEBT_HEADER,
        ),
    ]
    for debt in report.debts:
        rows.append(
            [
                Paragraph(
                    text=_escape(
                        text=debt.supplier_name,
                    ),
                    style=styles.cell,
                ),
                Paragraph(
                    text=_escape(
                        text=debt.invoice_number,
                    ),
                    style=styles.cell,
                ),
                _full_date(
                    value=debt.invoice_date,
                )
                if debt.invoice_date
                else "",
                _money(
                    value=debt.cost_total,
                ),
                _money(
                    value=debt.paid,
                ),
                _money(
                    value=debt.debt,
                ),
            ],
        )
    rows.append(
        [
            "Итого",
            "",
            "",
            _money(
                value=sum(
                    (debt.cost_total for debt in report.debts),
                    start=zero,
                ),
            ),
            _money(
                value=sum(
                    (debt.paid for debt in report.debts),
                    start=zero,
                ),
            ),
            _money(
                value=sum(
                    (debt.debt for debt in report.debts),
                    start=zero,
                ),
            ),
        ],
    )
    table = Table(
        data=rows,
        colWidths=[width * mm for width in DEBT_WIDTHS],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        tblstyle=TableStyle(
            cmds=[
                ("FONT", (0, 0), (-1, -1), FONT, FONT_SIZE),
                ("FONT", (0, 0), (-1, 0), FONT_BOLD, FONT_SIZE),
                ("FONT", (0, -1), (-1, -1), FONT_BOLD, FONT_SIZE),
                ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                ("BACKGROUND", (0, -1), (-1, -1), SHADE),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, GRID),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ],
        ),
    )
    return table


def invoices_pdf_filename(invoices: list[PrintedInvoice]) -> str:
    if len(invoices) == 1:
        invoice = invoices[0]
        invoice_date = format_invoice_date(
            value=invoice.invoice_date,
        )
        return f"nakladnaya_{invoice_date}.pdf"
    return f"nakladnye_{len(invoices)}.pdf"


def invoices_pdf(invoices: list[PrintedInvoice]) -> bytes:
    """
    the invoices one after another on portrait pages, at the retail prices,
    every date starts on a page of its own, the invoices come sorted by date
    """
    _register_fonts()
    styles = _Styles()
    story: list[Flowable] = []
    for index, invoice in enumerate(
        invoices,
    ):
        if index and invoice.invoice_date != invoices[index - 1].invoice_date:
            story.append(
                PageBreak(),
            )
        elif index:
            story.append(
                Spacer(
                    width=0,
                    height=8 * mm,
                ),
            )
        supplier = _escape(
            text=invoice.supplier_name,
        )
        number = _escape(
            text=invoice.invoice_number,
        )
        invoice_date = _full_date(
            value=invoice.invoice_date,
        )
        # the supplier stands out, the number and the date follow in the regular weight
        title = (
            f'<font name="{FONT_BOLD}">{supplier}</font>'
            f"  ·  накладная №{number} от {invoice_date}"
        )
        # a short invoice is not torn between two pages, a long one breaks anyway
        story.append(
            KeepTogether(
                flowables=[
                    Paragraph(
                        text=title,
                        style=styles.invoice_title,
                    ),
                    Spacer(
                        width=0,
                        height=2 * mm,
                    ),
                    _invoice_table(
                        invoice=invoice,
                        styles=styles,
                    ),
                ],
            ),
        )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        filename=buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=12 * mm,
        title="Накладные",
    )
    page_number = partial(
        _page_number,
        page_width=A4[0],
    )
    document.build(
        flowables=story,
        onFirstPage=page_number,
        onLaterPages=page_number,
    )
    return buffer.getvalue()


def _invoice_table(
    invoice: PrintedInvoice,
    styles: _Styles,
) -> Table:
    rows: list[list[object]] = [
        list(
            INVOICE_HEADER,
        ),
    ]
    for line in invoice.lines:
        rows.append(
            [
                str(
                    line.line_no,
                ),
                Paragraph(
                    text=_escape(
                        text=line.name,
                    ),
                    style=styles.invoice_cell,
                ),
                _quantity(
                    value=line.quantity,
                ),
                Paragraph(
                    text=_escape(
                        text=line.unit or "",
                    ),
                    style=styles.invoice_unit,
                ),
                _money(
                    value=line.retail_price,
                ),
                _money(
                    value=line.retail_price_total,
                ),
            ],
        )
    rows.append(
        [
            "Итого в розничных ценах",
            *[""] * (len(INVOICE_HEADER) - 2),
            _money(
                value=invoice.retail_total,
            ),
        ],
    )
    table = Table(
        data=rows,
        colWidths=[width * mm for width in INVOICE_WIDTHS],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        tblstyle=TableStyle(
            cmds=[
                ("FONT", (0, 0), (-1, -1), FONT, INVOICE_FONT_SIZE),
                ("FONT", (0, 0), (-1, 0), FONT_BOLD, INVOICE_FONT_SIZE),
                ("FONT", (0, -1), (-1, -1), FONT_BOLD, INVOICE_FONT_SIZE),
                # light stripes keep the eye on the row across the wide name column
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, STRIPE]),
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_SHADE),
                ("BACKGROUND", (0, -1), (-1, -1), HEAD_SHADE),
                ("SPAN", (0, -1), (-2, -1)),
                ("ALIGN", (0, 1), (0, -2), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -2), "CENTER"),
                ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, -1), (-2, -1), "RIGHT"),
                # after the body, the header row is centered in both directions
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("LINEAFTER", (0, 0), (-2, -2), 0.3, GRID),
                ("LINEBELOW", (0, 1), (-1, -3), 0.3, GRID),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ],
        ),
    )
    return table


def _page_number(
    canvas: Canvas,
    _document: SimpleDocTemplate,
    page_width: float,
) -> None:
    canvas.saveState()
    canvas.setFont(
        psfontname=FONT,
        size=FONT_SIZE,
    )
    canvas.drawRightString(
        x=page_width - MARGIN,
        y=6 * mm,
        text=f"стр. {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def _register_fonts() -> None:
    registered = pdfmetrics.getRegisteredFontNames()
    for name, file in (
        (FONT, "DejaVuSans.ttf"),
        (FONT_BOLD, "DejaVuSans-Bold.ttf"),
    ):
        if name not in registered:
            pdfmetrics.registerFont(
                TTFont(
                    name=name,
                    filename=str(
                        FONT_DIR / file,
                    ),
                ),
            )


def _money(
    value: Decimal,
    signed: bool = False,
    blank_zero: bool = False,
) -> str:
    """12 400,50 with a no-break space between the thousands, the minus is a real minus"""
    if blank_zero and not value:
        return ""
    digits = f"{abs(value):,.2f}".replace(",", " ").replace(".", ",")
    if value < 0:
        return f"−{digits}"
    if signed and value > 0:
        return f"+{digits}"
    return digits


def _quantity(value: Decimal) -> str:
    """2, 1,5 or 0,125 without the trailing zeros"""
    return f"{value.normalize():f}".replace(".", ",")


def _short_date(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year % 100:02d}"


def _full_date(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"


def _escape(text: str) -> str:
    """a paragraph reads its text as markup"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
