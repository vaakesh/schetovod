"""black and white shelf tags on A4, ported from the cenniki-v2 skill script pricetags.py

the layout and the drawing follow the script one to one, a change here changes the printed tags
"""

import math
from dataclasses import dataclass
from functools import cache
from html import escape
from pathlib import Path
from threading import Lock
from typing import Any

import pymupdf
from fontTools.ttLib import TTFont

MM = 72 / 25.4
PAGE_W = 210 * MM
PAGE_H = 297 * MM
# sheet margins and the gap between blocks of different sizes, in mm
MARGIN = 7
TOP = 12
GAP = 4
SIZES = frozenset(
    {
        (40, 50),
        (50, 80),
        (60, 70),
        (70, 100),
    },
)
WEIGHTS = {
    "Regular": 400,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
    "ExtraBold": 800,
    "Black": 900,
}
BLACK = (0, 0, 0)
WHITE = (1, 1, 1)
BORDER = 0.9
HINT = "Печатать в масштабе 100% (без «подогнать под размер»). Резать по линиям."
FONT_DIR = (
    Path(
        __file__,
    ).parent
    / "fonts"
)

# MuPDF keeps global state and is not thread safe, one rendering at a time
RENDER_LOCK = Lock()


class PriceTagError(ValueError):
    """the tags cannot be printed, the message is for the user"""


@dataclass(frozen=True)
class PrintedTag:
    """the printed texts of one tag, sizes in mm"""

    width_mm: int
    height_mm: int
    # «ШТ.» or «ВЕС»
    left: str
    # the pack, may be empty
    right: str
    name: str
    sub: str
    # both empty leave the price block blank
    rub: str
    kop: str
    # «Производитель» or «Страна»
    foot_label: str
    foot: str

    def texts(self) -> tuple[str, ...]:
        return (
            self.left,
            self.right,
            self.name,
            self.sub,
            self.rub,
            self.kop,
            self.foot_label,
            self.foot,
        )


Placement = tuple[PrintedTag, float, float]
Box = tuple[float, float, float, float]


class Fonts:
    """the real Inter 4.0 faces and metrics, never a system substitute"""

    def __init__(
        self,
        directory: Path,
    ) -> None:
        self.directory = directory
        self.paths: dict[str, Path] = {}
        self.faces: dict[str, pymupdf.Font] = {}
        self.cap_heights: dict[str, float] = {}
        for weight, expected in WEIGHTS.items():
            path = directory / f"Inter-{weight}.ttf"
            with TTFont(
                file=path,
            ) as font:
                # fontTools fills the table fields at runtime, the stubs do not list them
                head: Any = font["head"]
                os2: Any = font["OS/2"]
                if (
                    font["name"].getDebugName(6) != f"Inter-{weight}"
                    or head.fontRevision != 4.0
                    or os2.usWeightClass != expected
                ):
                    raise RuntimeError(
                        f"{path.name}: требуется Inter 4.0, вес {expected}",
                    )
                # composite glyphs such as «т» break in some viewers
                if "glyf" not in font or any(
                    font["glyf"][glyph].isComposite() for glyph in font.getGlyphOrder()
                ):
                    raise RuntimeError(
                        f"{path.name}: нужен комплект с цельными контурами",
                    )
                self.cap_heights[weight] = os2.sCapHeight / head.unitsPerEm
            self.paths[weight] = path
            self.faces[weight] = pymupdf.Font(
                fontfile=str(
                    path,
                ),
            )
        self.archive = pymupdf.Archive(
            str(
                directory,
            ),
        )

    def width(
        self,
        text: str,
        weight: str,
        size: float = 1,
    ) -> float:
        return self.faces[weight].text_length(
            text=text,
            fontsize=size,
        )

    def check_text(
        self,
        tags: list[PrintedTag],
    ) -> None:
        characters = set(
            HINT + "руб.:",
        )
        for tag in tags:
            for text in tag.texts():
                characters.update(
                    text,
                )
        characters.difference_update(
            "\n\r\t",
        )
        for face in self.faces.values():
            missing = sorted(
                character
                for character in characters
                if not face.has_glyph(
                    chr=ord(
                        character,
                    ),
                )
            )
            if missing:
                raise PriceTagError(
                    f"Шрифт не умеет печатать символы {''.join(missing)!r}",
                )

    def line(
        self,
        page: pymupdf.Page,
        text: str,
        weight: str,
        size: float,
        box: Box,
        align: str = "center",
        color: tuple[float, float, float] = BLACK,
    ) -> None:
        """one line by the real metrics, smaller when it is too wide"""
        if not text:
            return
        x0, y0, x1, y1 = box
        width_at_one = self.width(
            text=text,
            weight=weight,
        )
        if width_at_one:
            size = min(
                size,
                (x1 - x0) / width_at_one,
            )
        if size < 3:
            raise PriceTagError(
                f"Слишком длинная строка: «{text}»",
            )
        width = width_at_one * size
        x = {
            "left": x0,
            "right": x1 - width,
            "center": x0 + (x1 - x0 - width) / 2,
        }[align]
        baseline = (y0 + y1 + self.cap_heights[weight] * size) / 2
        page.insert_text(
            point=(
                x,
                baseline,
            ),
            text=text,
            fontsize=size,
            fontname=f"Tag{weight}",
            fontfile=str(
                self.paths[weight],
            ),
            color=color,
        )


