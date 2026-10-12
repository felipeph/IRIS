# Guia Técnico: Sanitização de Metadados EXIF para Compatibilidade com a Economia de Armazenamento do Google Fotos

## 1. Contexto do Problema

Quando uma fotografia é enviada ao **Google Fotos** no modo *Economia de armazenamento* (Storage Saver), ela passa por um pipeline interno de processamento e recompressão (baseado em parsers como libjpeg-turbo, MozJPEG e rotinas de transcodificação em nuvem). 

Caso o decodificador encontre estruturas de metadados binárias anômalas, formatos multi-imagem não suportados para compressão destrutiva ou corrupção de offsets, o pipeline aborta a conversão para proteger a integridade do arquivo. Em vez de descartar a imagem, o Google Fotos opta pelo fallback de segurança: salva a foto em **Qualidade original** e sinaliza o arquivo como *"Incompatível com a Economia de armazenamento"*, debitando o peso bruto (ex.: 6,0 MB em vez dos ~300 kB esperados) da cota da conta.

Em câmeras da linha **Canon PowerShot** (como a SX60 HS), isso ocorre com frequência mesmo em capturas sequenciais com a mesma lente e configuração de cena.

---

## 2. Elementos que Causam Incompatibilidade e Devem Ser Removidos

Abaixo estão os elementos específicos na estrutura do contêiner JPEG que provocam a falha no transcoder do Google:

### 2.1 Bloco MPF (*Multi-Picture Format* / Extensão CIPA DC-007)
* **Marcador JPEG:** Segmento `APP2` (`0xFFE2`).
* **Motivo da rejeição:** O padrão MPF encapsula ponteiros para múltiplos fluxos de imagem em um único arquivo (muito comum em modos de disparo contínuo, retratos com mapa de profundidade ou pré-visualizações em alta resolução geradas pela Canon). O próprio suporte do Google declara explicitamente que arquivos contendo MPF não passam pelo motor de compactação.

### 2.2 *MakerNotes* Proprietárias da Canon
* **Tag:** `MakerNotes:all` ou `Canon:all` dentro da estrutura EXIF.
* **Motivo da rejeição:** A Canon grava blocos proprietários extensos de telemetria (foco milimétrico, microajuste de sensor, dados internos do zoom ótico contínuo da SX60 HS, histórico de buffer). Se algum offset interno do MakerNote ultrapassar os limites ou apontar para endereços de memória inválidos fora do padrão TIFF, parsers restritivos falham na leitura dos metadados durante o parsing.

### 2.3 Dados de Trailer (*Data Past EOI Marker*)
* **Marcador JPEG afetado:** Dados gravados após o marcador final `EOI` (`0xFFD9`).
* **Motivo da rejeição:** Muitas câmeras Canon inserem metadados proprietários, índices de disparo ou arquivos de áudio auxiliares no fim do arquivo, após o término padrão do JPEG. O motor do Google descarta a compactação quando detecta lixo binário ou payloads no trailer que poderiam ser perdidos na remontagem do cabeçalho.

### 2.4 Fluxos Secundários de Imagem (*Embedded Previews*)
* **Tags:** `PreviewImage`, `ThumbnailImage` fora do IFD1 padrão.
* **Motivo da rejeição:** O embedding de JPEGs auxiliares de grande dimensão dentro do cabeçalho causa conflito de resolução quando o transcodificador tenta determinar as dimensões reais da imagem primária.

---

## 3. Preparação do Ambiente: Phil Harvey's ExifTool

O **ExifTool** é a ferramenta padrão da indústria para leitura, reescrita e saneamento de estruturas de metadados de baixo nível sem recodificar os blocos de imagem (mantendo 100% da fidelidade visual do RAW/JPEG).

### 3.1 Instalação

* **Linux (Debian/Ubuntu):**
  ```bash
  sudo apt-get update && sudo apt-get install libimage-exiftool-perl
  ```
* **macOS (Homebrew):**
  ```bash
  brew install exiftool
  ```
