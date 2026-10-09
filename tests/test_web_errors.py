import pytest

pytestmark = pytest.mark.db


def test_out_of_range_gap_id_is_a_400_not_a_500(web):
    r = web.get("/gaps/99999999999")
    assert r.status_code == 400 and "out of range or not allowed" in r.text


def test_out_of_range_id_in_a_post_path_is_a_400(web):
    r = web.post("/tasks/99999999999/retry", follow_redirects=False)
    assert r.status_code == 400


def test_out_of_range_id_in_a_form_field_is_a_400(web):
    r = web.post("/tasks", data={"gap_id": "99999999999", "profile": "verify-gap"})
    assert r.status_code == 400


def test_nul_byte_in_a_query_is_not_a_500(web):
    assert web.get("/knowledge?q=%00").status_code < 500


@pytest.mark.parametrize("field", ["theme", "sector"])
def test_nul_byte_in_a_form_text_field_is_a_400(web, field):
    r = web.post("/tasks", data={"profile": "verify-gap", field: "a\x00b"})
    assert r.status_code == 400


def test_session_is_usable_after_an_error(web):
    assert web.get("/gaps/99999999999").status_code == 400
    assert web.get("/gaps").status_code == 200
