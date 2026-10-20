from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import pytest

from app.db.models import Base, User, StudySpace
from app.exam_diagnostics.models import ExamDiagnostic, ExamJob


def test_verified_identity_and_active_job_are_unique(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path/'models.db'))
    Base.metadata.create_all(engine)
    assert {'exam_diagnostics','exam_attachments','exam_questions','exam_jobs'} <= set(inspect(engine).get_table_names())
    with Session(engine) as db:
        db.add(User(id='u', username='u', password_hash='h'))
        db.flush()
        db.add(StudySpace(id='s', user_id='u', goal='g', init_key='s', request_digest='d'))
        db.flush()
        db.add(ExamDiagnostic(id='e1', user_id='u', space_id='s', request_key='k1', request_digest='d', name='test', verified_files_digest='a'))
        db.commit()
        db.add(ExamDiagnostic(id='e2', user_id='u', space_id='s', request_key='k2', request_digest='d', name='test', verified_files_digest='a'))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        db.add(ExamJob(id='j1', user_id='u', space_id='s', diagnostic_id='e1', request_key='j1', active_space_id='s'))
        db.commit()
        db.add(ExamJob(id='j2', user_id='u', space_id='s', diagnostic_id='e1', request_key='j2', active_space_id='s'))
        with pytest.raises(IntegrityError):
            db.flush()
    engine.dispose()
