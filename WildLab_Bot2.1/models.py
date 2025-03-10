from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class UserSettings(Base):
    __tablename__ = 'user_settings'

    user_id = Column(Integer, primary_key=True)
    wb_api_key = Column(String)
    notifications_enabled = Column(Boolean, default=False)
    auto_reply_enabled = Column(Boolean, default=False)
    auto_reply_five_stars = Column(Boolean, default=False)
    greeting = Column(String)
    farewell = Column(String)

    # Связь с отзывами
    reviews = relationship("Review", back_populates="user")


class Review(Base):
    __tablename__ = 'reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user_settings.user_id'))
    source_api_id = Column(String(50))  # ID из внешней системы
    stars = Column(Integer)
    comment = Column(Text)
    pros = Column(Text)
    cons = Column(Text)
    photo_url = Column(Text)
    response = Column(Text)
    is_answered = Column(Boolean, default=False)

    # Связь с пользователем
    user = relationship("UserSettings", back_populates="reviews")


# Инициализация базы данных
engine = create_engine('sqlite:///bot.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)