"""
Módulo de Consenso de Espécies em Rajadas (IRIS Bird ID - Burst Consensus).
Agrega as predições taxonômicas de múltiplos recortes de fotos pertencentes ao mesmo
disparo contínuo (burst_id), aplicando votação ponderada (Soft Voting) para determinar
a espécie predominante e calcular a confiança consolidada da rajada.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def calculate_crop_quality_score(rec: Dict[str, Any]) -> float:
    """
    Calcula o score de qualidade visual de um recorte baseado em nitidez e confiança YOLO.
    Prioriza recortes com maior nitidez (variância Laplaciana) e maior probabilidade de ave.
    """
    meta = rec.get("metadata_json", {})
    sharpness = meta.get("sharpness")
    if sharpness is None or sharpness == 0.0:
        crop_path = rec.get("crop_saved_path", "")
        if crop_path:
            p = Path(crop_path)
            if p.exists():
                try:
                    import cv2
                    from .detector import safe_imread
                    img_bgr = safe_imread(str(p))
                    if img_bgr is not None:
                        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    else:
                        sharpness = 0.0
                except Exception:
                    sharpness = 0.0
            else:
                sharpness = 0.0
        else:
            sharpness = 0.0

    yolo_conf = float(meta.get("yolo_conf", 0.5))
    # Score composto: nitidez modulada pela confiança YOLO
    return float(sharpness) * (yolo_conf if yolo_conf > 0 else 0.1)


def rank_burst_crops(crops_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ranqueia a lista de recortes da rajada em ordem decrescente de nitidez e qualidade visual.
    Garante que as fotos mais nítidas e confiáveis sejam avaliadas primeiro.
    """
    return sorted(crops_list, key=calculate_crop_quality_score, reverse=True)


def check_burst_early_exit(
    evaluated_predictions: List[Dict[str, Any]],
    required_confirmations: int,
    min_species_confidence: float = 0.70
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], int]:
    """
    Verifica se alguma espécie já alcançou o número mínimo configurado de fotos
    com alta confiança dentro da rajada.

    Retorna:
    - (is_early_exit, leading_scientific_name, leading_sample_meta, leading_confirmations_count)
    """
    if not evaluated_predictions or required_confirmations <= 0:
        return False, None, None, 0

    species_confirmations = Counter()
    species_samples: Dict[str, Dict[str, Any]] = {}

    for item in evaluated_predictions:
        preds = item.get("predictions", [])
        if not preds:
            continue
        top1 = preds[0]
        conf = float(top1.get("confidence", 0.0))
        sci = top1.get("scientific_name", "")

        if conf >= min_species_confidence and sci:
            species_confirmations[sci] += 1
            if sci not in species_samples:
                species_samples[sci] = top1

            if species_confirmations[sci] >= required_confirmations:
                return True, sci, species_samples[sci], species_confirmations[sci]

    if species_confirmations:
        top_sci, top_count = species_confirmations.most_common(1)[0]
        return False, top_sci, species_samples.get(top_sci), top_count

    return False, None, None, 0


