from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str]
    price: Mapped[float]
    description: Mapped[str] = mapped_column(default="", server_default="")
