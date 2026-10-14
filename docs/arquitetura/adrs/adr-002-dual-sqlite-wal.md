# ADR-002: Arquitetura de Banco de Dados Duplo (SQLite Dual com WAL Mode)

* **Status:** Aprovado e Implementado
* **Data:** 22/09/2026
* **Decisores:** Felipe Heitmann

---

## Contexto

Inicialmente, o rastreamento do progresso dos arquivos utilizava arquivos JSON gravados em disco. Esse modelo apresentava três problemas críticos:
1. Quedas abruptas de energia durante o salvamento corrompiam a árvore JSON inteira, destruindo o histórico da sessão.
2. Em lotes com dezenas de milhares de fotos (comuns em timelapses), o arquivo JSON crescia para mais de 50MB, exigindo parsing lento a cada verificação de item.
3. Não havia atomicidade nem suporte a consultas condicionais rápidas (`SELECT count(*) WHERE verified=1`).

A alternativa clássica seria adotar um servidor de banco de dados tradicional (como PostgreSQL ou MySQL). No entanto, o IRIS é uma aplicação desktop/local executada na máquina pessoal do usuário, e exigir a instalação e manutenção de um serviço de banco de dados em segundo plano aumentaria drasticamente o atrito de uso e consumo de recursos.

---

## Decisão

Adotamos uma arquitetura relacional baseada em **dois níveis de SQLite** operando em **Modo WAL (Write-Ahead Logging)**:
1. **Banco Central (`iris_central.db`)** em `~/.iris/`: Armazena metadados agregados sobre todas as sessões já criadas pelo sistema.
2. **Banco por Projeto (`<projeto>.db`)** na raiz de cada pasta de projeto: Armazena o estado granular arquivo por arquivo com integridade referencial.
3. **Modo WAL (`PRAGMA journal_mode=WAL`)**: Configurado em todas as conexões para permitir que threads leitoras e escritoras coexistam sem bloqueios mútuos.

---

## Consequências

- **Positivas:** 
  - Propriedades ACID completas sem necessidade de instalar servidores externos.
  - Zero corrupção de estado mesmo em desligamentos forçados do computador.
  - Isolamento de falhas: se uma pasta de projeto for corrompida por falha física de hardware, todos os outros projetos permanecem intactos.
  - Portabilidade total: a pasta do projeto pode ser movida para um HD externo levando consigo todo o histórico de hashes, metadados e IDs do YouTube.
- **Cuidados:** Necessidade de habilitar `PRAGMA busy_timeout=5000` para tolerar concorrência leve entre threads.