def aggregate_burst_species(
    crop_predictions: List[Dict[str, Any]],
    min_species_confidence: float = 0.70,
    min_agreement_ratio: float = 0.50
) -> Optional[Dict[str, Any]]:
    """
    Consolida as predições de múltiplos recortes de uma mesma rajada fotográfica.

    Parâmetros:
    - crop_predictions: Lista de dicionários, onde cada elemento representa um recorte avaliado:
        {
            "crop_path": str,
            "item_path": str,
            "predictions": List[Dict[str, Any]]  # Top-K predições do BirdClassifier
        }
    - min_species_confidence: Limiar de confiança para considerar identificação de alta certeza.
    - min_agreement_ratio: Razão mínima de recortes concordantes com a espécie vencedora (ex: 0.50 = 50%).

    Retorna:
    - Dicionário com a espécie consensual e métricas da rajada, ou None se não houver predições válidas.
    """
    if not crop_predictions:
        return None

    # Mapeamento de votos acumulados por espécie (chave: (scientific_name, common_name))
    votes = defaultdict(float)
    top1_vote_counts = Counter()
    species_meta: Dict[Tuple[str, str], Dict[str, str]] = {}
    valid_crops_count = 0

    individual_top1_list = []

    for item in crop_predictions:
        preds = item.get("predictions", [])
        if not preds:
            continue

        valid_crops_count += 1
        top1 = preds[0]
        top1_key = (top1["scientific_name"], top1["common_name"])
        top1_vote_counts[top1_key] += 1

        individual_top1_list.append({
            "item_path": item.get("item_path", ""),
            "crop_path": item.get("crop_path", ""),
            "top1_scientific": top1["scientific_name"],
            "top1_common": top1["common_name"],
            "top1_confidence": float(top1["confidence"])
        })

        # Acumula votos de todas as predições top-k do recorte
        for p in preds:
            sp_key = (p["scientific_name"], p["common_name"])
            conf = float(p.get("confidence", 0.0))
            votes[sp_key] += conf

            if sp_key not in species_meta:
                species_meta[sp_key] = {
                    "common_en": p.get("common_name_en", ""),
                    "family": p.get("family", ""),
                    "order": p.get("order", "")
                }

    if not votes or valid_crops_count == 0:
        return None

    total_weight = sum(votes.values())
    sorted_votes = sorted(votes.items(), key=lambda x: x[1], reverse=True)

    # Espécie vencedora por votação ponderada
    winner_sci, winner_comm = sorted_votes[0][0]
    meta_winner = species_meta.get((winner_sci, winner_comm), {})

    # Contagem de recortes onde a espécie vencedora foi top-1
    crops_supporting_winner = top1_vote_counts[(winner_sci, winner_comm)]
    agreement_ratio = (crops_supporting_winner / valid_crops_count) if valid_crops_count > 0 else 0.0

    # Média aritmética das confianças individuais nos recortes onde a espécie vencedora foi top-1
    winner_confs = [
        it["top1_confidence"] for it in individual_top1_list
        if it["top1_scientific"] == winner_sci and it["top1_common"] == winner_comm
    ]
    mean_individual_confidence = (sum(winner_confs) / len(winner_confs)) if winner_confs else 0.0

    # Métrica de confiança consolidada:
    # A confiança da espécie vencedora não deve ser diluída pela soma de votos alternativos Top-2/Top-3.
    # Reflete a média das confianças individuais onde foi Top-1.
    if winner_confs:
        consensus_confidence = mean_individual_confidence
    else:
        consensus_confidence = (sorted_votes[0][1] / total_weight) if total_weight > 0 else 0.0

    # Top 2 e Top 3 consensuais
    top2_sci, top2_comm, top2_conf = "", "", 0.0
    if len(sorted_votes) > 1:
        top2_sci, top2_comm = sorted_votes[1][0]
        top2_conf = sorted_votes[1][1] / total_weight if total_weight > 0 else 0.0

    top3_sci, top3_comm, top3_conf = "", "", 0.0
    if len(sorted_votes) > 2:
        top3_sci, top3_comm = sorted_votes[2][0]
        top3_conf = sorted_votes[2][1] / total_weight if total_weight > 0 else 0.0

    # Avaliação de necessidade de revisão:
    # 1. Confiança consolidada abaixo do limiar
    # 2. Concordância entre os membros da rajada abaixo do limiar (ex: empate ou dispersão)
    needs_review = (
        (consensus_confidence < min_species_confidence) or
        (agreement_ratio < min_agreement_ratio)
    )

    vote_distribution = {
        f"{comm} ({sci})": round(weight / total_weight, 4) if total_weight > 0 else 0.0
        for (sci, comm), weight in sorted_votes[:5]
    }

    return {
        "species_common": winner_comm,
        "species_scientific": winner_sci,
        "species_common_en": meta_winner.get("common_en", ""),
        "family": meta_winner.get("family", ""),
        "order": meta_winner.get("order", ""),
        "confidence": round(consensus_confidence, 4),
        "mean_individual_confidence": round(mean_individual_confidence, 4),
        "top2_common": top2_comm,
        "top2_scientific": top2_sci,
        "top2_confidence": round(top2_conf, 4),
        "top3_common": top3_comm,
        "top3_scientific": top3_sci,
        "top3_confidence": round(top3_conf, 4),
        "needs_review": needs_review,
        "agreement_ratio": round(agreement_ratio, 4),
        "supporting_crops": crops_supporting_winner,
        "total_crops": valid_crops_count,
        "vote_distribution": vote_distribution,
        "individual_evaluations": individual_top1_list
    }
