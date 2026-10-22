"""
Cliente de Integração com a API de Visão Computacional do iNaturalist.
Permite inferência taxonômica com prior geográfico, gerenciamento de tokens OAuth/JWT,
controle de taxa (rate-limiting) e parsing estruturado de táxons.
"""

import io
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import requests
from PIL import Image


class INaturalistAuthError(Exception):
    """Exceção levantada em caso de falha de autenticação com o iNaturalist."""
    pass


class INaturalistAPIError(Exception):
    """Exceção levantada quando a API retorna erro de processamento."""
    pass


class INaturalistClient:
    """Cliente para a API de Visão Computacional do iNaturalist."""

    DEFAULT_API_URL = "https://api.inaturalist.org/v2/computervision/score_image"
    OAUTH_TOKEN_URL = "https://www.inaturalist.org/oauth/token"
    USER_API_TOKEN_URL = "https://www.inaturalist.org/users/api_token"

    def __init__(
        self,
        credentials_path: Optional[Union[str, Path]] = None,
        jwt_token: Optional[str] = None,
        api_url: Optional[str] = None,
        request_delay_seconds: float = 1.0,
        timeout_seconds: float = 25.0
    ):
        self.credentials_path = Path(credentials_path) if credentials_path else None
        self._manual_jwt = jwt_token or os.getenv("INATURALIST_API_TOKEN")
        self.api_url = api_url or self.DEFAULT_API_URL
        self.request_delay_seconds = max(0.1, float(request_delay_seconds))
        self.timeout_seconds = float(timeout_seconds)

        self._cached_jwt: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        self._last_request_time: float = 0.0

    def _load_credentials(self) -> Dict[str, Any]:
        """Carrega credenciais de secrets/inaturalist.json."""
        if self.credentials_path and self.credentials_path.exists():
            try:
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                raise INaturalistAuthError(f"Erro ao ler arquivo de credenciais {self.credentials_path}: {e}")

        # Tenta caminho relativo padrão se não fornecido
        default_p = Path(__file__).resolve().parent.parent.parent.parent / "secrets" / "inaturalist.json"
        if default_p.exists():
            try:
                with open(default_p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {}

    def get_valid_jwt(self, force_refresh: bool = False) -> str:
        """
        Obtém um JWT válido para autenticação.
        Se houver manual_jwt, utiliza-o.
        Caso contrário, utiliza credenciais OAuth (username, password, app_id, app_secret)
        para gerar e renovar automaticamente o token.
        """
        now = datetime.now()

        # Se já tiver um JWT em cache não expirado e não for forçado o refresh
        if not force_refresh and self._cached_jwt:
            if self._jwt_expires_at is None or now < self._jwt_expires_at:
                return self._cached_jwt

        creds = self._load_credentials()

        # 1. Token JWT explícito nas credenciais ou manual
        token_candidate = creds.get("jwt_token") or self._manual_jwt
        if token_candidate and not force_refresh:
            self._cached_jwt = token_candidate.strip()
            self._jwt_expires_at = now + timedelta(hours=20)
            return self._cached_jwt

        # 2. Fluxo OAuth automatizado (Username + Password + App ID + App Secret)
        username = creds.get("username")
        password = creds.get("password")
        app_id = creds.get("app_id")
        app_secret = creds.get("app_secret")

        if not all([username, password, app_id, app_secret]):
            if token_candidate:
                # Se só tiver o token mesmo expirando, retorna ele
                self._cached_jwt = token_candidate.strip()
                return self._cached_jwt
            raise INaturalistAuthError(
                "Credenciais do iNaturalist não encontradas. Configure 'secrets/inaturalist.json' "
                "com username, password, app_id e app_secret, ou defina um jwt_token."
            )

        try:
            # Etapa 1: Obter access_token via OAuth password grant
            oauth_payload = {
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "password",
                "username": username,
                "password": password
            }
            resp_oauth = requests.post(
                self.OAUTH_TOKEN_URL,
                json=oauth_payload,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds
            )
            if resp_oauth.status_code != 200:
                raise INaturalistAuthError(
                    f"Falha ao autenticar no iNaturalist OAuth (HTTP {resp_oauth.status_code}): {resp_oauth.text[:300]}"
                )

            oauth_data = resp_oauth.json()
            access_token = oauth_data.get("access_token")
            if not access_token:
                raise INaturalistAuthError(f"OAuth do iNaturalist não retornou access_token: {oauth_data}")

            # Etapa 2: Obter JWT a partir do access_token
            resp_jwt = requests.get(
                self.USER_API_TOKEN_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                },
                timeout=self.timeout_seconds
            )
            if resp_jwt.status_code != 200:
                raise INaturalistAuthError(
                    f"Falha ao obter JWT da API do iNaturalist (HTTP {resp_jwt.status_code}): {resp_jwt.text[:300]}"
                )

            jwt_data = resp_jwt.json()
            jwt_token = jwt_data.get("api_token")
            if not jwt_token:
                raise INaturalistAuthError(f"Resposta do endpoint users/api_token não conteve api_token: {jwt_data}")

            self._cached_jwt = jwt_token.strip()
            # JWT do iNaturalist tem validade típica de 24h. Renovamos preventivamente com 22h.
            self._jwt_expires_at = now + timedelta(hours=22)
            return self._cached_jwt

        except requests.RequestException as e:
            raise INaturalistAuthError(f"Erro de conexão durante autenticação no iNaturalist: {e}")

    def _throttle(self):
        """Garante intervalo de segurança entre chamadas para respeitar o rate-limiting."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)
        self._last_request_time = time.time()

    def _prepare_image_bytes(self, pil_image: Image.Image, max_dim: int = 1600, quality: int = 90) -> bytes:
        """
        Redimensiona defensivamente se a imagem for gigantesca e comprime em JPEG na memória.
        A API do iNaturalist processa com precisão máxima em ~1024 a 1600px, economizando banda.
        """
        w, h = pil_image.size
        img_to_send = pil_image

        if max(w, h) > max_dim:
            if w >= h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))
            img_to_send = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        if img_to_send.mode != "RGB":
            img_to_send = img_to_send.convert("RGB")

        buf = io.BytesIO()
        img_to_send.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def score_image(
        self,
        image: Union[Image.Image, bytes],
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        positional_accuracy: Optional[float] = None,
        observed_on: Optional[Union[str, datetime]] = None,
        taxon_id: Optional[int] = 3,  # 3 = Classe Aves no iNaturalist
        top_k: int = 3,
        locale: str = "pt-BR"
    ) -> List[Dict[str, Any]]:
        """
        Envia recorte para o endpoint computervision/score_image da API do iNaturalist.
        Retorna as top_k predições formatadas com taxonomia detalhada e scores de confiança.
        """
        if isinstance(image, Image.Image):
            img_bytes = self._prepare_image_bytes(image)
        elif isinstance(image, bytes):
            img_bytes = image
        else:
            raise ValueError("O parâmetro image deve ser uma instância de PIL.Image ou bytes.")

        # Obtém token de autenticação
        jwt_token = self.get_valid_jwt()

        # Monta dados de geolocalização e data
        data_payload: Dict[str, str] = {}
        if lat is not None:
            data_payload["lat"] = f"{float(lat):.6f}"
        if lng is not None:
            data_payload["lng"] = f"{float(lng):.6f}"
        if positional_accuracy is not None:
            data_payload["positional_accuracy"] = str(int(positional_accuracy))
        if observed_on is not None:
            if isinstance(observed_on, datetime):
                data_payload["observed_on"] = observed_on.strftime("%Y-%m-%d %H:%M:%S")
            else:
                data_payload["observed_on"] = str(observed_on)
        if taxon_id is not None:
            data_payload["taxon_id"] = str(taxon_id)

        # Headers: iNaturalist v2 aceita o JWT diretamente no cabeçalho Authorization
        headers = {
            "Authorization": jwt_token,
            "Accept": "application/json",
            "Accept-Language": locale
        }

        # Tentativas com tratamento de 401 (reautenticação) e 429 (rate-limit)
        max_retries = 2
        for attempt in range(max_retries + 1):
            self._throttle()

            files = {
                "image": ("crop.jpg", img_bytes, "image/jpeg")
            }

            try:
                resp = requests.post(
                    self.api_url,
                    headers=headers,
                    files=files,
                    data=data_payload,
                    timeout=self.timeout_seconds
                )

                # Tratamento de 401 Unauthorized: renova token e tenta mais uma vez
                if resp.status_code == 401 and attempt < max_retries:
                    jwt_token = self.get_valid_jwt(force_refresh=True)
                    headers["Authorization"] = jwt_token
                    continue

                # Tratamento de 429 Too Many Requests: espera com backoff
                if resp.status_code == 429 and attempt < max_retries:
                    wait_time = (attempt + 1) * 3.0
                    time.sleep(wait_time)
                    continue

                if resp.status_code != 200:
                    raise INaturalistAPIError(
                        f"Erro na API do iNaturalist (HTTP {resp.status_code}): {resp.text[:400]}"
                    )

                return self._parse_predictions(resp.json(), top_k=top_k)

            except requests.RequestException as e:
                if attempt == max_retries:
                    raise INaturalistAPIError(f"Falha de rede ao conectar com a API do iNaturalist: {e}")
                time.sleep(1.5)

        return []

    def _parse_predictions(self, resp_json: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        """Extrai e normaliza os resultados da resposta JSON do iNaturalist."""
        results = resp_json.get("results", [])
        if not results:
            return []

        parsed = []
        for item in results:
            taxon = item.get("taxon", {})
            if not taxon:
                continue

            sci_name = taxon.get("name", "").strip()
            comm_pt = (taxon.get("preferred_common_name") or "").strip()
            comm_en = (taxon.get("english_common_name") or "").strip()

            # Se não houver nome em português, usa o inglês ou científico como fallback
            if not comm_pt:
                comm_pt = comm_en or sci_name

            # Extrai Ordem e Família da árvore taxonômica de ancestrais
            family = ""
            order = ""
            for anc in taxon.get("ancestors", []):
                rank = anc.get("rank", "").lower()
                if rank == "family":
                    family = anc.get("name", "").strip()
                elif rank == "order":
                    order = anc.get("name", "").strip()

            # Ponderação de score: prioriza combined_score (que inclui geo-prior), com fallback para vision_score
            combined = float(item.get("combined_score", 0.0) or 0.0)
            vision = float(item.get("vision_score", 0.0) or 0.0)
            conf = combined if combined > 0.0 else vision

            parsed.append({
                "scientific_name": sci_name,
                "common_name": comm_pt,
                "common_name_en": comm_en,
                "family": family,
                "order": order,
                "confidence": conf,
                "vision_score": vision,
                "combined_score": combined,
                "taxon_id": taxon.get("id")
            })

            if len(parsed) >= top_k:
                break

        return parsed
