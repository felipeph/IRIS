# IRIS - Assistente Integrado de Mídia :camera::rocket:

IRIS é uma central de automação e gerenciamento local para fluxos de fotografia e filmagem. Seu objetivo principal é simplificar e assegurar o processo inicial de transferência (ingestão) de mídias de cartões SD ou discos externos para um armazenamento de destino de forma totalmente segura.

## Principais Recursos

- **Ingestão Segura (Copy & Verify):** Copia arquivos utilizando cálculo de hash (`xxhash`) *on-the-fly* simultaneamente com a cópia. Depois verifica o hash no destino lendo os dados gravados do disco para garantir 100% de integridade.
- **Tolerância a Falhas:** Registra o progresso dos arquivos copiados em um banco de dados local SQLite (no nível do projeto). Caso o processo seja interrompido, ele pode ser retomado exatamente de onde parou, sem copiar os mesmos arquivos duas vezes.
- **Extensível em Etapas (Pipelines):** Arquitetura plugável por "stages". Atualmente focado na Ingestão, com capacidade de estender para rotinas de limpeza, deduplicação e compressão.
- **Progresso Interativo no Terminal:** UI Rica no terminal utilizando a biblioteca `rich`, com tempo estimado, velocidade de cópia e status do ambiente.

## Como usar

### Pré-requisitos
- Python 3.10+
- Instalar dependências a partir do `requirements.txt`:
```bash
pip install -r iris/requirements.txt
```

### Configuração
1. Copie o arquivo `iris/config.example.yaml` para `iris/config.yaml` e ajuste as variáveis de origem e destino padrão conforme suas necessidades (ex: mapeando para a raiz do seu drive de fotografia).
2. O IRIS irá criar automaticamente diretórios locais e configurações globais (como logs e banco de dados SQLite central) na pasta `.iris` dentro da raiz do usuário do sistema (`~/.iris/`).

### Rodando a Aplicação
Inicie a CLI interativa pelo script principal:
```bash
python iris/main.py
```
Um menu interativo aparecerá. Escolha se deseja iniciar um novo projeto (onde você pode nomeá-lo e indicar o diretório de origem do cartão de memória) ou se prefere retomar a cópia de um projeto anterior.

## Estrutura do Código

- `iris/main.py`: O ponto de entrada principal do projeto (CLI com `rich`).
- `iris/src/core/`: Componentes centrais do sistema.
  - `config.py`: Gerenciamento unificado de configuração do projeto.
  - `pipeline.py`: O "executor" responsável por encadear as etapas do workflow.
  - `project.py`: Modelagem do projeto (estado SQLite de cada job de ingestão).
  - `logger.py`: Serviço de logger.
- `iris/src/modules/ingestion/`: Módulo de ingestão que inclui a lógica avançada de cópia com verificação de hash e flush físico.
- `iris/tests/`: Bateria de testes automatizados unitários usando `pytest`.

## Licença
Este é um projeto pessoal open-source. Sinta-se livre para adaptar para seus próprios fluxos de backup.
