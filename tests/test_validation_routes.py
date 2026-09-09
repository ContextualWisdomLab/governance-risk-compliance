"""Check validation privacy on actual GRC routes with synthetic unit-test payloads."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.remote_access import validation_error_response


@pytest.mark.parametrize('route_path,request_body', [
    ('/evidence-records', {'payload_text': ['unit_test_private_value']}),
    ('/evidence-records', {'unit_test_private_value': []}),
    ('/evidence-records', 'unit_test_private_value'),
    ('/control-evidence-bindings', {'unit_test_private_value': []}),
    ('/policy-documents', ['unit_test_private_value']),
])
def test_real_routes_use_the_non_reflecting_validation_handler(
    route_path: str, request_body: Any,
) -> None:
    service_app = create_app(database_url='sqlite://', evidence_key=None)
    assert service_app.exception_handlers[RequestValidationError] is validation_error_response
    with TestClient(service_app) as service_client:
        response = service_client.post(route_path, json=request_body)
        policy_rows = service_client.get('/policy-documents').json()['policies']
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['detail'][0]['type'] == 'request_validation_failed'
    assert response.json()['detail'][0]['loc'] == []
    assert 'unit_test_private_value' not in response.text
    assert len(response.content) < 180
    assert policy_rows == []


def test_missing_form_fields_do_not_reflect_other_form_values() -> None:
    with TestClient(create_app(database_url='sqlite://', evidence_key=None)) as service_client:
        response = service_client.post(
            '/officer/policy',
            headers={'Origin':'http://testserver'},
            data={'policy_body':'unit_test_private_value'},
        )
        policy_rows = service_client.get('/policy-documents').json()['policies']
    assert response.status_code == 422
    assert response.json()['detail'][0]['type'] == 'request_validation_failed'
    assert 'unit_test_private_value' not in response.text
    assert policy_rows == []
