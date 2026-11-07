import json
from decimal import Decimal
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

from core.enums import PriceTagOrigin, PriceTagUnit
from price_tags.import_tags import read_tags
from price_tags.pdf import PriceTagError, PrintedTag, layout, price_tags_pdf
from price_tags.schemas import GeneralTag, PriceTagFields
from price_tags.service import general_tag_fields, price_tag_key
from tests.fakes import FakeStore

NBSP = chr(0xA0)


def row(**changes: Any) -> dict[str, Any]:
    """a form row as the page sends it"""
    return {
        "width_mm": 50,
        "height_mm": 80,
        "unit": "piece",
        "pack": "500 г",
        "name": "Масло сливочное традиционное",
        "subtitle": "м.д.ж. 82,5%",
        "price": "380.00",
        "origin": "country",
        "origin_name": "Россия",
        "quantity": 1,
        **changes,
    }


def fields(**changes: Any) -> PriceTagFields:
    values = row(
        **changes,
    )
    del values["quantity"]
    # json mode, the same strict parsing as a request
    return PriceTagFields.model_validate_json(
        json_data=json.dumps(
            obj=values,
        ),
    )


def printed(
    width_mm: int,
    height_mm: int,
    name: str = "Пломбир «Отборный»",
) -> PrintedTag:
    return PrintedTag(
        width_mm=width_mm,
        height_mm=height_mm,
        left="ШТ.",
        right="90 г",
        name=name,
        sub="ванильный, в" + NBSP + "вафельном стаканчике",
        rub="100",
        kop="00",
        foot_label="Производитель",
        foot="Полярис",
    )


class TestKey:
    def test_case_and_spaces_make_the_same_tag(self) -> None:
        assert price_tag_key(
            tag=fields(),
        ) == price_tag_key(
            tag=fields(
                name="МАСЛО  сливочное\nтрадиционное",
                subtitle="м.д.ж." + NBSP + "82,5%",
            ),
        )

    @pytest.mark.parametrize(
        argnames="change",
        argvalues=[
            {"price": "390.00"},
            {"price": None},
            {"pack": "180 г"},
            {"width_mm": 40, "height_mm": 50},
            {"unit": "weight"},
            {"origin": "maker"},
        ],
    )
    def test_another_printed_field_makes_another_tag(
        self,
        change: dict[str, Any],
    ) -> None:
        assert price_tag_key(
            tag=fields(),
        ) != price_tag_key(
            tag=fields(
                **change,
            ),
        )


class TestImport:
    def test_empty_fields_of_general_json_become_none(self) -> None:
        tag = general_tag_fields(
            tag=GeneralTag(
                w=40,
                h=50,
                left="ВЕС",
                right="",
                name="Сельдь",
                sub="",
                rub="",
                kop="",
                foot_label="Производитель",
                foot="Мурманск",
            ),
        )

        assert tag.unit == PriceTagUnit.WEIGHT
        assert tag.origin == PriceTagOrigin.MAKER
        assert tag.pack is None
        assert tag.subtitle is None
        assert tag.price is None

    def test_rubles_and_kopecks_make_one_price(self) -> None:
        tag = general_tag_fields(
            tag=GeneralTag(
                w=70,
                h=100,
                left="ШТ.",
                right="1 л",
                name="Молоко",
                rub="89",
                kop="5",
                foot_label="Страна",
                foot="Россия",
            ),
        )

        assert tag.price == Decimal(
            value="89.05",
        )

    def test_a_custom_size_stops_the_import(self) -> None:
        with pytest.raises(
            expected_exception=SystemExit,
        ):
            read_tags(
                text='[{"w": 30, "h": 40, "left": "ШТ.", "right": "", "name": "Тест",'
                ' "sub": "", "rub": "1", "kop": "00", "foot_label": "Страна",'
                ' "foot": "Россия", "custom": true}]',
            )


class TestPdf:
    def test_the_skill_example_takes_two_sheets(self) -> None:
        tags = (
            [
                printed(
                    width_mm=70,
                    height_mm=100,
                ),
            ]
            * 5
            + [
                printed(
                    width_mm=50,
                    height_mm=80,
                ),
            ]
            * 2
            + [
                printed(
                    width_mm=40,
                    height_mm=50,
                ),
            ]
            * 2
            + [
                printed(
                    width_mm=60,
                    height_mm=70,
                ),
            ]
        )

        assert (
            len(
                layout(
                    tags=tags,
                ),
            )
            == 2
        )
        document = pymupdf.open(
            stream=price_tags_pdf(
                tags=tags,
            ),
            filetype="pdf",
        )
        assert document.page_count == 2
        assert "Пломбир" in document[0].get_text()

    def test_a_name_that_does_not_fit_is_refused(self) -> None:
        with pytest.raises(
            expected_exception=PriceTagError,
        ):
            price_tags_pdf(
                tags=[
                    printed(
                        width_mm=40,
                        height_mm=50,
                        name="Очень длинное название " * 20,
                    ),
                ],
            )


