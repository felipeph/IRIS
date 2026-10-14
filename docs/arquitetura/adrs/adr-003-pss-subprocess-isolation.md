# ADR-003: Isolamento do PlanetarySystemStacker via Subprocesso e Patches Headless

* **Status:** Aprovado e Implementado
* **Data:** 12/10/2026
* **Decisores:** Felipe Heitmann

---

## Contexto

Para automatizar a etapa de empilhamento de imagens lunares (Astro Stacking), avaliou-se integrar o **PlanetarySystemStacker (PSS)**, uma ferramenta científica de alta performance para alinhamento multiponto por superfície escrita em Python.

Entretanto, o PSS apresentava desafios técnicos severos:
1. **Acoplamento Gráfico:** O PSS foi desenhado originalmente como um software com interface gráfica baseada em PyQt5, exibindo caixas de diálogo modais e barras de progresso na tela do usuário, o que impedia a execução totalmente autônoma em linha de comando (headless).
2. **Questão de Licenciamento:** O PSS é distribuído sob a licença **GNU General Public License v3 (GPL-3)**, que possui cláusulas virais de cópia caso seja importado como módulo no mesmo processo Python de um software com licença permissiva (como o MIT do IRIS).
3. **Instabilidade de Memória:** O PSS aloca arrays NumPy massivos em C++ durante o alinhamento de dezenas de frames RAW. Vazamentos de memória poderiam degradar a estabilidade do IRIS.

---

## Decisão

Adotamos a estratégia de **Vendorização e Isolamento por Subprocesso**:
1. O código-fonte do PSS foi vendorizado em `iris/vendor/PlanetarySystemStacker/`.
2. Desenvolvemos **patches headless cirúrgicos** no código do PSS para desabilitar a inicialização de interfaces gráficas do Qt, suprimir janelas de diálogo e emitir telemetria em formato padronizado no `stdout`.
3. O orquestrador do IRIS (`AstroStackStage` e `worker.py`) dispara o empilhamento exclusivamente via subprocesso do sistema operacional (`subprocess.Popen`), lendo a saída linha a linha com timeout configurável de segurança (padrão de 600 segundos).

---

## Consequências

- **Positivas:**
  - O interpretador principal do IRIS permanece leve, estável e livre de interferências de dependências gráficas pesadas do PyQt5.
  - A separação de processos preserva a conformidade legal da licença MIT do IRIS.
  - Se o empilhador sofrer um estouro de memória ou crash de driver em imagens anômalas, o subprocesso é terminado pelo timeout e o IRIS registra o erro no SQLite sem travar a CLI.
