from dataclasses import dataclass

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String)
    order_id = Column(Integer, ForeignKey("orders.id"))


@dataclass
class OrderRecord:
    id: int
    status: str
