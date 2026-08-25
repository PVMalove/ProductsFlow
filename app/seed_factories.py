from typing import Any

from faker import Faker

fake = Faker("ru_RU")
fake.seed_instance(42)

CATEGORIES: list[str] = [
    "Электроника",
    "Бытовая техника",
    "Книги",
    "Одежда",
    "Спорт",
    "Дом и сад",
]

_NOUNS_BY_CATEGORY: dict[str, list[str]] = {
    "Электроника": [
        "ноутбук",
        "смартфон",
        "планшет",
        "наушники",
        "монитор",
        "клавиатура",
    ],
    "Бытовая техника": ["чайник", "кофеварка", "тостер", "утюг", "пылесос", "блендер"],
    "Книги": [
        "роман",
        "словарь",
        "учебник",
        "справочник",
        "сборник рассказов",
        "путеводитель",
    ],
    "Одежда": ["футболка", "куртка", "джинсы", "свитер", "рубашка", "кепка"],
    "Спорт": ["мяч", "гантели", "коврик", "велосипед", "ракетка", "скакалка"],
    "Дом и сад": ["лейка", "табурет", "лампа", "ваза", "кашпо", "стремянка"],
}

_ADJECTIVES: list[str] = [
    "Беспроводной",
    "Компактный",
    "Удобный",
    "Стильный",
    "Лёгкий",
    "Прочный",
    "Современный",
    "Универсальный",
    "Надёжный",
    "Практичный",
]


def _generate_name(category: str) -> str:
    adjective: str = fake.random_element(_ADJECTIVES)
    noun: str = fake.random_element(_NOUNS_BY_CATEGORY[category])
    return f"{adjective} {noun}"


_DESCRIPTION_TAILS: list[str] = [
    "для повседневной жизни",
    "в современном дизайне",
    "с надёжной сборкой",
    "от ведущих производителей",
    "по выгодной цене",
]


def _generate_description(name: str) -> str:
    tail: str = fake.random_element(_DESCRIPTION_TAILS)
    return f"{name} {tail}"


def generate_products(count: int = 100) -> list[dict[str, Any]]:
    seen_names: set[str] = set()
    products: list[dict[str, Any]] = []
    max_attempts = count * 20

    for _ in range(max_attempts):
        if len(products) >= count:
            break
        category: str = fake.random_element(CATEGORIES)
        name = _generate_name(category)
        if name in seen_names:
            continue
        seen_names.add(name)
        products.append(
            {
                "name": name,
                "category": category,
                "price": float(fake.random_int(min=10, max=9999) * 10),
                "description": _generate_description(name),
            }
        )

    return products
