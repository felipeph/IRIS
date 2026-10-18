# Módulo 07: Edição & Upscale de Vídeo 4K UHD (`video_edit`)

O estágio de Edição de Vídeo (`VideoEditStage`) é projetado para processar clipes de vídeo convencionais gravados em campo (como filmagens de pássaros em superzoom na Canon SX60 HS), aplicando estabilização de pontas, aceleração de velocidade, filtros de nitidez e **upscale de alta fidelidade para 4K UHD (3840x2160)**.

---

## 1. Motivação Técnica: O Problema do 1080p no YouTube

Quando um vídeo gravado em resolução nativa 1080p (Full HD) é enviado diretamente ao YouTube:
1. O YouTube atribui o codec de baixa prioridade **AVC1 (H.264)** com bitrate muito reduzido (~8 Mbps).
2. A textura de penas de aves, folhagens finas e ondas de água sofrem forte degradação por compressão de blocos (*macroblocking*).
3. Ao realizar o **upscale para 4K UHD (3840x2160)** no IRIS antes do envio:
   - O YouTube aloca bitrates até 5x superiores (40–60 Mbps).
   - O player do YouTube passa a servir os formatos premium **VP09** e **AV01**, garantindo fidelidade cristalina.

---

## 2. Modos de Operação

O módulo oferece dois modos operacionais configuráveis:

### Modo 1: Individual (`mode: "individual"`)
Cada vídeo é processado de forma isolada (upscale 1:1), gerando um clipe master 4K correspondente de saída em `7_Video_Editado_4K/YYYY/MM/DD/`.

### Modo 2: Junção por Pasta de Origem (`mode: "joined"`)
Agrupa e concatena automaticamente em um único vídeo contínuo todos os clipes que vieram da mesma pasta de origem (e mesma câmera):
- Clipes são ordenados cronologicamente e concatenados sem perda de sincronia, independente do intervalo de tempo decorrido entre eles.
- Clipes de câmeras distintas são separados para preservar a homogeneidade de codec, resolução e perfil de cor.

---

## 3. Trimming Inteligente (Corte de Bordas)

Em filmagens de natureza com superzoom de 65x (1365mm), o simples ato mecânico de pressionar o botão de início e término de gravação no corpo da câmera introduz uma trepidação severa na imagem.

O IRIS aplica **Trimming Automático**:
- Corta os primeiros 2.0 segundos (`trim_start_sec = 2.0`) e os últimos 2.0 segundos (`trim_end_sec = 2.0`).
- **Proteção para Clipes Curtos:** Se um clipe tiver duração total inferior a 6.0 segundos, o algoritmo ajusta proporcionalmente os cortes para nunca descartar mais do que 30% da duração total do vídeo.

---

## 4. Controle de Velocidade e Áudio

- **Aceleração Dinâmica (`--speed=Nx`):** Permite acelerar filmagens de comportamento animal ou nuvens (ex: 2x, 5x, 10x) ajustando a escala de tempo com `setpts=(1/speed)*PTS` e interpolando a taxa de quadros para até 60 FPS (`fps=target_fps:round=near`).
- **Tratamento de Áudio:**
  - `strip_audio: true`: Remove completamente a trilha de áudio (`-an`) para evitar ruídos de vento em vídeos acelerados.
  - `strip_audio: false`: Ajusta a frequência e o tom do áudio com o filtro `atempo=speed` e codifica em AAC estéreo a 320 kbps.

---

## 5. Filtro Unsharp Mask + Upscale Lanczos

Antes de expandir a matriz de pixels de 1920x1080 para 3840x2160, o IRIS aplica uma máscara seletiva de nitidez:
```text
unsharp=5:5:0.8:5:5:0.0
```
Isso realça o contraste das micro-arestas na resolução nativa do sensor antes da interpolação Lanczos, impedindo que o upscale crie um aspecto difuso ou borrado.
