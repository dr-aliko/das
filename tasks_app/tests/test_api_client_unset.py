from unittest.mock import patch

from django.test import override_settings

from tasks_app.services import api_client


@override_settings(EXTERNAL_API_BASE_URL='')
def test_unset_base_url_returns_empty_lists_without_http():
    with patch('tasks_app.services.api_client.requests.get') as http_get, \
            patch('tasks_app.services.api_client.cache') as cache:
        assert api_client.get_dersler() == []
        assert api_client.get_oynatma_listeleri(1, 'tyt') == []
        assert api_client.get_videolar(1) == []
    http_get.assert_not_called()
    cache.get.assert_not_called()


@override_settings(EXTERNAL_API_BASE_URL='https://catalog.example/api')
def test_configured_base_url_is_used():
    with patch('tasks_app.services.api_client.requests.get') as http_get, \
            patch('tasks_app.services.api_client.cache') as cache:
        cache.get.return_value = None
        http_get.return_value.json.return_value = [{'Id': 1, 'Title': 'Mat'}]
        assert api_client.get_dersler() == [{'id': 1, 'ad': 'Mat'}]
    assert http_get.call_args.args[0] == 'https://catalog.example/api/dersler'
