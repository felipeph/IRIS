# Automação de processamento lunar: alternativas para testar

Este documento reúne as alternativas discutidas para automatizar um fluxo de processamento de imagens RAW da Lua, reduzindo ao mínimo o trabalho manual.

## 1. Objetivo

O fluxo atual é aproximadamente:

```text
RAW da Canon
   ↓
PIPP
   ↓
AutoStakkert!
   ↓
TIFF empilhado
   ↓
RegiStax
   ↓
Wavelets / sharpening
   ↓
Imagem final
```

A meta é transformar esse processo em algo o mais próximo possível de:

```text
processar-lua pasta_com_raws
```

e receber automaticamente os arquivos empilhados e processados.

---

# 2. Estratégia geral de testes

Em vez de trocar todo o fluxo de uma vez, a ideia é testar cada etapa separadamente.

Ordem sugerida:

1. Automatizar apenas os wavelets/sharpening.
2. Automatizar o PIPP.
3. Automatizar o AutoStakkert!.
4. Testar o Strehl apenas na etapa de sharpening.
5. Testar o Strehl no pipeline completo.
6. Comparar os resultados com o fluxo manual atual.
7. Só então escolher o pipeline definitivo.

---

# 3. Alternativa A — manter PIPP + AutoStakkert! + RegiStax

Esta é a opção de menor risco.

O processamento continua usando as ferramentas já conhecidas, mas tenta-se automatizar as etapas repetitivas.

## Fluxo

```text
RAW
 ↓
PIPP
 ↓
AutoStakkert!
 ↓
TIFF
 ↓
RegiStax Batch/Macro
 ↓
Imagem final
```

## Vantagens

- Mantém o resultado já conhecido.
- AutoStakkert! continua responsável pelo stacking.
- RegiStax continua responsável pelos wavelets.
- Menor mudança no fluxo atual.

## Desvantagens

- O RegiStax tem automação limitada.
- O processo continua dependente de programas Windows com interface gráfica.
- Pode ser difícil chegar a um pipeline realmente 100% automático.

---

# 4. Automatizar o PIPP por linha de comando

O PIPP possui um executável chamado `pipp_core.exe`, que pode ser usado por linha de comando.

Exemplo conceitual:

```bat
pipp_core.exe -centre -crop=1000 -join *.CR2
```

Outra possibilidade é utilizar um arquivo de configuração:

```bat
pipp_core.exe -ini=lua.ini *.CR2
```

## Ideia

Criar um arquivo:

```text
lua.ini
```

contendo os parâmetros usados normalmente no PIPP.

Depois:

```bat
pipp_core.exe -ini=lua.ini D:\Lua\Sessao\*.CR2
```

## Possíveis tarefas automatizadas

- leitura dos RAWs;
- centralização da Lua;
- crop;
- ordenação;
- conversão;
- geração de TIFF, AVI ou SER.

## O que testar

Comparar:

```text
PIPP GUI
```

contra:

```text
pipp_core.exe
```

usando exatamente o mesmo conjunto de RAWs.

---

# 5. Automatizar o AutoStakkert! com sessão `.as3`

O AutoStakkert! pode salvar sessões em arquivos:

```text
lua.as3
```

A sessão contém vários parâmetros do processamento.

Uma sessão pode ser aberta por linha de comando:

```bat
AutoStakkert.exe lua.as3
```

## Como criar a sessão

No AutoStakkert!:

1. abrir um conjunto típico de imagens;
2. escolher `Surface`;
3. configurar o Quality Estimator;
4. escolher Noise Robust;
5. escolher porcentagens de stack;
6. definir tamanho dos Alignment Points;
7. executar `Analyse`;
8. gerar os APs;
9. salvar a sessão.

## Exemplo de configuração para teste

```text
Image Stabilization:
    Surface

Quality Estimator:
    Laplacian

Noise Robust:
    4

AP Size:
    64 pixels

Stack:
    10%
    25%
    50%

Output:
    TIFF
```

## Limitação importante

O arquivo `.as3` não é necessariamente apenas uma configuração genérica.

Ele pode conter:

- caminho do arquivo original;
- Alignment Points;
- dados do alinhamento;
- informações dependentes da geometria da imagem.

Portanto, deve-se testar até que ponto uma sessão pode ser reaproveitada.

## Possível estratégia

Usar um `.as3` como template.

Exemplo em Python:

```python
from pathlib import Path
import subprocess

template = Path("template.as3").read_text(encoding="utf-8")

entrada = r"D:\Lua\sessao\lua.ser"

sessao = template.replace(
    r"D:\Lua\MODELO\lua.ser",
    entrada
)

Path("temp.as3").write_text(
    sessao,
    encoding="utf-8"
)

subprocess.run([
    r"C:\AutoStakkert\AutoStakkert.exe",
    "temp.as3"
])
```

