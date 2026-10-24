from typing import Any

from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestSimilarProduct(InvoiceApi):
    def upload_misread(self) -> dict[str, Any]:
        """the sugar misread by a letter, the second line is nothing the supplier has"""
        payload = invoice_payload()
        payload["items"][0]["name"] = "Сахар-песк 1 кг"
        payload["items"][1]["name"] = "Перец"
        return self.upload(
            payload=payload,
        )

    def similar_issues(
        self,
        draft: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            issue for issue in draft["issues"] if issue["code"] == "similar_product"
        ]

    def test_misread_name_suggests_the_product_as_a_warning(self) -> None:
        _, sugar, _ = self.known_supplier()
        # a close name at another supplier is not a candidate
        other = self.store.add_supplier(
            name="ИП Иванов",
            inn=None,
        )
        self.store.add_product(
            supplier=other,
            name="Перец молотый",
            markup_pct="10",
            retail_price="100",
        )

        draft = self.upload_misread()

        assert [line["similar"] for line in draft["lines"]] == [
            [{"id": sugar.id, "name": "Сахар-песок 1 кг", "similarity": 96}],
            [],
        ]
        assert self.similar_issues(
            draft=draft,
        ) == [
            {
                "line": 1,
                "message": "похож на товар «Сахар-песок 1 кг» (96%), проверьте, не он ли это",
                "blocking": False,
                "code": "similar_product",
            },
        ]
        # nothing is decided for the user, both lines are new until a price or a link is set
        assert self.blocking(
            draft=draft,
        ) == [
            (1, "новый товар, укажите розничную цену"),
            (2, "новый товар, укажите розничную цену"),
        ]

    def test_known_and_linked_lines_are_not_compared(self) -> None:
        _, _, salt = self.known_supplier()
        draft = self.upload()
        assert [line["similar"] for line in draft["lines"]] == [[], []]

        draft = self.upload_misread()
        form = draft["form"]
        form["lines"][0]["product_id"] = salt.id
        draft = self.save(
            draft=draft,
            form=form,
        )

        assert (
            draft["lines"][0]["similar"],
            self.similar_issues(
                draft=draft,
            ),
        ) == ([], [])

    def test_linking_the_suggestion_adds_the_spelling_when_posted(self) -> None:
        _, sugar, _ = self.known_supplier()
        draft = self.upload_misread()
        form = draft["form"]
        form["lines"][0]["product_id"] = draft["lines"][0]["similar"][0]["id"]
        form["lines"][1]["retail_price"] = 40
        self.save(
            draft=draft,
            form=form,
        )

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert (sugar.id, "сахар-песк 1 кг") in [
            (alias.product_id, alias.alias_normalized) for alias in self.store.aliases
        ]
