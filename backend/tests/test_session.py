from sqlalchemy import text

from market_desk.db.session import get_session


def test_get_session_yields_a_working_session_and_closes_it() -> None:
    """Needs Postgres running. Drives the dependency the way FastAPI does."""
    dependency = get_session()
    session = next(dependency)  # FastAPI runs the code up to `yield`

    assert session.execute(text("SELECT 1")).scalar_one() == 1
    assert session.in_transaction()  # SQLAlchemy opened a transaction implicitly

    # FastAPI resumes the generator after the response; the `with` block closes the session
    for _ in dependency:
        pass
    assert not session.in_transaction()