## O que testar

- se o AutoStakkert! começa automaticamente;
- se executa análise;
- se preserva os APs;
- se gera os stacks automaticamente;
- quais campos do `.as3` precisam ser modificados.

---

# 6. Automatizar os wavelets do RegiStax

Esta provavelmente é a automação mais simples para testar primeiro.

O RegiStax permite salvar configurações de wavelets.

A ideia é criar alguns presets.

Exemplo:

```text
lua_suave.rwv
lua_normal.rwv
lua_forte.rwv
```

## Estratégia

Para cada TIFF produzido pelo AutoStakkert!, gerar três versões:

```text
stack_25.tif
   ↓
lua_suave.png
lua_normal.png
lua_forte.png
```

Depois basta escolher visualmente a melhor.

## Vantagens

- elimina quase todo o trabalho repetitivo;
- continua usando o sharpening que já é conhecido;
- fácil comparar intensidades diferentes.

## Desvantagens

- automação do RegiStax é antiga;
- nem todas as funções são igualmente fáceis de automatizar;
- pode continuar exigindo alguma interação gráfica.

---

# 7. Alternativa B — AutoStakkert! + `astrosharp`

Uma opção interessante é manter o AutoStakkert! para stacking e substituir apenas o RegiStax.

## Fluxo

```text
RAW
 ↓
PIPP
 ↓
AutoStakkert!
 ↓
TIFF
 ↓
astrosharp
 ↓
Imagem final
```

O `astrosharp` faz parte do projeto Strehl.

Ele implementa:

- wavelets à trous;
- sharpening;
- deconvolução Richardson–Lucy;
- proteção do limbo;
- suporte a debayer.

## Exemplo

```bash
astrosharp stack.tif --method wavelet -o final.png
```

Ou:

```bash
astrosharp stack.tif --method both --limb-guard -o final.png
```

## `--limb-guard`

É especialmente interessante para Lua.

Tenta reduzir artefatos próximos ao limbo, como:

- halos;
- ringing;
- bordas artificiais.

## Batch

No Windows:

```bat
for %%F in (*.tif) do (
    astrosharp "%%F" --method both --limb-guard -o "sharp_%%~nF.png"
)
```

Isso transforma:

```text
Moon_stack_10.tif
Moon_stack_25.tif
Moon_stack_50.tif
```

em:

```text
sharp_Moon_stack_10.png
sharp_Moon_stack_25.png
sharp_Moon_stack_50.png
```

## Estratégia recomendada

Criar três presets:

```text
suave
normal
forte
```

Assim cada stack gera automaticamente três versões.

---

# 8. Alternativa C — Strehl completo

O Strehl tenta substituir o pipeline:

```text
PIPP
+
AutoStakkert!
+
RegiStax
```

por ferramentas de linha de comando.

Os três programas principais são:

```text
astroprep
astrostack
astrosharp
```

---

# 9. `astroprep`

Cumpre aproximadamente o papel do PIPP.

## Possíveis funções

- leitura dos arquivos;
- centralização;
- crop;
- análise de qualidade;
- preparação dos frames;
- leitura de RAW de DSLR.

Exemplo:

```bash
astroprep ./raw_lua/ --profile lunar -o ./prepped/
```

## RAW da Canon

O suporte RAW utiliza `rawpy`.

Isso significa que o pipeline pode potencialmente começar diretamente nos:

```text
.CR2
```

sem precisar converter antes.

---

# 10. `astrostack`

Cumpre aproximadamente o papel do AutoStakkert!.

Exemplo:

```bash
astrostack ./prepped/     --keep-percent 20     --ap-size 64     -o lua_stack.tif
```

## Processo conceitual

```text
frame
 ↓
alinhamento global
 ↓
Alignment Points
 ↓
análise local de qualidade
 ↓
deslocamentos locais
 ↓
seleção dos melhores frames por região
 ↓
campo de deformação
 ↓
stack final
```

Isso é importante porque imagens lunares sofrem deformação atmosférica diferente em partes distintas da imagem.

## Selection por AP

Com:

```bash
--keep-percent 20
```

cada região pode selecionar frames diferentes.

Exemplo conceitual:

```text
Tycho
usa frames 3, 8, 10, 15...
```

enquanto:

```text
Copernicus
usa frames 1, 3, 9, 12...
```

---

# 11. Drizzle no Strehl

Exemplo:

