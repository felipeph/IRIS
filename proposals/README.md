# IRIS — Catálogo de Propostas de Melhoria de Arquitetura, Performance e Segurança (RFCs)

Este diretório reúne as propostas técnicas detalhadas e desmembradas a partir da investigação profunda realizada no código-fonte do **IRIS (Imaging Resources and Integration System)**.

Nenhuma alteração de código foi executada ainda. O objetivo deste material é fornecer a você uma análise cirúrgica de cada gargalo e vulnerabilidade, acompanhada de **múltiplas abordagens de solução com prós e contras**, permitindo uma tomada de decisão consciente no seu próprio ritmo.

---

## Matriz de Prioridade e Impacto

| ID | Arquivo da Proposta | Categoria | Gravidade / Impacto | Complexidade | Status |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **01** | [`01-seguranca-limpeza-sd-unlink-fallback.md`](./01-seguranca-limpeza-sd-unlink-fallback.md) | Segurança | 🔴 Crítica (Risco de Perda de Dados) | Baixa | ✅ Concluída |
| **02** | [`02-seguranca-migracao-destrutiva-drop-table.md`](./02-seguranca-migracao-destrutiva-drop-table.md) | Segurança | 🔴 Crítica (Perda de Histórico) | Baixa | ✅ Concluída |
| **03** | [`03-concorrencia-race-condition-project-lock.md`](./03-concorrencia-race-condition-project-lock.md) | Segurança | 🟠 Alta (Colisão entre Processos) | Baixa | ✅ Concluída |
| **04** | [`04-ingestao-falso-positivo-tamanho-move-strategy.md`](./04-ingestao-falso-positivo-tamanho-move-strategy.md) | Segurança / Integridade | 🟠 Alta (Omissão de Mídias) | Média | ✅ Concluída |
| **05** | [`05-performance-sqlite-commit-churn-batching.md`](./05-performance-sqlite-commit-churn-batching.md) | Performance | 🟠 Alta (Gargalo de I/O em Lote) | Média | ✅ Concluída |
| **06** | [`06-performance-property-items-overhead-leitura.md`](./06-performance-property-items-overhead-leitura.md) | Performance | 🟡 Média (Lentidão no Menu Interativo) | Baixa | ✅ Concluída |
| **07** | [`07-performance-ffprobe-exiftool-subprocessos.md`](./07-performance-ffprobe-exiftool-subprocessos.md) | Performance | 🟡 Média (Latência de Subprocessos) | Baixa | ✅ Concluída |
| **08** | [`08-arquitetura-dual-sqlite-dessincronizacao.md`](./08-arquitetura-dual-sqlite-dessincronizacao.md) | Arquitetura | 🟠 Alta (Inconsistência de Estado) | Alta | ✅ Concluída |
| **09** | [`09-arquitetura-decomposicao-god-object-project.md`](./09-arquitetura-decomposicao-god-object-project.md) | Arquitetura | 🟡 Média (Manutenibilidade & SOLID) | Alta | ✅ Concluída |
| **10** | [`10-arquitetura-acoplamento-rich-ui-regras-negocio.md`](./10-arquitetura-acoplamento-rich-ui-regras-negocio.md) | Arquitetura | 🟡 Média (Testabilidade & Headless) | Média | ✅ Concluída |
| **11** | [`11-classificacao-heuristicas-rigidas-camera.md`](./11-classificacao-heuristicas-rigidas-camera.md) | Regra de Negócio | 🟡 Média (Falso Positivo de Astro) | Baixa | ✅ Concluída |
| **12** | [`12-portabilidade-caminhos-hardcoded-ambiente.md`](./12-portabilidade-caminhos-hardcoded-ambiente.md) | Portabilidade | 🟡 Média (Acoplamento de Máquina) | Baixa | ✅ Concluída |

---

## Sumário Executivo das Propostas

