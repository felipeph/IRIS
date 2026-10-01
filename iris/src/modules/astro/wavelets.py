"""Motor de Wavelets À Trous Multiescala com Proteção de Limbo para Astrofotografia Lunar.

Implementa a transformada de wavelets discretas estacionárias (Starlet / B3-spline)
com filtragem separável de alta performance em C++/OpenCV, ganho ajustável por camada,
denoising adaptativo e supressão de ringing/halos no limbo lunar (Limb Guard).
"""

from typing import Tuple, List, Optional, Dict
import numpy as np
import cv2


class LunarWaveletEngine:
    """Motor de decomposição e realce multiescala de relevo lunar."""

    # Presets padrão de ganhos por camada (do micro-detalhe 1px até estruturas amplas 16px)
    # e limiares de redução de ruído (denoise threshold)
    PRESETS: Dict[str, Dict[str, list]] = {
        "suave": {
            "description": "Realce sutil e natural, ideal para seeing instável ou ruído residual.",
            "gains": [1.15, 1.35, 1.45, 1.30, 1.10],
            "denoise": [0.003, 0.001, 0.0, 0.0, 0.0],
            "saturation_boost": 1.0,
        },
        "equilibrado": {
            "description": "Equilíbrio padrão: crateras nítidas, relevo esculpido e baixo ruído.",
            "gains": [1.35, 1.80, 1.90, 1.50, 1.20],
            "denoise": [0.002, 0.0005, 0.0, 0.0, 0.0],
            "saturation_boost": 1.05,
        },
        "enfatico": {
            "description": "Realce agressivo para stacks de alta relação sinal-ruído e microcrateras.",
            "gains": [1.60, 2.30, 2.20, 1.70, 1.30],
            "denoise": [0.0015, 0.0005, 0.0, 0.0, 0.0],
            "saturation_boost": 1.10,
        },
        "mineral": {
            "description": "Enfatiza variações de relevo e realça saturação mineral (titânio vs ferro).",
            "gains": [1.30, 1.70, 1.80, 1.45, 1.20],
            "denoise": [0.002, 0.0005, 0.0, 0.0, 0.0],
            "saturation_boost": 2.20,
        },
        "crateras_profundas": {
            "description": "Máxima profundidade e relevo 3D de crateras: wavelets enfáticas + Local Clarity + Curva S.",
            "gains": [1.65, 2.35, 2.30, 1.80, 1.35],
            "denoise": [0.0015, 0.0005, 0.0, 0.0, 0.0],
            "clarity_amount": 0.55,
            "clarity_sigma": 12.0,
            "s_curve_contrast": 1.25,
            "saturation_boost": 1.05,
        },
        "deconvolucao_extrema": {
            "description": "Nitidez cirúrgica de microdetalhes: Deconvolução Richardson-Lucy contra seeing + wavelets finas.",
            "deconvolve": True,
            "deconvolve_sigma": 1.3,
            "deconvolve_iterations": 6,
            "gains": [1.70, 2.40, 2.10, 1.60, 1.25],
            "denoise": [0.0015, 0.0005, 0.0, 0.0, 0.0],
            "clarity_amount": 0.30,
            "clarity_sigma": 10.0,
            "saturation_boost": 1.05,
        },
        "contraste_dramatico": {
            "description": "Relevo teatral e sombras profundas: Dual-scale CLAHE + curva tonal agressiva para terminador.",
            "gains": [1.50, 2.10, 2.10, 1.70, 1.30],
            "denoise": [0.002, 0.0008, 0.0, 0.0, 0.0],
            "clarity_amount": 0.65,
            "clarity_sigma": 14.0,
            "s_curve_contrast": 1.35,
            "dual_clahe": True,
            "saturation_boost": 1.10,
        },
        "cinematografico": {
            "description": "Acabamento HDR de alto impacto: micro-deconvolução suave + relevo equilibrado e cores ricas.",
            "deconvolve": True,
            "deconvolve_sigma": 1.1,
            "deconvolve_iterations": 4,
            "gains": [1.45, 1.95, 2.00, 1.60, 1.25],
            "denoise": [0.0018, 0.0005, 0.0, 0.0, 0.0],
            "clarity_amount": 0.40,
            "clarity_sigma": 10.0,
            "s_curve_contrast": 1.15,
            "saturation_boost": 1.25,
        },
    }

    def __init__(self, levels: int = 5):
        """
        Inicializa o motor de wavelets.

        Args:
            levels: Número de escalas diádicas (padrão: 5, correspondendo a 1, 2, 4, 8, 16 pixels).
        """
        self.levels = levels

    @staticmethod
    def _create_kernel_1d(step: int) -> np.ndarray:
        """
        Cria o kernel 1D B3-spline [1/16, 1/4, 3/8, 1/4, 1/16] dilatado com (step - 1) zeros.
        """
        k = np.zeros(4 * step + 1, dtype=np.float32)
        k[0] = 0.0625        # 1/16
        k[step] = 0.25       # 1/4
        k[2 * step] = 0.375  # 3/8
        k[3 * step] = 0.25   # 1/4
        k[4 * step] = 0.0625 # 1/16
        return k

    def decompose(self, image_float: np.ndarray, levels: Optional[int] = None) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        Decompõe a imagem em camadas de detalhe e uma camada residual suave (À Trous).

        Args:
            image_float: Imagem com valores float32 no intervalo [0.0, 1.0]. Pode ser 2D (mono) ou 3D (RGB).
            levels: Quantidade de níveis. Se None, usa self.levels.

        Returns:
            Tupla (approx, details), onde approx é o resíduo e details é a lista [w_0, w_1, ..., w_{J-1}].
        """
        j_levels = levels or self.levels
        current = image_float.astype(np.float32)
        details = []

        for j in range(j_levels):
            step = 2 ** j
            kernel = self._create_kernel_1d(step)

            # cv2.sepFilter2D aplica convolução 1D separável em linhas e colunas com borda refletida
            smoothed = cv2.sepFilter2D(current, -1, kernel, kernel, borderType=cv2.BORDER_REFLECT)
            detail = current - smoothed
            details.append(detail)
            current = smoothed

        return current, details

    @staticmethod
    def compute_limb_mask(image_float: np.ndarray, blur_radius: int = 7, edge_dilation: int = 15) -> np.ndarray:
        """
        Calcula uma máscara contínua [0.0, 1.0] identificando a borda externa da Lua contra o espaço negro.
        Onde a máscara for próxima de 1.0, o ganho de wavelets deve ser suprimido para evitar halos.

        Args:
            image_float: Imagem em float32 [0.0, 1.0].
            blur_radius: Raio de suavização para reduzir ruído de fundo.
            edge_dilation: Largura em pixels da zona de proteção ao redor do limbo.

        Returns:
            Máscara 2D float32 [0.0, 1.0] do mesmo tamanho espacial (H, W).
        """
        if image_float.ndim == 3:
            gray = cv2.cvtColor(image_float, cv2.COLOR_BGR2GRAY if image_float.shape[2] == 3 else cv2.COLOR_RGB2GRAY)
        else:
            gray = image_float.copy()

        # Suavização preliminar
        k_blur = blur_radius if blur_radius % 2 != 0 else blur_radius + 1
        blurred = cv2.GaussianBlur(gray, (k_blur, k_blur), 0)

        # Determinar limiar entre espaço escuro e superfície iluminada
        positives = blurred[blurred > 0.005]
        if len(positives) > 0:
            threshold = float(np.percentile(positives, 4))
            threshold = max(0.02, min(threshold, 0.15))
        else:
            threshold = 0.05

        binary_mask = (blurred > threshold).astype(np.uint8)

        # Gradiente morfológico para isolar apenas o contorno externo da Lua
        morph_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        boundary = cv2.morphologyEx(binary_mask, cv2.MORPH_GRADIENT, morph_k)

        # Dilatação suave gaussiana para criar uma zona de amortecimento contínua
        k_dil = edge_dilation if edge_dilation % 2 != 0 else edge_dilation + 1
        limb_mask = cv2.GaussianBlur(boundary.astype(np.float32), (k_dil, k_dil), 0)

        max_val = float(limb_mask.max())
        if max_val > 0.0:
            limb_mask /= max_val

        return limb_mask

    @staticmethod
    def apply_smooth_shrinkage(detail: np.ndarray, threshold: float) -> np.ndarray:
        """
        Redução de ruído contínua (smooth shrinkage) na camada de detalhe:
        w_out = w * (|w|^2 / (|w|^2 + tau^2)).
        Preserva bordas fortes e atenua micro-flutuações de ruído Gaussiano sem cortes abruptos.
        """
        if threshold <= 0.0:
            return detail

        tau_sq = threshold ** 2
        w_sq = detail ** 2
        factor = w_sq / (w_sq + tau_sq)
        return detail * factor

    def reconstruct(
        self,
        approx: np.ndarray,
        details: List[np.ndarray],
        gains: List[float],
        denoise_thresholds: Optional[List[float]] = None,
        limb_mask: Optional[np.ndarray] = None,
        limb_guard_strength: float = 1.0,
    ) -> np.ndarray:
        """
        Reconstrói a imagem a partir das camadas de aproximação e detalhes ponderados.

        Args:
            approx: Resíduo de baixa frequência.
            details: Lista de camadas de detalhe [w_0, ..., w_{J-1}].
            gains: Lista de multiplicadores para cada camada.
            denoise_thresholds: Lista opcional de limiares de ruído por camada.
            limb_mask: Máscara opcional do limbo para proteger a borda lunar contra ringing.
            limb_guard_strength: Força da atenuação do ganho nas imediações do limbo (0.0 = sem proteção, 1.0 = ganho 1.0 no limbo).

        Returns:
            Imagem reconstruída e aprimorada, limitada ao intervalo [0.0, 1.0].
        """
        reconstructed = approx.copy()

        # Ajusta dimensões da máscara para broadcasting em imagens RGB (H, W, 1)
        limb_factor = None
        if limb_mask is not None and limb_guard_strength > 0.0:
            mask = np.clip(limb_mask * limb_guard_strength, 0.0, 1.0)
            if approx.ndim == 3 and mask.ndim == 2:
                mask = np.expand_dims(mask, axis=2)
            limb_factor = 1.0 - mask

        num_layers = min(len(details), len(gains))
        for j in range(num_layers):
            layer_detail = details[j]
            gain = gains[j]

            # Denoising na camada de detalhe, se especificado
            if denoise_thresholds and j < len(denoise_thresholds) and denoise_thresholds[j] > 0.0:
                layer_detail = self.apply_smooth_shrinkage(layer_detail, denoise_thresholds[j])

            # Aplicação do ganho com proteção de limbo
            if limb_factor is not None:
                # O ganho efetivo no limbo decai suavemente para 1.0 (sem amplificação)
                effective_gain = 1.0 + (gain - 1.0) * limb_factor
                amplified = layer_detail * effective_gain
            else:
                amplified = layer_detail * gain

            reconstructed += amplified

        return np.clip(reconstructed, 0.0, 1.0)

    @staticmethod
    def richardson_lucy(
        image_float: np.ndarray,
        psf_sigma: float = 1.3,
        iterations: int = 6,
    ) -> np.ndarray:
        """
        Aplica Deconvolução Richardson-Lucy com PSF Gaussiana para reverter
        o borramento óptico induzido pela atmosfera (seeing) e difração da lente.
        """
        ksize = int(2 * np.ceil(3 * psf_sigma) + 1)
        psf_1d = cv2.getGaussianKernel(ksize, psf_sigma)
        psf = psf_1d @ psf_1d.T
        psf_mirror = cv2.flip(psf, -1)

        estimate = image_float.astype(np.float32).copy()
        for _ in range(iterations):
            reconv = cv2.filter2D(estimate, -1, psf, borderType=cv2.BORDER_REFLECT)
            reconv = np.maximum(reconv, 1e-6)
            ratio = image_float / reconv
            correction = cv2.filter2D(ratio, -1, psf_mirror, borderType=cv2.BORDER_REFLECT)
            estimate = np.clip(estimate * correction, 0.0, 1.0)

        return np.clip(estimate, 0.0, 1.0)

    @staticmethod
    def apply_local_clarity(
        image_float: np.ndarray,
        sigma: float = 12.0,
        amount: float = 0.5,
    ) -> np.ndarray:
        """
        Aplica micro-contraste de relevo médio (Clarity) no canal de luminância,
        aprofundando sombras internas de crateras e realçando cristas iluminadas.
        """
        if amount <= 0.0:
            return image_float

        if image_float.ndim == 2:
            blurred = cv2.GaussianBlur(image_float, (0, 0), sigma)
            high_pass = image_float - blurred
            return np.clip(image_float + high_pass * amount, 0.0, 1.0)

        # Em RGB, atua no canal L do LAB para preservar as cores dos mares
        lab = cv2.cvtColor(image_float, cv2.COLOR_RGB2LAB)
        l_channel = lab[:, :, 0] / 100.0  # normaliza L para [0, 1]
        blurred = cv2.GaussianBlur(l_channel, (0, 0), sigma)
        high_pass = l_channel - blurred
        enhanced_l = np.clip(l_channel + high_pass * amount, 0.0, 1.0)
        lab[:, :, 0] = enhanced_l * 100.0
        return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0.0, 1.0)

    def process_preset(
        self,
        image_float: np.ndarray,
        preset_name: str = "equilibrado",
        use_limb_guard: bool = True,
        limb_guard_strength: float = 1.0,
        override_deconvolve: Optional[bool] = None,
        override_clarity: Optional[float] = None,
    ) -> np.ndarray:
        """
        Aplica um preset completo de wavelets multiescala sobre uma imagem lunar em ponto flutuante.

        Args:
            image_float: Imagem em float32 [0.0, 1.0].
            preset_name: Nome do preset (ex: 'equilibrado', 'enfatico', 'crateras_profundas', etc.).
            use_limb_guard: Se True, calcula e aplica a máscara anti-halo no limbo lunar.
            limb_guard_strength: Intensidade da proteção (0.0 a 1.0).
            override_deconvolve: Se especificado, força ativação ou desativação de Richardson-Lucy.
            override_clarity: Se especificado, força a intensidade do micro-contraste de relevo (Clarity).

        Returns:
            Imagem processada e corrigida.
        """
        if preset_name not in self.PRESETS:
            raise ValueError(f"Preset desconhecido '{preset_name}'. Opções: {list(self.PRESETS.keys())}")

        config = self.PRESETS[preset_name]
        gains = config["gains"]
        denoise = config["denoise"]
        sat_boost = config.get("saturation_boost", 1.0)

        # 1. Deconvolução Richardson-Lucy preliminar (se ativada pelo preset ou override)
        should_deconvolve = config.get("deconvolve", False) if override_deconvolve is None else override_deconvolve
        working_img = image_float
        if should_deconvolve:
            sigma = config.get("deconvolve_sigma", 1.3)
            iters = config.get("deconvolve_iterations", 6)
            working_img = self.richardson_lucy(working_img, psf_sigma=sigma, iterations=iters)

        # 2. Decomposição À Trous
        approx, details = self.decompose(working_img, levels=len(gains))

        # 3. Detecção de Limbo (Anti-ringing)
        limb_mask = None
        if use_limb_guard:
            limb_mask = self.compute_limb_mask(working_img)

        # 4. Reconstrução Ponderada
        result = self.reconstruct(
            approx,
            details,
            gains=gains,
            denoise_thresholds=denoise,
            limb_mask=limb_mask,
            limb_guard_strength=limb_guard_strength,
        )

        # 5. Micro-contraste de relevo local (Clarity)
        clarity_amt = config.get("clarity_amount", 0.0) if override_clarity is None else override_clarity
        if clarity_amt > 0.0:
            clarity_sig = config.get("clarity_sigma", 12.0)
            result = self.apply_local_clarity(result, sigma=clarity_sig, amount=clarity_amt)

        # 6. Ajuste de saturação mineral (se solicitado e for imagem colorida)
        if sat_boost != 1.0 and result.ndim == 3 and result.shape[2] == 3:
            hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_boost, 0.0, 1.0)
            result = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

        return np.clip(result, 0.0, 1.0)