```bash
astrostack ./prepped/     --keep-percent 20     --ap-size 64     --drizzle 2     -o lua_stack.tif
```

Pode ser interessante testar quando a imagem original está subamostrada.

---

# 12. Sigma clipping

Também pode ser testado:

```bash
astrostack ./prepped/     --sigma-clip     -o lua_stack.tif
```

Pode ajudar a reduzir:

- pixels anômalos;
- satélites;
- aviões;
- eventos transitórios.

---

# 13. Presets do Strehl

Uma vantagem importante é a possibilidade de usar arquivos de configuração.

Exemplo:

```text
lua.toml
```

Fluxo:

```bash
astroprep ./raw/ --config lua.toml
astrostack ./prepped/ --config lua.toml
```

Isso é mais adequado para automação do que uma sessão gráfica.

---

# 14. Strehl + RAW Bayer

Uma característica interessante é manter os dados Bayer durante parte do processamento.

Fluxo conceitual:

```text
CR2
 ↓
Bayer RAW
 ↓
alinhamento
 ↓
stack
 ↓
debayer
 ↓
sharpening
```

Exemplo posterior:

```bash
astrosharp stack.tif --debayer
```

A ideia é evitar interpolação RGB desnecessária antes do stacking.

---

# 15. Limitação principal do Strehl

O Strehl ainda deve ser considerado experimental.

Antes de substituir o AutoStakkert!, fazer comparação A/B.

## Pipeline A

```text
CR2
 ↓
PIPP
 ↓
AutoStakkert!
 ↓
TIFF
```

## Pipeline B

```text
CR2
 ↓
astroprep
 ↓
astrostack
 ↓
TIFF
```

Não aplicar sharpening nessa primeira comparação.

---

# 16. Como comparar os stacks

Usar exatamente os mesmos RAWs.

Examinar regiões como:

```text
Tycho
Copernicus
Clavius
Mare Imbrium
limbo lunar
```

Ver a imagem a:

```text
100%
200%
```

Comparar:

- resolução fina;
- microdetalhes;
- nitidez;
- ruído;
- deformações;
- halos;
- ringing;
- duplicação de crateras;
- bordas artificiais;
- artefatos entre Alignment Points.

---

# 17. Alternativa D — sharpening próprio em Python

Outra possibilidade futura é abandonar RegiStax e `astrosharp` e controlar o sharpening diretamente em Python.

Possíveis técnicas:

- Unsharp Mask;
- Laplacian sharpening;
- wavelets;
- Richardson–Lucy;
- Wiener;
- CLAHE;
- curvas;
- contraste local.

## Vantagem

Controle total.

Exemplo conceitual:

```python
stack = carregar_tiff("stack.tif")

stack = wavelet_sharpen(stack)
stack = local_contrast(stack)
stack = ajustar_gamma(stack)

salvar(stack, "final.tif")
```

Também seria possível automatizar parâmetros de acordo com características da imagem.

---

# 18. Pipeline híbrido recomendado para começar

A primeira combinação que vale testar é:

```text
RAW Canon
 ↓
PIPP
 ↓
AutoStakkert!
 ↓
TIFF
 ↓
astrosharp
 ↓
PNG/TIFF final
```

Isso preserva o AutoStakkert!, que é a parte mais crítica e madura do pipeline, enquanto elimina o trabalho manual dos wavelets.

---

# 19. Pipeline automatizado intermediário

Depois:

```text
RAW Canon
 ↓
pipp_core.exe
 ↓
SER
 ↓
AutoStakkert! via .as3
 ↓
TIFF
 ↓
astrosharp
 ↓
imagem final
```

Objetivo:

```bat
processar_lua.bat D:\Lua\2026-09-25
```

---

# 20. Pipeline totalmente CLI

Se o Strehl apresentar resultados bons:

```text
CR2
 ↓
astroprep
 ↓
astrostack
 ↓
astrosharp
 ↓
imagem final
```

Exemplo conceitual:

```bash
astroprep ./raw -o ./prep
astrostack ./prep --keep-percent 20 --ap-size 64 -o stack.tif
astrosharp stack.tif --method both --limb-guard -o final.png
```

---

# 21. Estrutura de pastas sugerida

```text
Astrofotografia/
│
├── configs/
│   ├── pipp/
│   │   └── lua.ini
│   │
│   ├── autostakkert/
│   │   └── lua.as3
│   │
│   └── strehl/
│       └── lua.toml
│
├── presets/
│   ├── lua_suave
│   ├── lua_normal
│   └── lua_forte
│
└── sessoes/
    │
    ├── 2026-09-20/
    │   ├── raw/
    │   ├── prep/
    │   ├── stack/
    │   └── final/
    │
    └── 2026-09-25/
        ├── raw/
        ├── prep/
        ├── stack/
        └── final/
```

