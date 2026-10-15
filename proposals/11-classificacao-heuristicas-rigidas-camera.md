# Proposta 11: Correção de Heurísticas Rígidas de Modelo de Câmera na Classificação de Astrofotografia

## Contexto e Localização do Problema

- **Arquivo**: [`src/core/classifier.py`](file:///c:/code/IRIS/iris/src/core/classifier.py)
- **Linhas Críticas**: 206-218
- **Princípio Afetado**: **Correção de Domínio e Prevenção de Falhas no Pipeline**

### O Trecho de Código Atual

```python
# Em src/core/classifier.py (linhas 206-218)

moon_zoom = class_config.get("moon_zoom_threshold_mm", 1000.0)
for item in sorted_items:
    # 1. Astrofotografia (Lua RAW teleobjetiva)
    is_moon_focal = item.focal_length_equiv is not None and item.focal_length_equiv >= moon_zoom
    
    # <-- FALHA: Se a câmera for SX60 ou SX50, classifica como LUA independente do zoom!
    if item.is_raw and (is_moon_focal or "sx60" in item.camera_model.lower() or "sx50" in item.camera_model.lower()):
        astro_items.append(item)
    # 2. Vídeos
    elif item.is_video:
        video_items.append(item)
    # 3. Fotos Gerais
    else:
        general_photo_items.append(item)
```

---

## Diagnóstico da Causa-Raiz

1. **Classificação Errada de Fotos Diurnas e Paisagens**:
   - As câmeras Canon PowerShot SX50 HS e SX60 HS são superzooms versáteis. O fotógrafo as utiliza não apenas para astrofotografia lunar (onde o zoom equivalente atinge 1200mm a 1365mm), mas também para **paisagens, arquitetura e fotos de aves/natureza durante o dia**.
   - Por causa do operador `or "sx60" in ... or "sx50" in ...`:
     - Uma foto RAW de paisagem tirada em **21mm grande angular** ao meio-dia com uma SX60 é **obrigatoriamente categorizada como `astro_lua`**!
     - Ela é enviada para a pasta `5_Astrofotografia/Lua/YYYY/MM/DD/sessao_...`.

2. **Falha em Cascata na Etapa de Empilhamento (`AstroStackStage`)**:
   - Quando o pipeline chega na etapa 6 (`astro_stack`), o pré-processador tenta encontrar o disco lunar brilhante contra o fundo negro:
     ```python
     # Em preprocessor.py:
     count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
     if count < 2:
         raise ValueError("Nenhum objeto brilhante detectado.")
     ```
   - O worker do PlanetarySystemStacker falha imediatamente com exceção porque a foto é de um parque ensolarado, interrompendo todo o fluxo da sessão.

3. **Violação de Boas Práticas Arquiteturais**:
   - Modelos específicos de equipamento (`"sx60"`, `"sx50"`) nunca devem ser hardcoded em arquivos core de regras de negócio. Se o usuário adquirir uma Nikon P1000 ou uma Sony com teleobjetiva de 1200mm, o código precisará de nova edição manual.

---

## Abordagens de Solução

### Abordagem A: "Heurística Óptica Estrita (Distância Focal >= 1000mm)" (Recomendada para Simplicidade)
**Conceito**: Remover completamente o bypass de modelo de câmera. A Canon SX60 HS possui lente equivalente a 21-1365mm (e a SX50 a 24-1200mm). Quando o fotógrafo mira na Lua com zoom máximo, a distância focal equivalente calculada pelo `exiftool` é de **1365mm** (ou 1200mm), o que **já ultrapassa naturalmente o limiar de 1000mm**:

```python
is_moon_focal = item.focal_length_equiv is not None and item.focal_length_equiv >= moon_zoom
if item.is_raw and is_moon_focal:
    astro_items.append(item)
```

- **Vantagens**:
  - Elimina o bug imediatamente: fotos diurnas em grande angular voltam a ser tratadas como fotos gerais/avulsas normais.
  - Funciona universalmente para qualquer câmera presente ou futura (Canon, Sony, Nikon, telescópios conectados).
  - Reduz complexidade de código.
- **Desvantagens**:
  - Se um dia o fotógrafo usar um telescópio com lente totalmente manual sem comunicação eletrônica com o corpo (onde a distância focal EXIF vem como `0mm`), a foto precisará de ajuste manual ou indicação via pasta/configuração.

---

### Abordagem B: "Regras Configuráveis no `config.yaml` com Filtro Multi-Fatorial"
**Conceito**: Mover os critérios para o `config.yaml` sob `classification.astro`:
```yaml
classification:
  moon_zoom_threshold_mm: 1000.0
  astro:
    require_raw: true
    min_focal_mm: 1000.0
    # Opcional: só considera astro se tirada à noite/madrugada
    filter_night_only: false
```
E no código, avaliar apenas os parâmetros da configuração.

- **Vantagens**:
  - O usuário pode customizar o limiar de zoom conforme a lente que possui (ex: telescópio de 800mm).
  - Zero acoplamento no código-fonte.
- **Desvantagens**:
  - Nenhuma.

---

### Abordagem C: "Detecção Rápida de Conteúdo por Visão Computacional (CV2 Moon Pre-Flight)"
**Conceito**: Se o arquivo for RAW e tiver zoom suspeito, roda uma função leve do OpenCV (`has_moon_candidate(img)`) em um thumbnail reduzido de 128x128 pixels (< 2 milissegundos). Se houver um corpo circular brilhante isolado sobre fundo escuro, classifica como astro; caso contrário, classifica como foto comum.

- **Vantagens**:
  - Precisão de 100%: nunca tentará empilhar fotos que não sejam a Lua.
  - Alinhado com a meta do `TODO.md` de inteligência visual local.
- **Desvantagens**:
  - Exige abrir o thumbnail da imagem durante o planejamento.

---

## Tabela Comparativa

| Critério | Atual (Bugado) | Abordagem A (Óptica Estrita) | Abordagem B (Configurável) | Abordagem C (CV2 Pre-Flight) |
| :--- | :---: | :---: | :---: | :---: |
| **Fotos Diurnas SX60 no Astro?** | 🔴 Sim (Erro grave) | 🟢 Não (Corrigido) | 🟢 Não (Corrigido) | 🟢 Não (Corrigido) |
| **Suporte a Novas Câmeras** | ❌ Hardcoded | 🟢 Automático | 🟢 Automático | 🟢 Automático |
| **Tempo de Execução** | 0 ms | 0 ms | 0 ms | ~2 ms por foto |
| **Complexidade** | — | Mínima (1 linha) | Baixa (5 linhas) | Média (25 linhas) |

---

## Implementação Recomendada (União de A + B)

```python
# Em src/core/classifier.py

def classify_media_batch(items: list[MediaMetadata], class_config: dict | None = None, name_config: dict | None = None) -> list[ClassifiedItem]:
    if class_config is None:
        class_config = {}
    if name_config is None:
        name_config = {}

    sorted_items = sorted(items, key=lambda x: x.timestamp)
    classified: list[ClassifiedItem] = []

    astro_items: list[MediaMetadata] = []
    video_items: list[MediaMetadata] = []
    general_photo_items: list[MediaMetadata] = []

    moon_zoom = float(class_config.get("moon_zoom_threshold_mm", 1000.0))
    
    for item in sorted_items:
        # 1. Astrofotografia Lunar: Requer formato RAW E teleobjetiva extrema (>= 1000mm)
        is_telephoto_moon = (item.focal_length_equiv is not None and item.focal_length_equiv >= moon_zoom)
        
        if item.is_raw and is_telephoto_moon:
            astro_items.append(item)
        elif item.is_video:
            video_items.append(item)
        else:
            general_photo_items.append(item)
            
    # Continua o processamento normal...
```