### 🛡️ Segurança e Prevenção de Perda de Dados
1. **[01. Fallback Silencioso para `unlink()` na Limpeza do SD](./01-seguranca-limpeza-sd-unlink-fallback.md)**: Evita a deleção permanente não autorizada de mídias na origem (cartões SD e pendrives) decorrente da ausência de suporte à Lixeira do Windows em unidades removíveis.
2. **[02. Migração Destrutiva com `DROP TABLE` em Projetos Anteriores](./02-seguranca-migracao-destrutiva-drop-table.md)**: Elimina o comando `DROP TABLE items` disparado na detecção da coluna legada `metadata_json`, preservando bases existentes.
3. **[03. Race Condition (TOCTOU) no `ProjectLock`](./03-concorrencia-race-condition-project-lock.md)**: Corrige a sobreposição atômica de locks via `os.replace`, garantindo que duas instâncias concorrentes não executem o mesmo projeto.
4. **[04. Falso Positivo de Arquivo Idêntico por Tamanho em Bytes](./04-ingestao-falso-positivo-tamanho-move-strategy.md)**: Corrige a presunção equivocada de que dois arquivos de mesmo tamanho em bytes são o mesmo arquivo, prevenindo o abandono de fotos na ingestão.

### ⚡ Performance & Otimização de I/O
5. **[05. Commit Churn no SQLite & Batching com `executemany`](./05-performance-sqlite-commit-churn-batching.md)**: Substitui inserções com commits unitários e DDLs repetidas por transações em lote agrupadas, reduzindo o tempo de persistência em mais de 100x.
6. **[06. Overhead de Leitura e Deserialização na Property `project.items`](./06-performance-property-items-overhead-leitura.md)**: Elimina o `SELECT *` e instanciação desnecessária de dataclasses apenas para verificar a contagem de mídias no menu principal.
7. **[07. Explosão de Subprocessos `ffprobe` e `exiftool`](./07-performance-ffprobe-exiftool-subprocessos.md)**: Consolida a extração de resolução e duração de vídeos em uma única invocação do `ffprobe` por arquivo, eliminando latência de processo no Windows.

### 🏛️ Arquitetura, Design & Manutenibilidade
8. **[08. Sincronização e Reconciliação do Duplo Banco SQLite](./08-arquitetura-dual-sqlite-dessincronizacao.md)**: Resolve a vulnerabilidade de descompasso de dados entre o banco local (`{projeto}.db`) e o banco central (`iris_central.db`).
9. **[09. Decomposição do God Object `Project` (1.272 linhas)](./09-arquitetura-decomposicao-god-object-project.md)**: Separa regras de domínio, DDL de tabelas e repositórios de acesso a dados em módulos coesos e desacoplados.
10. **[10. Desacoplamento da Interface Rich das Estratégias de Negócio](./10-arquitetura-acoplamento-rich-ui-regras-negocio.md)**: Introduz padrão de notificação desacoplada (`ProgressReporter`) para viabilizar execução headless, automações em segundo plano e testes unitários limpos.
11. **[11. Heurísticas Rígidas de Modelo de Câmera na Classificação](./11-classificacao-heuristicas-rigidas-camera.md)**: Remove o hardcode que força fotos RAW diurnas de Canon SX50/SX60 a serem classificadas como astrofotografia lunar.
12. **[12. Portabilidade e Caminhos Hardcoded no Módulo Astro](./12-portabilidade-caminhos-hardcoded-ambiente.md)**: Elimina referências a pastas absolutas da máquina de desenvolvimento (`C:/code/FOTOGRAFIA/...`), adotando resolução dinâmica.

---

## Como Navegar e Decidir

Cada arquivo de proposta possui a seguinte estrutura padronizada:
- **Descrição do Problema**: Localização exata no código, trecho problemático e causa-raiz.
- **Impacto & Riscos**: Cenários práticos onde o problema se manifesta.
- **Abordagens Propostas**:
  - *Abordagem A* (Mínima intervenção / Correção pontual)
  - *Abordagem B* (Abordagem equilibrada / Padrão da indústria)
  - *Abordagem C* (Abordagem arquitetural de longo prazo)
- **Comparativo e Recomendação**: Tabela comparativa e indicação da melhor opção para o perfil do IRIS.
- **Exemplo de Implementação**: Código de exemplo com diff ou snippets prontos para uso.
