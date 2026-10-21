from fastapi import APIRouter, Depends, Request

from app.api.deps import current_user, get_db, own_space
from app.db.models import utcnow
from app.reviews.sessions import get_review, list_reviews, start_review
from app.schemas.adaptive import ReviewStart
from app.schemas.api import AttemptSubmit
from app.teaching.attempts import submit_attempt

router = APIRouter(prefix="/study-spaces/{space_id}/reviews", tags=["reviews"])


@router.get("")
async def listing(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    return list_reviews(db, own_space(db, user.id, space_id), utcnow())


@router.post("/start", status_code=201)
async def start(
    space_id: str, body: ReviewStart, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    return await start_review(request, db, own_space(db, user.id, space_id), body)


@router.get("/{review_id}")
async def show(space_id: str, review_id: str, db=Depends(get_db), user=Depends(current_user)):
    return get_review(db, own_space(db, user.id, space_id), review_id)


@router.post("/{review_id}/submit", status_code=201)
async def submit(
    space_id: str,
    review_id: str,
    body: AttemptSubmit,
    request: Request,
    db=Depends(get_db),
    user=Depends(current_user),
):
    return await submit_attempt(
        request, db, own_space(db, user.id, space_id), body, expected_review_id=review_id
    )
