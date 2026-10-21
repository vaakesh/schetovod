from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from enums import LedgerKind
from schemas import PeriodReport, ReportDay, format_invoice_date

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

CASH_LABELS = {
    LedgerKind.CASH_IN: "внесение",
    LedgerKind.CASH_OUT: "выдача",
    LedgerKind.CASH_COUNT: "сверка",
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
    "Внес./выд.",
    "Касса",
    "Товар",
)
# the column of the cash ins and outs, its notes read from the left
CASH_MOVES_COLUMN = 8
# one value a day, the other columns have a row for each invoice or cash note
DAY_COLUMNS = (0, 5, 6, 7, 9, 10)
# millimetres, the frame of the landscape page is about 272 wide inside its padding
WIDTHS = (15, 44, 22, 22, 22, 22, 22, 22, 36, 22, 22)
DEBT_HEADER = (
    "Фирма",
    "№",
    "Дата",
    "Закупка",
    "Оплачено",
    "Долг",
)
DEBT_WIDTHS = (70, 30, 22, 26, 26, 26)


def report_pdf_filename(report: PeriodReport) -> str:
    date_from = format_invoice_date(
        value=report.date_from,
    )
    date_to = format_invoice_date(
        value=report.date_to,
    )
    return f"otchet_{date_from}_{date_to}.pdf"


def report_pdf(report: PeriodReport) -> bytes:
    """one row a day with the invoices of the day under it, then the debts to the suppliers"""
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
                "Касса и Товар — остатки на конец дня, Приход и Товар — в розничных ценах, "
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
    document.build(
        flowables=story,
        onFirstPage=_page_number,
        onLaterPages=_page_number,
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
                value=sum(
                    (day.cash_moves for day in report.days),
                    start=zero,
                ),
                signed=True,
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
        ("FONT", (0, total), (-1, total), FONT_BOLD, FONT_SIZE),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("BACKGROUND", (0, 1), (-1, 1), SHADE),
        ("BACKGROUND", (0, total), (-1, total), SHADE),
        ("SPAN", (0, 1), (CASH_MOVES_COLUMN, 1)),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (CASH_MOVES_COLUMN, 0), (CASH_MOVES_COLUMN, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEABOVE", (0, total), (-1, total), 0.6, colors.black),
        ("LINEAFTER", (0, 0), (-2, -1), 0.3, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (CASH_MOVES_COLUMN, 0), (CASH_MOVES_COLUMN, -1), 5),
    ]
    for start, end in day_spans:
        commands.append(
            ("LINEABOVE", (0, start), (-1, start), 0.3, GRID),
        )
        # the day totals stand beside all the invoices of the day
        if end > start:
            for column in DAY_COLUMNS:
                commands.append(
                    ("SPAN", (column, start), (column, end)),
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
    """the day totals go on the first row, the invoices and the cash notes each on a row of their own,
    a tall cell spanning the day would stretch every row of it"""
    rows: list[list[object]] = [
        [
            _short_date(
                value=day.day,
            ),
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
                value=day.cash_moves,
                signed=True,
                blank_zero=not day.cash_notes,
            ),
            _money(
                value=day.cash_after,
            ),
            _money(
                value=day.balance_after,
            ),
        ],
    ]
    # the notes start under the sum of the day
    rows += [
        [""] * len(HEADER)
        for _ in range(
            max(
                len(day.invoices),
                len(day.cash_notes) + 1,
            )
            - 1,
        )
    ]
    for row, note in zip(
        rows[1:],
        day.cash_notes,
        strict=False,
    ):
        text = f"{CASH_LABELS[note.kind]} {_money(value=note.cash, signed=True)}"
        if note.comment:
            text = f"{text}: {note.comment}"
        row[CASH_MOVES_COLUMN] = Paragraph(
            text=_escape(
                text=text,
            ),
            style=styles.note,
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


def _page_number(
    canvas: Canvas,
    _document: SimpleDocTemplate,
) -> None:
    canvas.saveState()
    canvas.setFont(
        psfontname=FONT,
        size=FONT_SIZE,
    )
    canvas.drawRightString(
        x=PAGE_SIZE[0] - MARGIN,
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


def _short_date(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year % 100:02d}"


def _full_date(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"


def _escape(text: str) -> str:
    """a paragraph reads its text as markup"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
