from ..repositories.user_repository import UserRepository


class UserService:
    def __init__(self, repo: UserRepository | None = None):
        self.repo = repo or UserRepository()

    def find_all(self):
        return self.repo.find_all()
