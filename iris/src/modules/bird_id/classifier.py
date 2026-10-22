"""
Classificador Taxonômico de Espécies de Aves (IRIS Bird ID).
Suporta classificação via API de Visão Computacional do iNaturalist (recomendado e padrão)
ou BioCLIP local (OpenCLIP com catálogo regional).
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from PIL import Image

from .inaturalist_client import INaturalistClient

logger = logging.getLogger(__name__)


def load_species_catalog(csv_path: Path) -> List[Dict[str, str]]:
    """Carrega lista de espécies a partir de arquivo CSV (usado no modo BioCLIP)."""
    species = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            species.append({
                "scientific_name": row["scientific_name"].strip(),
                "common_name": row["common_name_pt"].strip(),
                "common_name_en": row.get("common_name_en", "").strip(),
                "family": row.get("family", "").strip(),
                "order": row.get("order", "").strip()
            })
    return species


class BirdClassifier:
    """Classificador taxonômico de espécies com suporte a iNaturalist API e BioCLIP."""

    def __init__(
        self,
        classifier_type: str = "inaturalist",
        species_csv_path: Optional[Path] = None,
        model_name: str = "hf-hub:imageomics/bioclip",
        device: Optional[str] = None,
        inat_client: Optional[INaturalistClient] = None,
        inat_credentials_path: Optional[Union[str, Path]] = None,
        inat_api_url: Optional[str] = None,
        inat_request_delay: float = 1.0
    ):
        self.classifier_type = (classifier_type or "inaturalist").lower().strip()

        if self.classifier_type == "inaturalist":
            self.client = inat_client or INaturalistClient(
                credentials_path=inat_credentials_path,
                api_url=inat_api_url,
                request_delay_seconds=inat_request_delay
            )
            self.model = None
            self.species_list = []
        else:
            # Modo BioCLIP local (lazy import para não onerar memória no modo iNaturalist)
            import torch
            if device is None:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self.device = device

            if species_csv_path is None:
                species_csv_path = Path(__file__).resolve().parent / "species_lists" / "br_mg_aves.csv"

            self.species_list = load_species_catalog(species_csv_path)

            import open_clip
            try:
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name)
                self.tokenizer = open_clip.get_tokenizer(model_name)
            except Exception:
                self.model, _, self.preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
                self.tokenizer = open_clip.get_tokenizer('ViT-B-32')

            self.model = self.model.to(self.device)
            self.model.eval()
            self._init_text_embeddings()

    def _init_text_embeddings(self):
        """Pré-computa embeddings para o catálogo local no modo BioCLIP."""
        import torch
        prompts = []
        for sp in self.species_list:
            comm_en = sp.get("common_name_en", "")
            comm_pt = sp.get("common_name", "")
            sci = sp.get("scientific_name", "")
            family = sp.get("family", "")
            if comm_en and comm_pt != comm_en:
                prompts.append(f"a photo of {sci}, also known as {comm_en} or {comm_pt}, a type of bird ({family})")
            else:
                prompts.append(f"a photo of {sci}, a type of bird ({comm_pt})")

        tokens = self.tokenizer(prompts).to(self.device)
        with torch.no_grad():
            text_features = self.model.encode_text(tokens)
            self.text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    def classify_crop(
        self,
        pil_image: Image.Image,
        top_k: int = 3,
        use_tta: bool = True,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        accuracy: Optional[float] = None,
        observed_on: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Classifica um recorte de ave.
        Se classifier_type == 'inaturalist', consulta a API do iNaturalist com prior geográfico.
        Se classifier_type == 'bioclip', realiza inferência zero-shot local com OpenCLIP.
        """
        if self.classifier_type == "inaturalist":
            try:
                return self.client.score_image(
                    image=pil_image,
                    lat=lat,
                    lng=lng,
                    positional_accuracy=accuracy,
                    observed_on=observed_on,
                    taxon_id=3,
                    top_k=top_k
                )
            except Exception as e:
                logger.warning(f"Erro ao consultar API do iNaturalist: {e}")
                return []

        # Rota BioCLIP local
        import torch
        imgs = [pil_image]
        if use_tta:
            imgs.append(pil_image.transpose(Image.FLIP_LEFT_RIGHT))

        tensors = [self.preprocess(img) for img in imgs]
        batch_tensors = torch.stack(tensors).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(batch_tensors)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            mean_features = image_features.mean(dim=0, keepdim=True)
            mean_features = mean_features / mean_features.norm(dim=-1, keepdim=True)

            similarity = (100.0 * mean_features @ self.text_features.T).softmax(dim=-1)[0]

        values, indices = similarity.topk(min(top_k, len(self.species_list)))

        predictions = []
        for val, idx in zip(values, indices):
            sp = self.species_list[idx.item()]
            predictions.append({
                "scientific_name": sp["scientific_name"],
                "common_name": sp["common_name"],
                "common_name_en": sp.get("common_name_en", ""),
                "family": sp.get("family", ""),
                "order": sp.get("order", ""),
                "confidence": float(val.item()),
                "vision_score": float(val.item()),
                "combined_score": float(val.item())
            })
        return predictions

