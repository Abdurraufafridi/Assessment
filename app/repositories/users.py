"""Repository for user records."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


class UserRepository:
    """Data-access operations for :class:`User`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: str) -> User | None:
        return self._session.get(User, user_id)

    def get_by_slack_user_id(self, slack_user_id: str) -> User | None:
        statement = select(User).where(User.slack_user_id == slack_user_id)
        return self._session.execute(statement).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> list[User]:
        statement = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        return list(self._session.execute(statement).scalars())

    def create(
        self,
        *,
        slack_user_id: str,
        display_name: str,
        email: str | None = None,
    ) -> User:
        user = User(
            slack_user_id=slack_user_id,
            display_name=display_name,
            email=email,
        )
        self._session.add(user)
        self._session.flush()
        return user

    def update(
        self,
        user: User,
        *,
        display_name: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if is_active is not None:
            user.is_active = is_active
        self._session.flush()
        return user

    def delete(self, user: User) -> None:
        self._session.delete(user)