* **Windows:**
  * Baixe o executável `exiftool(-k).exe` no site oficial ([exiftool.org](https://exiftool.org/)), renomeie para `exiftool.exe` e adicione ao `%PATH%`.

---

## 4. Diagnóstico da Imagem Incompatível

Antes de sanitizar, execute estes comandos no arquivo rejeitado pelo Google Fotos para identificar os fatores causadores da falha:

### 4.1 Validação de Integridade e Alertas de Parsing
```bash
exiftool -validate -warning -a "IMG_FALHA.JPG"
```
*Gera relatórios de marcadores inválidos, offsets de MakerNote fora de ordem ou tags corrompidas.*

### 4.2 Identificação de Contêineres MPF
```bash
exiftool -MPF:all "IMG_FALHA.JPG"
```
*Se retornar tags como `MP Image Flags`, `MP Image Start` ou `MP Image Length`, o arquivo está sob a especificação CIPA MPF.*

### 4.3 Verificação de Dados de Trailer (Pós-EOI)
```bash
exiftool -trailer:all "IMG_FALHA.JPG"
```

---

## 5. Procedimentos de Sanitização com ExifTool

Dependendo da tolerância do seu fluxo de trabalho, você pode adotar uma remoção cirúrgica, moderada ou uma reconstrução completa do cabeçalho.

---

### Opção A: Sanitização Cirúrgica (Recomendada)
Esta opção remove especificamente o **MPF** e os **dados de trailer**, preservando todo o restante do EXIF da Canon SX60 HS intacto (Data de captura, Abertura, ISO, Tempo de Exposição, Distância Focal e GPS, se houver).

```bash
exiftool -MPF:all= -trailer:all= -overwrite_original "IMG_FALHA.JPG"
```

* **`-MPF:all=`**: Remove os marcadores APP2 CIPA DC-007.
* **`-trailer:all=`**: Trunca quaisquer dados inseridos após o marcador EOI (`0xFFD9`).
* **`-overwrite_original`**: Evita a duplicação do arquivo original com sufixo `_original`.

---

### Opção B: Sanitização Intermediária (Garante Aprovação no Google Fotos)
Se a foto ainda falhar após a Opção A, o problema reside nas **MakerNotes** internas da Canon. Esta opção limpa os blocos proprietários da câmera mantendo os parâmetros fotográficos universais:

```bash
exiftool -MPF:all= -trailer:all= -MakerNotes:all= -PreviewImage= -overwrite_original "IMG_FALHA.JPG"
```

* **`-MakerNotes:all=`**: Remove o bloco binário proprietário da Canon que costuma gerar conflitos de offset de ponteiro TIFF.
* **`-PreviewImage=`**: Elimina a miniatura incorporada de alta resolução.

---

### Opção C: Reconstrução Limpa da Estrutura EXIF (Abordagem Definitiva)
Se o cabeçalho estiver estruturalmente danificado ou com conflitos insolúveis, a abordagem mais segura é purgar todos os metadados corrompidos e reconstruir apenas as tags fotográficas essenciais:

```bash
exiftool -all= -tagsfromfile @ -exif:all -gps:all -iptc:all -xmp:all -icc_profile -MPF:all= -trailer:all= -MakerNotes:all= -overwrite_original "IMG_FALHA.JPG"
```

Esta operação:
1. Limpa todas as tabelas com `-all=`.
2. Lê o próprio arquivo (`-tagsfromfile @`).
3. Reinsere o EXIF padrão, coordenadas GPS, metadados IPTC/XMP e o Perfil de Cores (`-icc_profile`).
4. Bloqueia explicitamente a reentrada de MPF, trailers e MakerNotes.

---

## 6. Automação em Lote (Batch Processing)

Se você transferiu centenas de fotos do cartão SD da Canon PowerShot e deseja garantir que nenhuma falhe no Google Fotos:

### 6.1 Linux / macOS (Terminal Bash / Zsh)
Processar recursivamente uma pasta inteira de fotos `.JPG` e `.jpg`:

```bash
exiftool -r -ext jpg -ext JPG \
  -MPF:all= \
  -trailer:all= \
  -MakerNotes:all= \
  -overwrite_original \
  /caminho/para/as/fotos/
```

### 6.2 Windows (PowerShell)
Navegue até a pasta das fotos e execute:

```powershell
exiftool -r -ext jpg -ext JPG -MPF:all= -trailer:all= -MakerNotes:all= -overwrite_original .
```

---

## 7. Checklist de Validação Pós-Processamento

Após rodar o comando, valide se o arquivo está limpo e pronto para o Google Fotos:

1. **Checagem de MPF:**
   ```bash
   exiftool -MPF:all "IMG_FALHA.JPG"
   ```
   *Resultado esperado:* Nenhuma saída de texto (vazio).

2. **Checagem de Dados Essenciais (Garantir que não perdeu informações):**
   ```bash
   exiftool -DateTimeOriginal -Make -Model -ExposureTime -FNumber -ISO -FocalLength "IMG_FALHA.JPG"
   ```
   *Resultado esperado:* Todas as informações fotográficas continuam presentes:
   * Data/Hora de captura (mantém a linha do tempo do Google Fotos correta).
   * Canon PowerShot SX60 HS.
   * Parâmetros de exposição.

3. **Reenvio para o Google Fotos:**
   Exclua a foto incompatível da nuvem (inclusive da lixeira) e envie a versão sanitizada. O Google Fotos executará a transcodificação normalmente, reduzindo o arquivo para o formato econômico de ~300 kB sem acusar erro.