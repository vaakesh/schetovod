import re
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

RUBLE = Decimal(
    value=1,
)
KOPECK = Decimal(
    value="0.01",
)
# the limit of products.markup_pct
MAX_MARKUP_PCT = Decimal(
    value="999.99",
)
# a misprint or a misread letter stays above it, a different word usually falls below,
# a different volume or fat content does not, so the user decides
SIMILAR_NAME_RATIO = 0.9

_QUOTES = re.compile(
    pattern=r"[\"'«»“”„`]",
)
_SPACES_AROUND_PUNCT = re.compile(
    pattern=r"\s*([.,;:()/%-])\s*",
)
_SPACES = re.compile(
    pattern=r"\s+",
)


def normalize_name(name: str) -> str:
    """lookup key for a product: the same name spelled differently"""
    key = name.lower().replace(
        "ё",
        "е",
    )
    key = _QUOTES.sub(
        repl=" ",
        string=key,
    )
    key = _SPACES_AROUND_PUNCT.sub(
        repl=r"\1",
        string=key,
    )
    return _SPACES.sub(
        repl=" ",
        string=key,
    ).strip()


def name_similarity(
    key: str,
    other: str,
) -> float:
    """share of matching characters of two normalized names, from 0 to 1"""
    return SequenceMatcher(
        isjunk=None,
        a=key,
        b=other,
        # the heuristic drops frequent characters of long strings and skews the ratio
        autojunk=False,
    ).ratio()


def retail_price(
    cost_price: Decimal,
    markup_pct: Decimal,
) -> Decimal:
    """marked-up price rounded to rubles, half up"""
    return (cost_price * (1 + markup_pct / 100)).quantize(
        RUBLE,
        rounding=ROUND_HALF_UP,
    )


def markup_for_price(
    cost_price: Decimal,
    price: Decimal,
) -> Decimal:
    """markup percent that turns the purchase price into the given price"""
    return ((price / cost_price - 1) * 100).quantize(
        KOPECK,
        rounding=ROUND_HALF_UP,
    )


def revaluation_amount(
    quantity: Decimal,
    old_price: Decimal,
    new_price: Decimal,
) -> Decimal:
    """how the stock at retail prices changes when the shelf gets the new price"""
    return (quantity * (new_price - old_price)).quantize(
        KOPECK,
        rounding=ROUND_HALF_UP,
    )


def retail_price_total(
    retail_price: Decimal,
    quantity: Decimal,
) -> Decimal:
    """line total at the marked-up price"""
    return (retail_price * quantity).quantize(
        KOPECK,
        rounding=ROUND_HALF_UP,
    )
