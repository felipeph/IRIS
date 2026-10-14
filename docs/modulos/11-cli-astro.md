# Módulo 11: CLI Unificada `iris-astro`

Além de operar como um estágio dentro do pipeline completo do IRIS, as ferramentas de astrofotografia lunar podem ser executadas como uma ferramenta autônoma de linha de comando (`iris-astro`).

---

## 1. Ponto de Entrada e Ajuda Geral

A CLI autônoma está localizada em `iris/src/modules/astro/cli.py` e pode ser invocada diretamente via Python:

```bash
python iris/src/modules/astro/cli.py --help
```

### Subcomandos Disponíveis:
- **`stack`**: Executa o pré-processamento de RAWs e o empilhamento multiponto com o PlanetarySystemStacker.
- **`sharpen`**: Executa a aplicação de wavelets À Trous, Limb Guard e filtros em uma imagem TIFF já empilhada.
- **`pipeline`**: Encadeia ambos os passos de ponta a ponta (`stack` seguido de `sharpen`).

---

## 2. Subcomando `stack` (Empilhamento Autônomo)

```bash
python iris/src/modules/astro/cli.py stack --input "C:\Caminho\Para\RAWs" [opções]
```

### Argumentos Principais:
- `--input` *(obrigatório)*: Caminho da pasta contendo os arquivos RAW da Canon (`.CR2`).
- `--output`: Diretório de destino para os TIFFs empilhados (padrão: subpasta `stacked/`).
- `--keep-percents`: Lista de percentuais de seleção (ex.: `--keep-percents 10 25 50`).
- `--align-box`: Tamanho da caixa de alinhamento em pixels (padrão: `64`).
- `--margin`: Margem de segurança em pixels ao redor do disco lunar (padrão: `128`).
- `--timeout`: Tempo limite em segundos para o subprocesso do PSS (padrão: `600`).

---

## 3. Subcomando `sharpen` (Wavelets e Pós-Processamento)

```bash
python iris/src/modules/astro/cli.py sharpen "C:\caminho\imagem_empilhada.tif" [opções]
```

### Argumentos Principais:
- `input_file` *(posicional, obrigatório)*: Caminho para a imagem TIFF de 16-bit resultante do empilhamento.
- `--preset`: Nome do preset desejado (ex.: `registax_fiel`, `registax_pro`, `equilibrado`) ou `all` para processar todos os 12 presets disponíveis de uma só vez.
- `--no-limb-guard`: Desabilita a máscara de proteção do limbo lunar.
- `--no-clahe`: Desabilita a equalização adaptativa de histograma em 16-bit.
- `--levels`: Número de níveis de wavelets À Trous (padrão: `5`).

---

## 4. Subcomando `pipeline` (Execução de Ponta a Ponta)

Permite passar uma pasta com fotos RAW e obter a galeria final de imagens processadas sem intervenção humana:

```bash
python iris/src/modules/astro/cli.py pipeline --input "C:\Sessao_Lua_RAWs" --preset registax_pro
```

Ao término, o sistema emite notificações na área de trabalho do Windows e envia mensagem via NTFY caso configurado no `config.yaml`.
