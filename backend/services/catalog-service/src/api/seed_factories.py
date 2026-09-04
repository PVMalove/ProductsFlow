"""Детерминированный генератор демо-товаров для catalog-bootstrap (issue #208),
перенесённый из замороженного монолита `app/seed_factories.py` — те же
категории, прилагательные, существительные и `fake.seed_instance(42)`,
чтобы засеянный каталог был воспроизводим в разных окружениях."""

from dataclasses import dataclass

from faker import Faker

fake = Faker("ru_RU")

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

_DESCRIPTION_TAILS: list[str] = [
    "для повседневной жизни",
    "в современном дизайне",
    "с надёжной сборкой",
    "от ведущих производителей",
    "по выгодной цене",
]


@dataclass(frozen=True)
class ProductSeed:
    name: str
    category: str
    price: float
    description: str


def _generate_name(category: str) -> str:
    adjective: str = fake.random_element(_ADJECTIVES)
    noun: str = fake.random_element(_NOUNS_BY_CATEGORY[category])
    return f"{adjective} {noun}"


def _generate_description(name: str) -> str:
    tail: str = fake.random_element(_DESCRIPTION_TAILS)
    return f"{name} {tail}"


def generate_products(count: int = 100) -> list[ProductSeed]:
    # Пересеивается при каждом вызове, не только при импорте: делает вывод
    # детерминированным независимо от того, сколько раз общий `fake`-инстанс
    # этого модуля уже был использован в процессе (например, другими тестами).
    fake.seed_instance(42)
    seen_names: set[str] = set()
    products: list[ProductSeed] = []
    max_attempts = count * 20

    for _ in range(max_attempts):
        if len(products) >= count:
            break
        category = fake.random_element(CATEGORIES)
        name = _generate_name(category)
        if name in seen_names:
            continue
        seen_names.add(name)
        products.append(
            ProductSeed(
                name=name,
                category=category,
                price=float(fake.random_int(min=10, max=9999) * 10),
                description=_generate_description(name),
            )
        )

    if len(products) < count:
        max_unique = sum(len(n) for n in _NOUNS_BY_CATEGORY.values()) * len(_ADJECTIVES)
        raise RuntimeError(
            f"generate_products: could not generate {count} unique names — only "
            f"{max_unique} adjective/noun combinations exist "
            f"(got {len(products)} within {max_attempts} attempts)"
        )

    return products
