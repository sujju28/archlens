from fastapi import APIRouter, Depends
from .services.user_service import UserService

router = APIRouter()


@router.get("/users")
def list_users(service: UserService = Depends(UserService)):
    return service.find_all()
