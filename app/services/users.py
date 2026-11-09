"""User application services."""

from sqlalchemy.orm import Session

from app.db.models.user import User
from app.domain.errors import EntityNotFoundError, ReferenceConsistencyError
from app.repositories.users import UserRepository


class UserService:
    """Create and maintain user records."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)

    def get_user(self, user_id: str) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise EntityNotFoundError(f"User '{user_id}' does not exist")
        return user

    def create_user(
        self,
        *,
        slack_user_id: str,
        display_name: str,
        email: str | None = None,
    ) -> User:
        slack_id = slack_user_id.strip()
        name = display_name.strip()
        if not slack_id:
            raise ReferenceConsistencyError("slack_user_id must not be blank")
        if not name:
            raise ReferenceConsistencyError("display_name must not be blank")
        return self._users.create(
            slack_user_id=slack_id,
            display_name=name,
            email=self._normalise_email(email),
        )

    def get_or_create(
        self,
        *,
        slack_user_id: str,
        display_name: str,
        email: str | None = None,
    ) -> User:
        existing = self._users.get_by_slack_user_id(slack_user_id.strip())
        if existing is None:
            return self.create_user(
                slack_user_id=slack_user_id,
                display_name=display_name,
                email=email,
            )
        updates: dict[str, object] = {}
        if existing.display_name != display_name.strip():
            updates["display_name"] = display_name.strip()
        normalised_email = self._normalise_email(email)
        if normalised_email is not None and existing.email != normalised_email:
            updates["email"] = normalised_email
        if updates:
            self._users.update(existing, **updates)  # type: ignore[arg-type]
        return existing

    @staticmethod
    def _normalise_email(email: str | None) -> str | None:
        if email is None:
            return None
        normalised = email.strip().lower()
        return normalised or None
