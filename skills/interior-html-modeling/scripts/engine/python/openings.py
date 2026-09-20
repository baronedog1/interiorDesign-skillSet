"""Opening facts are compiled by the shared browser/Node model kernel."""
from kernel import evaluate

def resolve_openings(layout):
    return evaluate(layout,'openings')
