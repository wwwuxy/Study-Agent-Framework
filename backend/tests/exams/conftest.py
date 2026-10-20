import io
from types import SimpleNamespace

import pytest
from PIL import Image



@pytest.fixture
def image_bytes():
    stream = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(stream, format='PNG')
    return stream.getvalue()


@pytest.fixture
def pdf_bytes():
    from app.providers.probe_pdf import make_probe_pdf
    return make_probe_pdf('teacher-mark-fixture')


@pytest.fixture
def exam_env(client):
    assert client.post("/api/v1/auth/register", json={"username":"alice", "password":"strong-password-2026"}).status_code == 201
    response = client.post('/api/v1/providers', json={
        'name': '试卷演示', 'provider_type': 'fake_files', 'chat_model': 'demo-model', 'api_key': 'demo-secret'})
    provider_id = response.json()['id']
    assert client.post(f'/api/v1/providers/{provider_id}/test').status_code == 200
    response = client.post('/api/v1/study-spaces', json={'provider_id':provider_id, 'goal':'学习操作系统', 'idempotency_key':'exam-space'})
    assert response.status_code == 201, response.text
    sid = response.json()['id']
    with client.app.state.session_factory() as db:
        from app.db.models import KnowledgeConcept
        keys = [c.key for c in db.query(KnowledgeConcept).filter_by(space_id=sid)]
    return SimpleNamespace(client=client, app=client.app, space_id=sid,
                           provider_id=provider_id, concepts=keys, root=f'/api/v1/study-spaces/{sid}/exam-diagnostics')


@pytest.fixture
def recognition_payload(exam_env):
    return {'title':'期中测试', 'coverage_complete':True, 'coverage_note':'',
            'stated_score':5, 'stated_max_score':10, 'questions':[
                {'key':'q1','number':'1','source_id':'a1','prompt':'操作系统的职责？',
                 'student_answer':'管理资源','teacher_marks':'✓ 5/5','teacher_mark_clear':True,
                 'teacher_result':'correct','result':'correct','score':5,'max_score':5,
                 'recognition_confidence':'high','mapping_confidence':'high','concept_ids':[exam_env.concepts[0]]},
                {'key':'q2','number':'2','source_id':'a1','prompt':'说明资源管理',
                 'student_answer':'不知道','teacher_marks':'× 0/5','teacher_mark_clear':True,
                 'teacher_result':'incorrect','result':'incorrect','score':0,'max_score':5,
                 'recognition_confidence':'high','mapping_confidence':'high','concept_ids':[exam_env.concepts[0]]}
            ]}
