"""Run: python tests/test_app.py  — renders the dashboard headlessly (needs data/warehouse.duckdb from `dbt build`)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def test_app_renders_nationally_and_for_an_icb():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.metric[1].label == "Potential generic saving" and at.metric[1].value.startswith("£")

    at.sidebar.selectbox[1].select_index(1).run()  # first ICB -> practice drill-down
    assert not at.exception, at.exception
    assert at.slider, "practice drill-down should show the minimum-spend slider"


if __name__ == "__main__":
    test_app_renders_nationally_and_for_an_icb()
    print("ok")
