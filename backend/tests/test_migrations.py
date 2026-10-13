from alembic import command
from alembic.config import Config


def test_alembic_stairway() -> None:
    alembic_cfg = Config("")
    alembic_cfg.set_main_option("script_location", "market_desk:db:migrations")
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
