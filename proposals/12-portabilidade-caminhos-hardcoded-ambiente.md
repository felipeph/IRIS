# Proposta 12: Portabilidade, Resolução Dinâmica de Ambientes e Remoção de Caminhos Hardcoded

> **Status**: ✅ **Implementada (Abordagens A e B: Resolução Relativa Estrita + Env Vars)**  
> **Data de Conclusão**: 19/10/2026  
> **Branch**: `feat/implement-pending-proposals`

## Contexto e Localização do Problema

- **Arquivos Afetados**:
  - [`src/modules/astro_stack/runner.py`](file:///c:/code/IRIS/iris/src/modules/astro_stack/runner.py#L41)
  - [`src/modules/astro_stack/worker.py`](file:///c:/code/IRIS/iris/src/modules/astro_stack/worker.py#L78-L79)
  - [`src/core/metadata.py`](file:///c:/code/IRIS/iris/src/core/metadata.py#L260)
  - [`src/modules/sanitization/stage.py`](file:///c:/code/IRIS/iris/src/modules/sanitization/stage.py#L24)
- **Princípio Afetado**: **Portabilidade, Reprodutibilidade e Isolamento de Ambiente**

### Exemplos de Caminhos Hardcoded Encontrados

Em `src/modules/astro_stack/runner.py`:
```python
candidates = [
    MODULE_DIR.parents[2] / ".venv_astro" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
    Path.home() / ".iris" / "astro_venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
    Path("C:/code/FOTOGRAFIA/pipp-core-test/pss/.venv/Scripts/python.exe"),  # <-- Caminho pessoal de outra pasta/projeto!
]
```

Em `src/modules/astro_stack/worker.py`:
```python
candidates = [
    MODULE_DIR.parents[2] / "vendor" / "PlanetarySystemStacker",
    Path("C:/code/IRIS/iris/vendor/PlanetarySystemStacker"),
    Path("C:/code/FOTOGRAFIA/pipp-core-test/pss"),  # <-- Caminho pessoal de máquina específica
]
```

Em `src/core/metadata.py` e `src/modules/sanitization/stage.py`:
```python
exiftool_bin = shutil.which("exiftool") or ("C:\\Windows\\exiftool.exe" if Path("C:\\Windows\\exiftool.exe").exists() else None)
```

---

## Diagnóstico da Causa-Raiz

1. **Acoplamento a Estruturas de Pastas Pessoais de Desenvolvimento**:
   - O caminho `C:/code/FOTOGRAFIA/pipp-core-test/pss` faz referência a um repositório de testes antigo e isolado na máquina do desenvolvedor.
   - Se o projeto for clonado em um notebook, em outro diretório (ex: `D:\IRIS`), ou se a pasta `pipp-core-test` for limpa/deletada, a busca por dependências do módulo de astrofotografia pode falhar ou tentar carregar binários antigos/incompatíveis.

2. **Suposições Rígidas de Instalação no Windows**:
   - Checar explicitamente `C:\Windows\exiftool.exe` não é recomendado (muitas pessoas instalam o ExifTool via Chocolatey em `C:\ProgramData\chocolatey\bin`, via Scoop em `~/scoop/shims`, ou pelo winget). O `shutil.which("exiftool")` já cobre todos esses casos desde que o utilitário esteja no `PATH` do sistema.

---

## Abordagens de Solução

### Abordagem A: "Resolução Relativa Estrita Ancorada em `PROJECT_ROOT`" (Recomendada)
**Conceito**: Eliminar todos os caminhos com strings absolutas como `C:/code/...`. Todas as buscas por arquivos do projeto devem ser 100% relativas à constante `PROJECT_ROOT` definida em `src/core/config.py`:
- Vendor do PSS: `PROJECT_ROOT / "vendor" / "PlanetarySystemStacker"`
- Virtualenv local de Astro: `PROJECT_ROOT / ".venv_astro"`
- Virtualenv global de usuário: `Path.home() / ".iris" / "astro_venv"`
- Binários externos (`exiftool`, `ffmpeg`, `ffprobe`): Exclusivamente via `shutil.which()`.

- **Vantagens**:
  - O repositório torna-se 100% portátil e independente de onde estiver clonado.
  - Elimina código fantasma referenciando projetos antigos.
- **Desvantagens**:
  - Nenhuma.

---

### Abordagem B: "Variáveis de Ambiente com Arquivo `.env`"
**Conceito**: Permitir sobrescrever caminhos via variáveis de ambiente padrão:
- `IRIS_ASTRO_PYTHON`: Caminho personalizado para o Python do módulo astro.
- `IRIS_PSS_VENDOR_DIR`: Caminho alternativo para o código-fonte do PSS.
- `IRIS_EXIFTOOL_PATH`: Caminho explícito para o binário do ExifTool.

- **Vantagens**:
  - Excelente para usuários avançados ou pipelines de CI/CD em servidores onde os binários ficam em locais atípicos.
- **Desvantagens**:
  - Exige documentar as variáveis de ambiente adicionais.

---

### Abordagem C: "Comando de Autodiagnóstico (`iris doctor`)"
**Conceito**: Implementar uma verificação de saúde pré-voo (`iris doctor` ou checagem na inicialização) que valida visualmente a presença e versão de cada binário dependente (`exiftool`, `ffmpeg`, `ffprobe`, `python_astro`, `rawpy`, `tifffile`), exibindo um painel Rich com status verde/vermelho e instruções claras de instalação se algo faltar.

- **Vantagens**:
  - Experiência de usuário profissional e amigável.
  - Resolve problemas de configuração antes de iniciar um processamento demorado.
- **Desvantagens**:
  - Requer implementar a UI da tela de diagnóstico.

---

## Tabela Comparativa

| Critério | Atual (Hardcoded) | Abordagem A (Relativa a Root) | Abordagem B (Env Vars) | Abordagem C (`iris doctor`) |
| :--- | :---: | :---: | :---: | :---: |
| **Portabilidade em Outro PC** | 🔴 Quebra ou busca lixo | 🟢 100% Portátil | 🟢 100% Portátil | 🟢 100% Portátil |
| **Transparência p/ o Usuário** | ❌ Oculta erros | 🟢 Automática | ⚠️ Requer Config | 🟢 Diagnóstico Visual |
| **Complexidade** | — | Baixa (limpar 5 linhas) | Baixa (10 linhas) | Média (40 linhas) |

---

## Implementação Recomendada (União de A + B)

```python
# Em src/modules/astro_stack/runner.py

from src.core.config import PROJECT_ROOT, config

def find_astro_python() -> Optional[Path]:
    # 1. Variável de ambiente explícita
    env_py = os.getenv("IRIS_ASTRO_PYTHON")
    if env_py and Path(env_py).exists():
        return Path(env_py)

    # 2. Configurado no config.yaml
    configured_py = config.get("modules.astro_stack.python_path")
    if configured_py and Path(configured_py).exists():
        return Path(configured_py)

    configured_venv = config.get("modules.astro_stack.venv_path")
    if configured_venv and configured_venv != "auto":
        p = Path(configured_venv)
        exe = p / "Scripts" / "python.exe" if sys.platform == "win32" else p / "bin" / "python"
        if exe.exists():
            return exe

    # 3. Candidatos padrão ancorados em PROJECT_ROOT e no Home do usuário
    exe_name = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    candidates = [
        PROJECT_ROOT / ".venv_astro" / exe_name,
        Path.home() / ".iris" / "astro_venv" / exe_name,
    ]

    for cand in candidates:
        if cand.exists():
            return cand

    # 4. Fallback para o interpretador atual se tiver as dependências instaladas
    try:
        import PyQt5, tifffile, cv2
        return Path(sys.executable)
    except ImportError:
        pass

    return None
```
