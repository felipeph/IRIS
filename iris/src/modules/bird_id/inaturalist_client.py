"""
Cliente de Integração com a API de Visão Computacional do iNaturalist.
Permite inferência taxonômica com prior geográfico, gerenciamento de tokens OAuth/JWT,
controle de taxa (rate-limiting) e parsing estruturado de táxons.
"""

import base64
import io
import json
import os
import re
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
    LOGIN_URL = "https://www.inaturalist.org/login"
    SESSION_URL = "https://www.inaturalist.org/session"

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
        self._loaded_credentials_path: Optional[Path] = None
        self._taxon_details_cache: Dict[int, Dict[str, str]] = {}

    def _load_credentials(self) -> Dict[str, Any]:
        """Carrega credenciais de secrets/inaturalist.json."""
        if self.credentials_path:
            if self.credentials_path.exists():
                try:
                    self._loaded_credentials_path = self.credentials_path
                    with open(self.credentials_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    raise INaturalistAuthError(f"Erro ao ler arquivo de credenciais {self.credentials_path}: {e}")
            return {}

        # Tenta caminhos padrão conhecidos apenas se nenhum caminho explícito foi fornecido
        iris_root = Path(__file__).resolve().parent.parent.parent.parent
        candidates = [
            iris_root / "secrets" / "inaturalist.json",
            iris_root.parent / "secrets" / "inaturalist.json",
            Path.cwd() / "secrets" / "inaturalist.json",
            Path.cwd() / "iris" / "secrets" / "inaturalist.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    self._loaded_credentials_path = candidate
                    with open(candidate, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        return {}

    def _save_token_to_credentials(self, jwt_token: str):
        """Salva o novo token JWT de volta no arquivo de credenciais para persistência entre execuções."""
        if not self._loaded_credentials_path or not self._loaded_credentials_path.exists():
            return
        try:
            with open(self._loaded_credentials_path, "r", encoding="utf-8") as f:
                creds = json.load(f)
            creds["jwt_token"] = jwt_token.strip()
            with open(self._loaded_credentials_path, "w", encoding="utf-8") as f:
                json.dump(creds, f, indent=4, ensure_ascii=False)
        except Exception:
            # Falha de escrita em disco não deve interromper execução se o token estiver válido em memória
            pass

    @staticmethod
    def _get_jwt_expiration(jwt_token: str) -> Optional[datetime]:
        """Extrai o timestamp de expiração (exp) do payload JWT sem verificar assinatura."""
        try:
            parts = jwt_token.strip().split(".")
            if len(parts) >= 2:
                payload_b64 = parts[1]
                payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                data = json.loads(base64.urlsafe_b64decode(payload_b64))
                exp_ts = data.get("exp")
                if exp_ts:
                    return datetime.fromtimestamp(exp_ts)
        except Exception:
            pass
        return None

    def _authenticate_via_web_session(self, username: str, password: str) -> str:
        """
        Autentica via formulário de sessão web do iNaturalist (Rails Devise session).
        Não requer criação de aplicativo OAuth (app_id/app_secret) nem aprovação de desenvolvedor.
        Retorna o token JWT oficial emitido em /users/api_token.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })

        try:
            # 1. Carregar página de login e extrair token CSRF (authenticity_token)
            resp_login_page = session.get(self.LOGIN_URL, timeout=self.timeout_seconds)
            if resp_login_page.status_code != 200:
                raise INaturalistAuthError(
                    f"Falha ao carregar página de login do iNaturalist (HTTP {resp_login_page.status_code})"
                )

            csrf_token = None
            csrf_match = re.search(r'name=[\'"]authenticity_token[\'"]\s+value=[\'"]([^\'"]+)[\'"]', resp_login_page.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
            else:
                csrf_meta = re.search(r'<meta\s+name=[\'"]csrf-token[\'"]\s+content=[\'"]([^\'"]+)[\'"]', resp_login_page.text)
                if csrf_meta:
                    csrf_token = csrf_meta.group(1)

            if not csrf_token:
                raise INaturalistAuthError(
                    "Não foi possível localizar o token CSRF (authenticity_token) na página de login do iNaturalist."
                )

            # 2. Submeter credenciais para /session
            payload = {
                "authenticity_token": csrf_token,
                "user[email]": username,
                "user[password]": password,
                "user[remember_me]": "1",
                "commit": "Log In"
            }

            resp_login = session.post(
                self.SESSION_URL,
                data=payload,
                allow_redirects=False,
                timeout=self.timeout_seconds
            )

            # Em caso de sucesso, o Rails retorna redirecionamento 302/303 ou 200 com cookie de sessão
            if resp_login.status_code in (301, 302, 303):
                pass
            elif resp_login.status_code == 200:
                text_lower = resp_login.text.lower()
                if "invalid email, username or password" in text_lower or "senha inválida" in text_lower or 'name="user[password]"' in resp_login.text:
                    raise INaturalistAuthError(
                        "Falha na autenticação do iNaturalist: Usuário/E-mail ou Senha incorretos."
                    )
            else:
                raise INaturalistAuthError(
                    f"Falha inesperada no login do iNaturalist (HTTP {resp_login.status_code}): {resp_login.text[:300]}"
                )

            # 3. Obter JWT em /users/api_token usando a sessão autenticada
            resp_jwt = session.get(
                self.USER_API_TOKEN_URL,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds
            )

            if resp_jwt.status_code == 401:
                raise INaturalistAuthError(
                    "Sessão web do iNaturalist não foi autorizada em /users/api_token (HTTP 401). "
                    "Verifique seu usuário e senha."
                )
            elif resp_jwt.status_code != 200:
                raise INaturalistAuthError(
                    f"Falha ao obter JWT da API do iNaturalist via sessão (HTTP {resp_jwt.status_code}): {resp_jwt.text[:300]}"
                )

            try:
                jwt_data = resp_jwt.json()
            except Exception:
                raise INaturalistAuthError(
                    f"Resposta inválida de /users/api_token (esperava JSON): {resp_jwt.text[:300]}"
                )

            api_token = jwt_data.get("api_token")
            if not api_token:
                raise INaturalistAuthError(
                    f"Resposta de /users/api_token não conteve 'api_token': {jwt_data}"
                )

            return api_token.strip()

        except requests.RequestException as e:
            raise INaturalistAuthError(f"Erro de conexão durante autenticação de sessão no iNaturalist: {e}")

    def _authenticate_via_oauth(self, username: str, password: str, app_id: str, app_secret: str) -> str:
        """Autenticação clássica via OAuth password grant."""
        try:
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
                    f"Falha ao obter JWT da API do iNaturalist via OAuth (HTTP {resp_jwt.status_code}): {resp_jwt.text[:300]}"
                )

            jwt_data = resp_jwt.json()
            jwt_token = jwt_data.get("api_token")
            if not jwt_token:
                raise INaturalistAuthError(f"Resposta do endpoint users/api_token não conteve api_token: {jwt_data}")

            return jwt_token.strip()

        except requests.RequestException as e:
            raise INaturalistAuthError(f"Erro de conexão durante autenticação OAuth no iNaturalist: {e}")

    def get_valid_jwt(self, force_refresh: bool = False) -> str:
        """
        Obtém um JWT válido para autenticação.
        1. Se houver JWT em cache/arquivo e não expirado, utiliza-o.
        2. Se houver username e password, autentica via Sessão Web (sem necessidade de OAuth App)
           ou via OAuth se app_id e app_secret também estiverem configurados.
        3. Fallback para jwt_token manual.
        """
        now = datetime.now()

        # Se já tiver um JWT em cache não expirado e não for forçado o refresh
        if not force_refresh and self._cached_jwt:
            if self._jwt_expires_at is None or now < (self._jwt_expires_at - timedelta(minutes=5)):
                return self._cached_jwt

        # Se manual_jwt foi fornecido explicitamente na inicialização (sem force_refresh)
        if self._manual_jwt and not force_refresh:
            self._cached_jwt = self._manual_jwt.strip()
            self._jwt_expires_at = self._get_jwt_expiration(self._cached_jwt) or (now + timedelta(hours=20))
            return self._cached_jwt

        creds = self._load_credentials()

        token_candidate = creds.get("jwt_token") or self._manual_jwt
        username = creds.get("username")
        password = creds.get("password")
        app_id = creds.get("app_id")
        app_secret = creds.get("app_secret")

        has_user_pass = bool(username and password)
        has_oauth_keys = bool(app_id and app_secret)

        # 1. Se temos um token candidato e não foi forçado o refresh:
        if token_candidate and not force_refresh:
            exp_dt = self._get_jwt_expiration(token_candidate)
            if exp_dt:
                # Se ainda tem pelo menos 15 minutos de validade
                if now < (exp_dt - timedelta(minutes=15)):
                    self._cached_jwt = token_candidate.strip()
                    self._jwt_expires_at = exp_dt
                    return self._cached_jwt
                # Se expirou ou está para expirar, só reutiliza se NÃO tivermos credenciais para renovar
                elif not has_user_pass:
                    self._cached_jwt = token_candidate.strip()
                    self._jwt_expires_at = exp_dt
                    return self._cached_jwt
            else:
                if not has_user_pass:
                    self._cached_jwt = token_candidate.strip()
                    self._jwt_expires_at = now + timedelta(hours=20)
                    return self._cached_jwt

        # 2. Renovação automática via Sessão Web ou OAuth
        if has_user_pass:
            if has_oauth_keys:
                new_jwt = self._authenticate_via_oauth(username, password, app_id, app_secret)
            else:
                new_jwt = self._authenticate_via_web_session(username, password)

            self._cached_jwt = new_jwt.strip()
            exp_dt = self._get_jwt_expiration(self._cached_jwt)
            self._jwt_expires_at = exp_dt or (now + timedelta(hours=22))
            self._save_token_to_credentials(self._cached_jwt)
            return self._cached_jwt

        # 3. Fallback se só tiver o token manual (mesmo que sem checagem de expiração)
        if token_candidate:
            self._cached_jwt = token_candidate.strip()
            self._jwt_expires_at = self._get_jwt_expiration(self._cached_jwt) or (now + timedelta(hours=20))
            return self._cached_jwt

        raise INaturalistAuthError(
            "Credenciais do iNaturalist não encontradas. Configure 'secrets/inaturalist.json' "
            "com 'username' e 'password' para autenticação automática, ou defina um 'jwt_token'."
        )

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

    def _get_taxon_ancestry(self, taxon_id: Optional[int]) -> Dict[str, str]:
        """
        Obtém família e ordem a partir do endpoint /v2/taxa/{taxon_id}.
        Resultados são mantidos em cache na instância para evitar requisições redundantes.
        """
        if not taxon_id:
            return {"family": "", "order": ""}

        if taxon_id in self._taxon_details_cache:
            return self._taxon_details_cache[taxon_id]

        family = ""
        order = ""
        try:
            self._throttle()
            jwt_token = self.get_valid_jwt()
            headers = {
                "Authorization": jwt_token,
                "Accept": "application/json"
            }
            url = f"https://api.inaturalist.org/v2/taxa/{int(taxon_id)}?fields=(name:!t,rank:!t,ancestors:(name:!t,rank:!t))"
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    for anc in results[0].get("ancestors", []):
                        rank = anc.get("rank", "").lower()
                        if rank == "family":
                            family = anc.get("name", "").strip()
                        elif rank == "order":
                            order = anc.get("name", "").strip()
        except Exception:
            pass

        info = {"family": family, "order": order}
        self._taxon_details_cache[taxon_id] = info
        return info

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

        # Monta dados de geolocalização e data. Na v2, fields é mandatório para retorno completo do taxon.
        data_payload: Dict[str, str] = {
            "fields": "(combined_score:!t,vision_score:!t,taxon:all)"
        }
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

            # Extrai Ordem e Família da árvore taxonômica de ancestrais se vierem no payload
            family = ""
            order = ""
            for anc in taxon.get("ancestors", []) or []:
                rank = anc.get("rank", "").lower()
                if rank == "family":
                    family = anc.get("name", "").strip()
                elif rank == "order":
                    order = anc.get("name", "").strip()

            # Se não estiverem presentes no payload da visão (caso da API v2), busca via endpoint de táxons em cache
            t_id = taxon.get("id")
            if (not family or not order) and t_id:
                anc_info = self._get_taxon_ancestry(t_id)
                family = family or anc_info.get("family", "")
                order = order or anc_info.get("order", "")

            # Ponderação de score: prioriza combined_score (que inclui geo-prior), com fallback para vision_score
            combined = float(item.get("combined_score", 0.0) or 0.0)
            vision = float(item.get("vision_score", 0.0) or 0.0)
            conf = combined if combined > 0.0 else vision

            # Normalização para escala 0.0 a 1.0 (o iNaturalist retorna scores em 0.0..100.0)
            if conf > 1.0:
                conf = conf / 100.0
            if vision > 1.0:
                vision = vision / 100.0
            if combined > 1.0:
                combined = combined / 100.0

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