class TestApi:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        store: FakeStore,
        client: TestClient,
    ) -> None:
        self.store = store
        self.client = client

    def print_rows(
        self,
        *rows: dict[str, Any],
    ) -> Any:
        return self.client.post(
            url="/price-tags/print.pdf",
            json={
                "rows": list(
                    rows,
                ),
            },
        )

    def test_printing_remembers_only_new_tags(self) -> None:
        response = self.print_rows(
            row(
                quantity=3,
            ),
            row(
                name="МАСЛО СЛИВОЧНОЕ ТРАДИЦИОННОЕ",
            ),
            row(
                price=None,
                pack="",
                subtitle="  ",
            ),
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        document = pymupdf.open(
            stream=response.content,
            filetype="pdf",
        )
        assert document[0].get_text().count("Россия") == 5
        assert [
            (tag.price, tag.pack, tag.subtitle) for tag in self.store.price_tags
        ] == [
            (
                Decimal(
                    value="380.00",
                ),
                "500 г",
                "м.д.ж. 82,5%",
            ),
            (
                None,
                None,
                None,
            ),
        ]
        assert self.store.commits == 1

        again = self.print_rows(
            row(),
        )

        assert again.status_code == 200
        assert len(self.store.price_tags) == 2

    @pytest.mark.parametrize(
        argnames="change",
        argvalues=[
            {"width_mm": 30},
            {"name": " "},
            {"origin_name": ""},
            {"price": "-1"},
            {"price": "1.005"},
            {"quantity": 0},
            {"quantity": 101},
        ],
    )
    def test_a_bad_row_is_refused(
        self,
        change: dict[str, Any],
    ) -> None:
        response = self.print_rows(
            row(
                **change,
            ),
        )

        assert response.status_code == 422
        assert self.store.price_tags == []

    def test_a_tag_that_does_not_print_is_not_saved(self) -> None:
        response = self.print_rows(
            row(
                width_mm=40,
                height_mm=50,
                # under the length limit of the form, but too long for the small tag
                subtitle="м.д.ж. 82,5% " * 12,
            ),
        )

        assert response.status_code == 422
        assert "не помещается" in response.json()["detail"]
        assert self.store.price_tags == []

    def test_search_finds_every_word_in_name_and_subtitle(self) -> None:
        self.print_rows(
            row(),
            row(
                name="Сыр «Аристократ»",
                subtitle="на" + NBSP + "топлёном молоке",
                price="1255.00",
            ),
        )

        response = self.client.get(
            url="/price-tags",
            params={
                "q": "сыр на топлёном",
            },
        )

        assert response.status_code == 200
        found = response.json()
        assert [tag["name"] for tag in found] == [
            "Сыр «Аристократ»",
        ]
        assert found[0]["price"] == "1255.00"
        assert "dedup_key" not in found[0]

    def test_an_empty_search_finds_nothing(self) -> None:
        self.print_rows(
            row(),
        )

        response = self.client.get(
            url="/price-tags",
            params={
                "q": "  ",
            },
        )

        assert response.json() == []


def fields_payload(**changes: Any) -> dict[str, Any]:
    """the body of an edit, a form row without the copies"""
    values = row(
        **changes,
    )
    del values["quantity"]
    return values


class TestManage:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        store: FakeStore,
        client: TestClient,
    ) -> None:
        self.store = store
        self.client = client
        response = client.post(
            url="/price-tags/print.pdf",
            json={
                "rows": [
                    row(),
                    row(
                        name="Сыр «Аристократ»",
                        price="1255.00",
                    ),
                ],
            },
        )
        assert response.status_code == 200, response.text
        self.butter, self.cheese = store.price_tags

    def test_the_whole_base_is_listed_by_name(self) -> None:
        response = self.client.get(
            url="/price-tags/all",
        )

        assert response.status_code == 200
        assert [tag["name"] for tag in response.json()] == [
            "Масло сливочное традиционное",
            "Сыр «Аристократ»",
        ]
        assert response.json()[0]["created_at"]

    def test_an_edit_changes_the_fields_and_the_key(self) -> None:
        old_key = self.butter.dedup_key

        response = self.client.put(
            url=f"/price-tags/{self.butter.id}",
            json=fields_payload(
                price="399.00",
                subtitle="",
            ),
        )

        assert response.status_code == 200, response.text
        assert response.json()["price"] == "399.00"
        assert self.butter.price == Decimal(
            value="399.00",
        )
        assert self.butter.subtitle is None
        assert self.butter.dedup_key != old_key
        # the old variant is free again, a print with it adds a new tag
        self.client.post(
            url="/price-tags/print.pdf",
            json={
                "rows": [
                    row(),
                ],
            },
        )
        assert len(self.store.price_tags) == 3

    def test_an_edit_into_another_tag_is_refused(self) -> None:
        response = self.client.put(
            url=f"/price-tags/{self.cheese.id}",
            json=fields_payload(
                name="масло  сливочное традиционное",
            ),
        )

        assert response.status_code == 409
        assert self.cheese.name == "Сыр «Аристократ»"

    def test_an_edit_that_does_not_print_is_refused(self) -> None:
        response = self.client.put(
            url=f"/price-tags/{self.butter.id}",
            json=fields_payload(
                width_mm=40,
                height_mm=50,
                subtitle="м.д.ж. 82,5% " * 12,
            ),
        )

        assert response.status_code == 422
        assert self.butter.width_mm == 50

    def test_a_tag_is_deleted(self) -> None:
        response = self.client.delete(
            url=f"/price-tags/{self.cheese.id}",
        )

        assert response.status_code == 204
        assert self.store.price_tags == [
            self.butter,
        ]

    @pytest.mark.parametrize(
        argnames="method",
        argvalues=[
            "PUT",
            "DELETE",
        ],
    )
    def test_a_missing_tag_is_not_found(
        self,
        method: str,
    ) -> None:
        response = self.client.request(
            method=method,
            url="/price-tags/999",
            json=fields_payload() if method == "PUT" else None,
        )

        assert response.status_code == 404