@cache
def get_fonts() -> Fonts:
    # the checks read six fonts, once per process is enough
    return Fonts(
        directory=FONT_DIR,
    )


class Paragraph:
    """the MuPDF Story engine wraps the text, keeps no-break spaces and fits the size"""

    def __init__(
        self,
        fonts: Fonts,
        text: str,
        weight: str,
        width: float,
        height: float,
        size: float,
        minimum: float,
        leading: float,
    ) -> None:
        self.document = pymupdf.open()
        self.page = self.document.new_page(
            width=width,
            height=height,
        )
        self.width = width
        self.height = height
        # a break is allowed after a hyphen, no-break spaces inside brands stay whole
        content = (
            escape(
                text,
            )
            .replace(
                "-",
                "-\u200b",
            )
            .replace(
                "\n",
                "<br>",
            )
        )
        # separate spans keep the unicode < and > through the contextual forms of Inter
        content = content.replace(
            "&lt;",
            "<span>&lt;</span>",
        ).replace(
            "&gt;",
            "<span>&gt;</span>",
        )
        css = f"""
            @font-face {{
                font-family: TagParagraph;
                src: url("Inter-{weight}.ttf");
            }}
            body {{ margin: 0; padding: 0; font-family: TagParagraph; }}
            p {{
                margin: 0; padding: 0; font-family: TagParagraph;
                font-weight: normal; font-style: normal;
                font-size: {size}pt; line-height: {leading};
                text-align: center; color: #000;
            }}
        """
        spare, self.scale = self.page.insert_htmlbox(
            rect=self.page.rect,
            text=f"<p>{content}</p>",
            css=css,
            archive=fonts.archive,
            scale_low=min(
                1,
                minimum / size,
            ),
        )
        if spare < 0:
            self.document.close()
            raise PriceTagError(
                f"Текст не помещается на ценник: «{text}»",
            )
        self.used_height = height - spare

    def paint(
        self,
        page: pymupdf.Page,
        x: float,
        y: float,
    ) -> None:
        page.show_pdf_page(
            rect=pymupdf.Rect(
                x0=x,
                y0=y,
                x1=x + self.width,
                y1=y + self.height,
            ),
            docsrc=self.document,
            pno=0,
        )

    def close(self) -> None:
        self.document.close()


