import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import spend_analysis as sa  # noqa: E402

DF = sa.generer()


def test_abc_couvre_toute_la_depense():
    a = sa.abc(DF)
    assert abs(a["part"].sum() - 1) < 1e-9
    assert set(a["classe"]) <= {"A", "B", "C"}
    assert a["cumul"].is_monotonic_increasing


def test_hhi_borne():
    h = sa.hhi(DF)
    assert ((h > 0) & (h <= 10_000)).all()


def test_economies_positives_et_inferieures_a_la_depense():
    e = sa.ecarts_prix(DF)
    assert (e["economie"] >= 0).all()
    assert e["economie"].sum() < DF["montant"].sum()
