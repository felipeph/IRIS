"""
Testes unitários automatizados para o cliente INaturalistClient (IRIS Bird ID).
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from src.modules.bird_id.inaturalist_client import (
    INaturalistClient,
    INaturalistAuthError,
    INaturalistAPIError
)


def test_client_init_with_direct_jwt():
    client = INaturalistClient(jwt_token="fake_jwt_token_123")
    assert client.get_valid_jwt() == "fake_jwt_token_123"


def test_client_load_credentials_missing(tmp_path):
    empty_creds = tmp_path / "non_existent.json"
    client = INaturalistClient(credentials_path=empty_creds)
    with pytest.raises(INaturalistAuthError):
        client.get_valid_jwt()


@patch("requests.post")
@patch("requests.get")
def test_client_oauth_login_flow(mock_get, mock_post, tmp_path):
    creds_file = tmp_path / "inaturalist.json"
    import json
    creds_file.write_text(json.dumps({
        "username": "user_test",
        "password": "pwd_test",
        "app_id": "app_123",
        "app_secret": "secret_456"
    }), encoding="utf-8")

    # Mock 1: OAuth token
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"access_token": "oauth_access_xyz"}
    mock_post.return_value = mock_post_resp

    # Mock 2: JWT API token
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {"api_token": "jwt_session_token_789"}
    mock_get.return_value = mock_get_resp

    client = INaturalistClient(credentials_path=creds_file, request_delay_seconds=0.01)
    jwt = client.get_valid_jwt()

    assert jwt == "jwt_session_token_789"
    # Chamada OAuth post
    assert mock_post.called
    payload = mock_post.call_args[1]["json"]
    assert payload["username"] == "user_test"
    assert payload["client_id"] == "app_123"

    # Chamada JWT get
    assert mock_get.called
    auth_header = mock_get.call_args[1]["headers"]["Authorization"]
    assert "oauth_access_xyz" in auth_header


def test_prepare_image_bytes():
    client = INaturalistClient(jwt_token="dummy")
    # Imagem grande 2400x1200
    large_img = Image.new("RGB", (2400, 1200), color="blue")
    img_bytes = client._prepare_image_bytes(large_img, max_dim=1600, quality=85)
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 0

    # Verifica se foi redimensionada
    import io
    reopened = Image.open(io.BytesIO(img_bytes))
    assert max(reopened.size) <= 1600


@patch("requests.post")
def test_score_image_with_geo_prior_and_parsing(mock_post):
    client = INaturalistClient(jwt_token="valid_jwt", request_delay_seconds=0.01)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "total_results": 2,
        "results": [
            {
                "combined_score": 0.945,
                "vision_score": 0.880,
                "taxon": {
                    "id": 16045,
                    "name": "Pitangus sulphuratus",
                    "preferred_common_name": "Bem-te-vi",
                    "english_common_name": "Great Kiskadee",
                    "ancestors": [
                        {"name": "Aves", "rank": "class"},
                        {"name": "Passeriformes", "rank": "order"},
                        {"name": "Tyrannidae", "rank": "family"}
                    ]
                }
            },
            {
                "combined_score": 0.050,
                "vision_score": 0.060,
                "taxon": {
                    "id": 16046,
                    "name": "Megarynchus pitangua",
                    "preferred_common_name": "Neinei",
                    "english_common_name": "Boat-billed Flycatcher",
                    "ancestors": [
                        {"name": "Passeriformes", "rank": "order"},
                        {"name": "Tyrannidae", "rank": "family"}
                    ]
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    test_img = Image.new("RGB", (300, 300), color="yellow")
    preds = client.score_image(
        image=test_img,
        lat=-19.9245,
        lng=-43.9456,
        positional_accuracy=15000,
        observed_on="2026-10-22 08:00:00",
        top_k=2
    )

    assert len(preds) == 2
    top1 = preds[0]
    assert top1["scientific_name"] == "Pitangus sulphuratus"
    assert top1["common_name"] == "Bem-te-vi"
    assert top1["common_name_en"] == "Great Kiskadee"
    assert top1["family"] == "Tyrannidae"
    assert top1["order"] == "Passeriformes"
    assert top1["confidence"] == pytest.approx(0.945, 0.001)

    # Verifica parâmetros enviados no POST
    call_kwargs = mock_post.call_args[1]
    data_sent = call_kwargs["data"]
    assert data_sent["lat"] == "-19.924500"
    assert data_sent["lng"] == "-43.945600"
    assert data_sent["positional_accuracy"] == "15000"
    assert data_sent["taxon_id"] == "3"
    assert "Authorization" in call_kwargs["headers"]


@patch("requests.post")
def test_score_image_401_refresh_retry(mock_post):
    client = INaturalistClient(jwt_token="stale_jwt", request_delay_seconds=0.01)

    # Primeira chamada: 401 Unauthorized
    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = "JWT is missing or invalid"

    # Segunda chamada pós-refresh: 200 OK
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "results": [
            {
                "combined_score": 0.89,
                "vision_score": 0.85,
                "taxon": {
                    "name": "Turdus rufiventris",
                    "preferred_common_name": "Sabiá-laranjeira"
                }
            }
        ]
    }

    mock_post.side_effect = [resp_401, resp_200]

    with patch.object(client, "get_valid_jwt", return_value="new_fresh_jwt"):
        test_img = Image.new("RGB", (100, 100), color="orange")
        preds = client.score_image(test_img, top_k=1)
        assert len(preds) == 1
        assert preds[0]["common_name"] == "Sabiá-laranjeira"
        assert mock_post.call_count == 2
