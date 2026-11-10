from fastapi import APIRouter, Depends

from app import schemas as s
from app.models import AppUser
from app.api.auth import user_out
from app.security import current_user_any

router = APIRouter()


@router.get("/me", response_model=s.UserOut)
def me(user: AppUser = Depends(current_user_any)):
    return user_out(user)   # raggiungibile anche con cambio password obbligatorio
