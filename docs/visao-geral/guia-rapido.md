# Visão Geral: Guia de Início Rápido (Quickstart)

Este guia orienta a instalação do ambiente, a primeira configuração do IRIS e os passos para executar tanto o pipeline interativo de ingestão quanto o pipeline astronômico autônomo.

---

## 1. Pré-Requisitos do Sistema

- **Sistema Operacional:** Windows 10/11 (ou Linux x86_64).
- **Python:** Versão 3.10 ou superior (testado e homologado em Python 3.11 e Python 3.13).
- **Ferramentas Externas Recomendadas:**
  - **FFmpeg (com suporte a GPU):** Adicionado ao `PATH` do sistema (`ffmpeg.exe` e `ffprobe.exe`).
  - **Phil Harvey's ExifTool:** Adicionado ao `PATH` (`exiftool.exe`) para a sanitização de metadados.

---

## 2. Instalação Passo a Passo

### Clonando o Repositório
```bash
git clone https://github.com/felipeph/IRIS.git
cd IRIS
```

### Criando e Ativando o Ambiente Virtual (Recomendado)
```bash
python -m venv .venv
# No Windows PowerShell:
.venv\Scripts\Activate.ps1
# No Linux/macOS:
source .venv/bin/activate
```

### Instalando as Dependências
O IRIS separa suas dependências para manter a instalação leve:

1. **Dependências do Core & Pipeline Padrão:**
   ```bash
   pip install -r iris/requirements.txt
   ```
   *Instala bibliotecas fundamentais como `rich`, `pyyaml` e `xxhash`.*

2. **Dependências do Módulo de Astrofotografia (Opcional, porém recomendado):**
   ```bash
   pip install -r iris/requirements-astro.txt
   ```
   *Instala motores científicos como `numpy`, `opencv-python`, `rawpy`, `tifffile`, `scipy`, `scikit-image`, `astropy` e `psutil`.*

3. **Dependências para Edição e Geração Local da Documentação:**
   ```bash
   pip install -r requirements-docs.txt
   ```

---

## 3. Configuração Inicial do Ambiente

1. Crie o seu arquivo de configuração local a partir do modelo fornecido:
   ```powershell
   Copy-Item iris\config.example.yaml iris\config.yaml
   ```

2. Abra o arquivo `iris/config.yaml` e ajuste os diretórios conforme os discos da sua máquina:
   ```yaml
   general:
     default_source: "G:\\DCIM"       # Letra do drive onde o cartão SD costuma ser montado
     destination_root: "C:\\IRIS"     # Diretório raiz no SSD para o staging e organização
     log_level: "INFO"
   ```

> [!NOTE]
> Na primeira execução, o IRIS criará automaticamente o diretório global `~/.iris/` na raiz do seu usuário, alocando o banco de dados central (`iris_central.db`) e arquivos de histórico de log.

---

## 4. Rodando o Pipeline Interativo

Inicie a aplicação pelo script mestre:

```bash
python iris/main.py
```

O terminal exibirá o painel principal com opções numeradas:

```text
╭─────────────────────────────────────────────────────────────────────────────╮
│ 📷 IRIS - IMAGING RESOURCES AND INTEGRATION SYSTEM 🚀                       │
│ Central de Processamento de Fotos e Vídeos                                  │
╰─────────────────────────────────────────────────────────────────────────────╯

[1] Iniciar Novo Projeto (Ingestão de Mídias)
[2] Retomar Projeto Existente
[3] Central de Configurações
[4] Executar Pipeline em Lote (Todos os Estágios Ativos)
[0] Sair
```

### Fluxo Típico de Ingestão:
1. Pressione `[1]` para criar um novo projeto.
2. Digite o nome do projeto (ex.: `2026-10-14_Sessao_Passaros`).
3. Confirme o caminho da pasta de origem (ex.: `G:\DCIM\100CANON`).
4. O IRIS iniciará a cópia com verificação de integridade simultânea (`xxHash64`), exibindo barras de progresso multiplexadas com taxa de transferência (MB/s) e estimativa de tempo restante.
5. Ao concluir a ingestão, os estágios subsequentes (Sanitização EXIF, Planejamento, Organização, Timelapses, Edição de Vídeo e YouTube) serão executados sequencialmente conforme habilitados no `config.yaml`.

---

## 5. Rodando o Pipeline de Astrofotografia (`iris-astro`)

Para empilhamento e wavelets em imagens RAW da Lua sem passar pelo menu da CLI geral, utilize o comando autônomo `iris-astro`:

```bash
# Executa apenas o empilhamento autônomo (Stacking com PSS headless)
python iris/src/modules/astro/cli.py stack --input="C:\IRIS\5_Astrofotografia\Lua\2026-10-14"

# Executa o processamento de wavelets em um TIFF já empilhado usando preset equilibrado
python iris/src/modules/astro/cli.py sharpen "C:\caminho\stack.tif" --preset=equilibrado

# Executa todos os 12 presets de sharpening para comparação lado a lado
python iris/src/modules/astro/cli.py sharpen "C:\caminho\stack.tif" --preset=all

# Executa o pipeline de ponta a ponta (Stacking + Sharpening)
python iris/src/modules/astro/cli.py pipeline --input="C:\caminho\raws" --preset=registax_fiel
```
