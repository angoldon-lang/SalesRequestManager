from fastapi import APIRouter, Depends

from app import schemas as s
from app.models import AppUser
from app.security import current_user

router = APIRouter()


@router.get("/me", response_model=s.UserOut)
def me(user: AppUser = Depends(current_user)):
    return user