def block(
    count: int,
    width: float,
    height: float,
    free_width: float,
    free_height: float,
) -> tuple[int, int] | None:
    """the columns and rows of a block of tags that fit a free rectangle"""
    cols = int(
        free_width // width,
    )
    rows = int(
        free_height // height,
    )
    if cols == 0 or rows == 0:
        return None
    if count >= cols * rows:
        return cols, rows
    # a wider and lower block leaves more room below
    rows_needed = -(-count // cols)
    cols_needed = (
        min(
            count,
            cols,
        )
        if rows_needed > 1
        else count
    )
    return cols_needed, rows_needed


def fill_page(
    queues: dict[tuple[int, int], list[PrintedTag]],
    order: list[tuple[int, int]],
    split: str,
) -> list[Placement]:
    """fills one sheet greedily, takes the tags out of the queues

    order lists the sizes from the larger to the smaller, split "h" leaves a strip as high as
    the block on the right and a full width strip below, "v" a full height strip on the right
    and a strip as wide as the block below, the positions are in mm from the top left corner
    """
    placed: list[Placement] = []
    free: list[Box] = [
        (
            MARGIN,
            TOP,
            PAGE_W / MM - 2 * MARGIN,
            PAGE_H / MM - TOP - MARGIN,
        ),
    ]
    while free:
        # top to bottom, left to right
        free.sort(
            key=lambda rect: (
                rect[1],
                rect[0],
            ),
        )
        fx, fy, fw, fh = free.pop(0)
        for size in order:
            count = len(
                queues[size],
            )
            if not count:
                continue
            w, h = size
            fitted = block(
                count=count,
                width=w,
                height=h,
                free_width=fw,
                free_height=fh,
            )
            if not fitted:
                continue
            cols, rows = fitted
            take = min(
                count,
                cols * rows,
            )
            for index in range(take):
                tag = queues[size].pop(0)
                placed.append(
                    (
                        tag,
                        fx + (index % cols) * w,
                        fy + (index // cols) * h,
                    ),
                )
            bw = cols * w
            bh = rows * h
            # the rest of an incomplete last row is free too
            last = take - (rows - 1) * cols
            if rows > 1 and last < cols:
                free.append(
                    (
                        fx + last * w + GAP,
                        fy + (rows - 1) * h + GAP,
                        (cols - last) * w - GAP,
                        h - GAP,
                    ),
                )
            if split == "h":
                free.append(
                    (
                        fx + bw + GAP,
                        fy,
                        fw - bw - GAP,
                        bh,
                    ),
                )
                free.append(
                    (
                        fx,
                        fy + bh + GAP,
                        fw,
                        fh - bh - GAP,
                    ),
                )
            else:
                free.append(
                    (
                        fx + bw + GAP,
                        fy,
                        fw - bw - GAP,
                        fh,
                    ),
                )
                free.append(
                    (
                        fx,
                        fy + bh + GAP,
                        bw,
                        fh - bh - GAP,
                    ),
                )
            free = [rect for rect in free if rect[2] > 0 and rect[3] > 0]
            break
    return placed


def layout(
    tags: list[PrintedTag],
) -> list[list[Placement]]:
    """saves paper: the largest tags go first as a tight block, smaller ones fill the rest

    every sheet tries several orders and both ways to split the free space,
    the variant that covers more of the sheet wins
    """
    queues: dict[tuple[int, int], list[PrintedTag]] = {}
    for tag in tags:
        queues.setdefault(
            (
                tag.width_mm,
                tag.height_mm,
            ),
            [],
        ).append(
            tag,
        )
    sizes = list(
        queues,
    )
    # larger tags by area always come before smaller ones
    orders = [
        sorted(
            sizes,
            key=lambda size: (
                size[0] * size[1],
                size[1],
            ),
            reverse=True,
        ),
        sorted(
            sizes,
            key=lambda size: (
                size[1],
                size[0],
            ),
            reverse=True,
        ),
        sorted(
            sizes,
            key=lambda size: (
                size[0],
                size[1],
            ),
            reverse=True,
        ),
    ]
    pages: list[list[Placement]] = []
    while any(
        queues.values(),
    ):
        best: (
            tuple[float, list[Placement], dict[tuple[int, int], list[PrintedTag]]]
            | None
        ) = None
        for order in orders:
            for split in ("h", "v"):
                trial = {size: list(queue) for size, queue in queues.items()}
                placed = fill_page(
                    queues=trial,
                    order=order,
                    split=split,
                )
                area = sum(tag.width_mm * tag.height_mm for tag, _, _ in placed)
                if best is None or area > best[0]:
                    best = (
                        area,
                        placed,
                        trial,
                    )
        if best is None or not best[1]:
            raise PriceTagError(
                "Ценник не помещается на лист A4",
            )
        _, placed, queues = best
        pages.append(
            placed,
        )
    return pages


def draw_title(
    page: pymupdf.Page,
    box: pymupdf.Rect,
    tag: PrintedTag,
    fonts: Fonts,
    k: float,
) -> None:
    name_block = None
    sub_block = None
    try:
        gap = 1 * MM if tag.sub else 0
        if tag.sub:
            sub_block = Paragraph(
                fonts=fonts,
                text=tag.sub,
                weight="Medium",
                width=box.width,
                height=box.height * 0.30,
                size=min(
                    tag.width_mm * 0.17,
                    8.5 * k,
                ),
                minimum=4.5,
                leading=1.15,
            )
        sub_height = sub_block.used_height if sub_block else 0
        name_width = box.width * 0.92
        name_block = Paragraph(
            fonts=fonts,
            text=tag.name,
            weight="ExtraBold",
            width=name_width,
            height=box.height - sub_height - gap,
            size=24 * k,
            minimum=5,
            leading=1.08,
        )
        total_height = name_block.used_height + sub_height + gap
        top = box.y0 + (box.height - total_height) / 2
        name_block.paint(
            page=page,
            x=box.x0 + (box.width - name_width) / 2,
            y=top,
        )
        if sub_block:
            sub_block.paint(
                page=page,
                x=box.x0,
                y=top + name_block.used_height + gap,
            )
    finally:
        if name_block:
            name_block.close()
        if sub_block:
            sub_block.close()


def draw_price(
    page: pymupdf.Page,
    box: pymupdf.Rect,
    tag: PrintedTag,
    fonts: Fonts,
) -> None:
    # both empty, the price is written by hand
    if tag.rub == "" and tag.kop == "":
        return
    kop_ratio = 0.375
    currency_ratio = 0.30
    gap_ratio = 0.06
    width_at_one = (
        fonts.width(
            text=tag.rub,
            weight="Black",
        )
        + gap_ratio
        + max(
            fonts.width(
                text=tag.kop,
                weight="Bold",
                size=kop_ratio,
            ),
            fonts.width(
                text="руб.",
                weight="SemiBold",
                size=currency_ratio,
            ),
        )
    )
    big = min(
        box.height * 0.95,
        box.width * 0.93 / width_at_one,
    )
    if big < 8:
        raise PriceTagError(
            f"Цена не помещается: {tag.rub},{tag.kop}",
        )
    cap = fonts.cap_heights["Black"] * big
    base = box.y0 + (box.height + cap) / 2
    x = box.x0 + (box.width - width_at_one * big) / 2

    def put(
        text: str,
        weight: str,
        size: float,
        origin: tuple[float, float],
    ) -> None:
        page.insert_text(
            point=origin,
            text=text,
            fontsize=size,
            fontname=f"Tag{weight}",
            fontfile=str(
                fonts.paths[weight],
            ),
            color=BLACK,
        )

    put(
        text=tag.rub,
        weight="Black",
        size=big,
        origin=(
            x,
            base,
        ),
    )
    side_x = (
        x
        + fonts.width(
            text=tag.rub,
            weight="Black",
            size=big,
        )
        + gap_ratio * big
    )
    kop_size = big * kop_ratio
    kop_base = base - cap + fonts.cap_heights["Bold"] * kop_size
    put(
        text=tag.kop,
        weight="Bold",
        size=kop_size,
        origin=(
            side_x,
            kop_base,
        ),
    )
    put(
        text="руб.",
        weight="SemiBold",
        size=big * currency_ratio,
        origin=(
            side_x,
            base,
        ),
    )


def draw_tag(
    page: pymupdf.Page,
    x: float,
    y: float,
    tag: PrintedTag,
    fonts: Fonts,
) -> pymupdf.Rect:
    wmm = tag.width_mm
    hmm = tag.height_mm
    rect = pymupdf.Rect(
        x0=x * MM,
        y0=y * MM,
        x1=(x + wmm) * MM,
        y1=(y + hmm) * MM,
    )
    pad = (
        max(
            2.2,
            wmm * 0.055,
        )
        * MM
    )
    k = max(
        0.7,
        math.sqrt(
            wmm * hmm / (50 * 80),
        ),
    )
    hh = (
        max(
            7,
            hmm * 0.12,
        )
        * MM
    )
    fh = (
        max(
            6.2,
            hmm * 0.11,
        )
        * MM
    )
    page.draw_rect(
        rect=rect,
        color=None,
        fill=WHITE,
    )
    header = pymupdf.Rect(
        x0=rect.x0,
        y0=rect.y0,
        x1=rect.x1,
        y1=rect.y0 + hh,
    )
    page.draw_rect(
        rect=header,
        color=None,
        fill=BLACK,
    )
    hs = min(
        hh * 0.42,
        9.5,
    )
    fonts.line(
        page=page,
        text=tag.left,
        weight="Bold",
        size=hs * 0.82,
        box=(
            rect.x0 + pad,
            header.y0,
            rect.x0 + rect.width / 2,
            header.y1,
        ),
        align="left",
        color=WHITE,
    )
    fonts.line(
        page=page,
        text=tag.right,
        weight="ExtraBold",
        size=hs * 1.05,
        box=(
            rect.x0 + rect.width / 2,
            header.y0,
            rect.x1 - pad,
            header.y1,
        ),
        align="right",
        color=WHITE,
    )
    footer_top = rect.y1 - fh
    page.draw_line(
        p1=(
            rect.x0,
            footer_top,
        ),
        p2=(
            rect.x1,
            footer_top,
        ),
        color=BLACK,
        width=BORDER,
    )
    label_size = min(
        fh * 0.26,
        6 * k,
    )
    value_size = min(
        fh * 0.40,
        9 * k,
    )
    fonts.line(
        page=page,
        text=f"{tag.foot_label}:",
        weight="Regular",
        size=label_size,
        box=(
            rect.x0 + pad,
            footer_top + 0.6,
            rect.x1 - pad,
            footer_top + fh * 0.48,
        ),
    )
    fonts.line(
        page=page,
        text=tag.foot,
        weight="Bold",
        size=value_size,
        box=(
            rect.x0 + pad,
            footer_top + fh * 0.48,
            rect.x1 - pad,
            rect.y1 - 0.9,
        ),
    )

    price_height = rect.height * 0.30
    price_bottom = footer_top - 2.4 * MM
    price_box = pymupdf.Rect(
        x0=rect.x0 + pad,
        y0=price_bottom - price_height,
        x1=rect.x1 - pad,
        y1=price_bottom,
    )
    draw_price(
        page=page,
        box=price_box,
        tag=tag,
        fonts=fonts,
    )
    divider_y = price_box.y0 - 0.8 * MM
    page.draw_line(
        p1=(
            rect.x0 + pad,
            divider_y,
        ),
        p2=(
            rect.x1 - pad,
            divider_y,
        ),
        color=BLACK,
        width=0.4,
        dashes="[1.2 1.6] 0",
    )
    title_box = pymupdf.Rect(
        x0=rect.x0 + pad,
        y0=header.y1 + 1.8 * MM,
        x1=rect.x1 - pad,
        y1=divider_y - 1.6 * MM,
    )
    if title_box.height <= 0:
        raise PriceTagError(
            f"Слишком маленький ценник: «{tag.name}»",
        )
    draw_title(
        page=page,
        box=title_box,
        tag=tag,
        fonts=fonts,
        k=k,
    )
    return rect


def price_tags_pdf(
    tags: list[PrintedTag],
) -> bytes:
    """all tags as one group, the layout saves paper across the sizes"""
    for tag in tags:
        if (tag.width_mm, tag.height_mm) not in SIZES:
            raise PriceTagError(
                f"Размер {tag.width_mm}×{tag.height_mm} мм не из списка: «{tag.name}»",
            )
    with RENDER_LOCK:
        fonts = get_fonts()
        fonts.check_text(
            tags=tags,
        )
        document = pymupdf.open()
        try:
            for placements in layout(
                tags=tags,
            ):
                page = document.new_page(
                    width=PAGE_W,
                    height=PAGE_H,
                )
                fonts.line(
                    page=page,
                    text=HINT,
                    weight="Regular",
                    size=7,
                    box=(
                        MARGIN * MM,
                        4.5 * MM,
                        (210 - MARGIN) * MM,
                        9 * MM,
                    ),
                    align="left",
                )
                frames = [
                    draw_tag(
                        page=page,
                        x=x,
                        y=y,
                        tag=tag,
                        fonts=fonts,
                    )
                    for tag, x, y in placements
                ]
                # the frames go last, a shared cutting line stays 0.9 pt thick
                frame = page.new_shape()
                for rect in frames:
                    frame.draw_rect(
                        rect=rect,
                    )
                frame.finish(
                    color=BLACK,
                    width=BORDER,
                    lineJoin=0,
                )
                frame.commit()
            document.set_metadata(
                m={
                    "title": "Ценники",
                    "creator": "Счетовод",
                    "producer": f"PyMuPDF {pymupdf.VersionBind}",
                },
            )
            document.subset_fonts()
            return document.tobytes(
                garbage=4,
                deflate=True,
            )
        finally:
            document.close()
