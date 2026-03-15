from whoopyy import constants


def test_no_v2_in_data_endpoints():
    for val in constants.ENDPOINTS.values():
        assert "/developer/v2/" not in val


def test_all_data_endpoints_use_v1():
    for val in constants.ENDPOINTS.values():
        if val.startswith("/developer"):
            assert "/developer/v1/" in val


def test_max_page_limit_is_25():
    assert constants.MAX_PAGE_LIMIT == 25


def test_sleep_for_cycle_not_in_endpoints():
    assert "sleep_for_cycle" not in constants.ENDPOINTS


def test_revoke_not_in_endpoints():
    assert "revoke" not in constants.ENDPOINTS
