from datetime import UTC, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from scout import cli
from scout.db import repo
from scout.seeds import seed_all

pytestmark = pytest.mark.db
runner = CliRunner()


@pytest.fixture(autouse=True)
def _wire(db_session, db_engine, settings, monkeypatch):
    from scout.db.base import make_session_factory

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "session_factory", lambda s: make_session_factory(db_engine))
    yield


def test_cli_seed_add_task_and_status(db_session):
    assert runner.invoke(cli.app, ["seed"]).exit_code == 0
    out = runner.invoke(cli.app, ["add-task", "map-sector", "--sector", "pets"])
    assert out.exit_code == 0 and "queued task #" in out.stdout
    assert repo.queued_tasks(db_session)[0].payload == {
        "sector": "pets",
        "sector_name": "Pets (vets, sitting, supplies)",
        "founder": True,
    }
    assert runner.invoke(cli.app, ["add-task", "bogus"]).exit_code != 0
    status = runner.invoke(cli.app, ["status"])
    assert status.exit_code == 0 and "spent today" in status.stdout and "queued: 1" in status.stdout


def test_field_check_answer_records_fact_and_requeues_verify(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    fc = repo.add_field_check(
        db_session,
        gap_id=gap.id,
        question="Sitters in Prizren?",
        why="w",
        due=datetime.now(UTC).date(),
    )
    out = runner.invoke(cli.app, ["field-check", "answer", str(fc.id), "No sitters, only two vets"])
    assert out.exit_code == 0
    fact = repo.search_facts(db_session, "sitters", now=datetime.now(UTC))[0]
    assert (
        fact.confidence == 0.95
        and fact.source_name == "founder"
        and fact.entity_key == f"gap:{gap.id}"
    )
    task = repo.queued_tasks(db_session)[0]
    assert task.profile == "verify-gap" and task.priority == 90 and task.payload["gap_id"] == gap.id
    assert repo.open_field_checks(db_session) == []


def test_flag_gap_and_set_phase(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    assert runner.invoke(cli.app, ["flag-gap", str(gap.id)]).exit_code == 0
    assert repo.get_setting(db_session, "flagged_gaps") == [gap.id]
    assert runner.invoke(cli.app, ["set-phase", "verification"]).exit_code == 0
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    assert runner.invoke(cli.app, ["set-phase", "nonsense"]).exit_code != 0


def test_run_dry_run_passes_flags(monkeypatch):
    seen = {}

    def fake_run_once(settings, **kw):
        seen.update(kw)
        from scout.director.run import RunSummary

        return RunSummary(
            1,
            kw["today"] or datetime.now(UTC).date(),
            "foundation",
            0,
            0,
            0,
            Decimal("0"),
            "",
            "dry run",
        )

    monkeypatch.setattr(cli, "run_once", fake_run_once)
    out = runner.invoke(
        cli.app, ["run", "--budget", "0.50", "--phase", "verification", "--dry-run"]
    )
    assert out.exit_code == 0 and seen["budget_override"] == Decimal("0.50")
    assert seen["phase_override"] == "verification" and seen["dry_run"] is True


def test_run_installs_a_sigterm_handler_that_exits_143_and_restores_it(monkeypatch):
    import os
    import signal

    before = signal.getsignal(signal.SIGTERM)
    seen = {}

    def fake_run_once(settings, **kw):
        seen["handler"] = signal.getsignal(signal.SIGTERM)
        if seen["handler"] is getattr(cli, "sigterm_to_exit", None):  # never kill pytest itself
            os.kill(os.getpid(), signal.SIGTERM)  # Render stopping the cron job
        raise AssertionError("SIGTERM should have raised SystemExit")

    monkeypatch.setattr(cli, "run_once", fake_run_once)
    out = runner.invoke(cli.app, ["run", "--dry-run"])
    assert seen["handler"] is cli.sigterm_to_exit and out.exit_code == 143
    assert signal.getsignal(signal.SIGTERM) is before
    with pytest.raises(SystemExit) as exc:
        cli.sigterm_to_exit(signal.SIGTERM, None)
    assert exc.value.code == 143


def test_set_cap_and_cli_actions_are_journaled(db_session):
    from scout.db.models import JournalEntry

    assert runner.invoke(cli.app, ["set-cap", "1.25"]).exit_code == 0
    assert runner.invoke(cli.app, ["set-cap", "abc"]).exit_code != 0
    assert runner.invoke(cli.app, ["set-phase", "verification"]).exit_code == 0
    did = db_session.query(JournalEntry).filter(JournalEntry.run_id.is_(None)).one().did_md
    assert "set today's cap to €1.25" in did and "set phase to verification" in did
