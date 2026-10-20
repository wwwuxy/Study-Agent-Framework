import pytest
from pydantic import ValidationError

from app.schemas.exams import ExamCreate, ExamRecognition, RecognizedQuestion


def manifest(count=1, mime='image/png'):
    return {'idempotency_key': 'exam-1', 'name': '期中试卷', 'attachments': [
        {'client_id': str(i), 'filename': f'{i}.png', 'mime_type': mime,
         'size_bytes': 100, 'sha256': 'a'*64} for i in range(count)]}


def test_manifest_and_scores_are_bounded():
    assert len(ExamCreate.model_validate(manifest(20)).attachments) == 20
    with pytest.raises(ValidationError):
        ExamCreate.model_validate(manifest(21))
    data = manifest(2)
    data['attachments'][0].update(filename='a.pdf', mime_type='application/pdf')
    with pytest.raises(ValidationError):
        ExamCreate.model_validate(data)


@pytest.mark.parametrize('score', [float('nan'), float('inf'), True, -1, 11])
def test_scores_reject_invalid_numbers(score):
    with pytest.raises(ValidationError):
        RecognizedQuestion(key='q1', number='1', source_id='a1', score=score, max_score=10)


def test_question_text_and_count_are_bounded():
    with pytest.raises(ValidationError):
        RecognizedQuestion(key='q1', number='1', source_id='a1', prompt='x'*12001)
    q = {'key':'q1', 'number':'1', 'source_id':'a1'}
    with pytest.raises(ValidationError):
        ExamRecognition(questions=[q]*201)
