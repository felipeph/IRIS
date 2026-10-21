"""
Classificador Taxonômico de Espécies de Aves (IRIS Bird ID).
Utiliza BioCLIP (OpenCLIP) para classificação fine-grained zero-shot
com prior taxonômico regional (Minas Gerais / Brasil).
"""

import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

import torch
from PIL import Image


def load_species_catalog(csv_path: Path) -> List[Dict[str, str]]:
    """Carrega lista de espécies a partir de arquivo CSV."""
    species = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            species.append({
                "scientific_name": row["scientific_name"].strip(),
                "common_name": row["common_name_pt"].strip(),
                "family": row.get("family", "").strip(),
                "order": row.get("order", "").strip()
            })
    return species


class BirdClassifier:
    """Classificador fine-grained de espécies baseado em BioCLIP / OpenCLIP."""

    def __init__(
        self,
        species_csv_path: Optional[Path] = None,
        model_name: str = "hf-hub:imageomics/bioclip",
        device: Optional[str] = None
    ):
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
            # Fallback seguro para ViT-B-32 padrão
            self.model, _, self.preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
            self.tokenizer = open_clip.get_tokenizer('ViT-B-32')

        self.model = self.model.to(self.device)
        self.model.eval()

        # Pré-computa embeddings de texto das espécies cadastradas
        self._init_text_embeddings()

    def _init_text_embeddings(self):
        prompts = [
            f"a photo of {sp['scientific_name']}, a type of bird ({sp['common_name']})"
            for sp in self.species_list
        ]
        tokens = self.tokenizer(prompts).to(self.device)
        with torch.no_grad():
            text_features = self.model.encode_text(tokens)
            self.text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    def classify_crop(self, pil_image: Image.Image, top_k: int = 5, use_tta: bool = True) -> List[Dict[str, Any]]:
        """
        Classifica um recorte de ave.
        Se use_tta=True, realiza Test-Time Augmentation (Original + Espelhamento Horizontal).
        """
        imgs = [pil_image]
        if use_tta:
            imgs.append(pil_image.transpose(Image.FLIP_LEFT_RIGHT))

        tensors = [self.preprocess(img) for img in imgs]
        batch_tensors = torch.stack(tensors).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(batch_tensors)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            # Média dos embeddings TTA
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
                "confidence": float(val.item())
            })
        return predictions
