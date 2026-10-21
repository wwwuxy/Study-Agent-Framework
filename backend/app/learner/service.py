from app.learner.bkt import estimate_bkt
from app.learner.evidence import observations_for
from app.learner.parameters import BKTParameters


def compute_states(concepts: list[dict], events: list[dict], params=None) -> dict:
    """Pure CPU boundary: no Session or shared mutable model enters the worker."""
    params = params or BKTParameters()
    return {c["key"]: estimate_bkt(observations_for(c["key"], events), params) for c in concepts}
