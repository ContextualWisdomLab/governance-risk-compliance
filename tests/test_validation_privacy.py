"""Privacy regressions for rejected requests; all payloads are unit-test fixtures."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI, Form
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.requests import Request

from cwl_grc import remote_access


EXPECTED_ERROR = {
    "detail": [{
        "type": "request_validation_failed",
        "loc": [],
        "msg": "Check required fields and data types against the API schema.",
    }],
}


def application_client() -> tuple[TestClient, list[object]]:
    """Exercise the production boundary and handler with real FastAPI validation."""
    service_app = FastAPI()
    service_app.add_middleware(remote_access.PreviewBoundaryMiddleware)
    service_app.add_exception_handler(
        RequestValidationError,
        remote_access.validation_error_response,
    )
    mutation_calls: list[object] = []

    @service_app.post('/evidence-records')
    def post_evidence(body: dict[str, str]) -> dict[str, str]:
        """Detect whether validation allowed the protected mutation to run."""
        mutation_calls.append(body)
        return body

    @service_app.post('/unit-form')
    def post_form(evidence_text: str = Form(), count_value: int = Form()) -> dict[str, Any]:
        """Exercise the same handler for form validation without changing route policy."""
        mutation_calls.append(evidence_text)
        return {'evidence_text': evidence_text, 'count_value': count_value}

    return TestClient(service_app), mutation_calls


@pytest.mark.parametrize('request_body', [
    {'evidence_title': 'Unit-test evidence', 'payload_text': ['unit_test_private_value']},
    {'unit_test_private_value': []},
    'unit_test_private_value',
    ['unit_test_private_value'],
    {'unit_test_private_value': {'nested': ['unit_test_private_value']}},
    {f'unit_test_private_value_{index_value}': [] for index_value in range(200)},
])
def test_invalid_evidence_does_not_reflect_values_or_keys(request_body: Any) -> None:
    service_client, mutation_calls = application_client()
    with service_client:
        response = service_client.post('/evidence-records', json=request_body)
    assert response.status_code == 422
    assert response.json() == EXPECTED_ERROR
    assert len(response.content) < 180
    assert response.headers['cache-control'] == 'no-store'
    assert 'unit_test_private_value' not in response.text
    assert mutation_calls == []


def test_malformed_json_uses_the_same_bounded_response() -> None:
    service_client, mutation_calls = application_client()
    with service_client:
        response = service_client.post('/evidence-records', content=b'{"unit_test_private_value":', headers={'Content-Type':'application/json'})
    assert response.status_code == 422
    assert response.json() == EXPECTED_ERROR
    assert mutation_calls == []


def test_invalid_form_is_not_reflected_or_persisted() -> None:
    service_client, mutation_calls = application_client()
    with service_client:
        response = service_client.post('/unit-form', data={'evidence_text':'unit_test_private_value','count_value':'unit_test_private_value'}, headers={'Origin':'http://testserver'})
    assert response.status_code == 422
    assert response.json() == EXPECTED_ERROR
    assert mutation_calls == []


def test_valid_values_and_remote_denial_remain_unchanged() -> None:
    service_client, mutation_calls = application_client()
    evidence_body = {'payload_text':'unit_test_private_value'}
    with service_client:
        response = service_client.post('/evidence-records', json=evidence_body)
        denied_response = service_client.post('/evidence-records', json=evidence_body, headers={'Forwarded':''})
    assert response.status_code == 200
    assert response.json() == evidence_body
    assert denied_response.status_code == 503
    assert mutation_calls == [evidence_body]


def test_handler_does_not_inspect_or_log_exception_material(caplog: pytest.LogCaptureFixture) -> None:
    class OpaqueValidationError(RequestValidationError):
        """Fail a test if the handler tries to serialize untrusted exception content."""
        def errors(self) -> list[Any]:
            raise AssertionError('Exception material must not be inspected.')

        def __str__(self) -> str:
            raise AssertionError('Exception material must not be logged.')

    error_value = OpaqueValidationError([], body='unit_test_private_value')
    request_context = Request({'type':'http', 'headers':[], 'method':'POST', 'path':'/'})
    handler = remote_access.validation_error_response
    response = asyncio.run(handler(request_context, error_value))
    assert response.status_code == 422
    assert json.loads(response.body) == EXPECTED_ERROR
    assert caplog.records == []