---

# 22. Teste 1 — automatizar apenas o sharpening

Entrada:

```text
stack.tif
```

Produzir:

```text
stack_suave.png
stack_normal.png
stack_forte.png
```

Comparar com o processamento manual no RegiStax.

### Resultado

| Critério | RegiStax manual | automático |
|---|---:|---:|
| Nitidez | | |
| Ruído | | |
| Halo | | |
| Microdetalhe | | |
| Tempo gasto | | |
| Trabalho manual | | |

---

# 23. Teste 2 — PIPP CLI

Usar o mesmo conjunto de RAWs.

```text
PIPP GUI
```

versus:

```text
pipp_core.exe
```

Verificar:

- crop;
- centralização;
- ordenação;
- qualidade;
- saída.

---

# 24. Teste 3 — AutoStakkert! `.as3`

Verificar se é possível chegar a:

```bat
AutoStakkert.exe sessao.as3
```

sem interação.

Registrar:

- análise automática;
- APs;
- porcentagens;
- nome dos arquivos de saída;
- necessidade de cliques;
- erros.

---

# 25. Teste 4 — AutoStakkert! + astrosharp

Fluxo:

```text
PIPP
 ↓
AutoStakkert!
 ↓
astrosharp
```

Este provavelmente é o teste com melhor relação entre esforço e benefício.

---

# 26. Teste 5 — Strehl stack vs AutoStakkert!

Usar exatamente a mesma captura.

## AS

```text
RAW
 ↓
PIPP
 ↓
AutoStakkert
```

## Strehl

```text
RAW
 ↓
astroprep
 ↓
astrostack
```

Não aplicar sharpening.

---

# 27. Teste 6 — pipeline completo

Comparar:

## Pipeline clássico

```text
PIPP
 ↓
AutoStakkert!
 ↓
RegiStax
```

## Pipeline híbrido

```text
PIPP
 ↓
AutoStakkert!
 ↓
astrosharp
```

## Pipeline Strehl

```text
astroprep
 ↓
astrostack
 ↓
astrosharp
```

---

# 28. Planilha mental de avaliação

Para cada teste, registrar:

| Pipeline | Qualidade | Artefatos | Tempo | Trabalho manual | Observações |
|---|---:|---:|---:|---:|---|
| PIPP + AS + RegiStax | | | | | |
| PIPP + AS + astrosharp | | | | | |
| Strehl completo | | | | | |
| Python próprio | | | | | |

---

# 29. Meta final

A meta ideal seria algo assim:

```bat
processar_lua.bat D:\Astrofotografia\2026-09-25
```

ou:

```bash
python processar_lua.py D:/Astrofotografia/2026-09-25
```

Executando automaticamente:

```text
1. localizar RAWs
2. pré-processar
3. alinhar
4. selecionar melhores frames
5. empilhar
6. aplicar sharpening
7. gerar versões suave/normal/forte
8. salvar TIFF final
9. salvar PNG de visualização
10. gerar log do processamento
```

---

# 30. Ordem recomendada de experimentação

## Etapa 1

Testar:

```text
AutoStakkert! → astrosharp
```

Objetivo: eliminar o RegiStax manual.

## Etapa 2

Testar:

```text
pipp_core.exe
```

Objetivo: eliminar a interface do PIPP.

## Etapa 3

Testar:

```text
AutoStakkert.exe sessão.as3
```

Objetivo: automatizar stacking.

## Etapa 4

Criar:

```text
processar_lua.bat
```

com:

```text
PIPP CLI
+
AutoStakkert!
+
astrosharp
```

## Etapa 5

Comparar com:

```text
astroprep
+
astrostack
+
astrosharp
```

## Etapa 6

Se o Strehl produzir qualidade equivalente ou superior, considerar migrar o pipeline inteiro.

---

# Conclusão

Há três caminhos principais.

### Conservador

```text
PIPP
+
AutoStakkert!
+
RegiStax batch
```

Menor risco.

### Híbrido

```text
PIPP
+
AutoStakkert!
+
astrosharp
```

Provavelmente o melhor ponto de partida.

### Totalmente automatizado

```text
astroprep
+
astrostack
+
astrosharp
```

Mais elegante para linha de comando e scripts, mas precisa ser validado cuidadosamente contra o AutoStakkert!.

O ideal é manter um conjunto fixo de RAWs como **dataset de benchmark**, processando sempre a mesma captura em cada pipeline. Assim fica possível avaliar objetivamente qual automação realmente preserva ou melhora a qualidade final.
