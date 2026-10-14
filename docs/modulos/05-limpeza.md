# Módulo 05: Limpeza Segura da Origem (`cleanup`)

O estágio de Limpeza (`CleanupStage`) tem a missão de liberar espaço no cartão de memória ou disco de origem, garantindo que nenhum arquivo seja apagado sem comprovação matemática de que sua cópia está 100% íntegra no destino.

---

## 1. Condições Rígidas de Disparo

A limpeza da origem nunca é executada de forma cega. Ela exige que todas as seguintes pré-condições sejam satisfeitas:

1. **Habilitação de Configuração ou Flag de Projeto:**
   - Parâmetro global `modules.cleanup.auto_clean: true` no `config.yaml`, OU
   - Confirmação explícita do usuário na CLI interativa ao iniciar o projeto (opção de atalho `[L]`).
2. **Validação Relacional no Banco de Dados SQLite:**
   O estágio executa uma checagem rigorosa na tabela `files`:
   ```sql
   SELECT COUNT(*) FROM files WHERE verified = 0;
   ```
   Se houver **qualquer arquivo** com `verified == 0`, a limpeza é imediatamente cancelada com erro crítico.
3. **Existência Física no Destino:**
   O IRIS verifica se os arquivos apontados na coluna `staging_path` ou `final_path` continuam existindo fisicamente no SSD com o tamanho correto em bytes.

---

## 2. Envio Seguro para a Lixeira (`Send2Trash`)

Por padrão, o IRIS não utiliza a função destrutiva imediata `os.unlink()` nem comandos de baixo nível como `del` ou `rm`.

O sistema emprega a biblioteca multiplataforma `send2trash`:
- **No Windows:** O arquivo original é movido para a Lixeira do Windows daquele volume, preservando metadados de exclusão e permitindo que o usuário restaure qualquer arquivo com um simples clique direito se mudar de ideia.
- **No macOS/Linux:** O arquivo é transferido para a pasta de lixeira do usuário (`~/.local/share/Trash`).

---

## 3. Remoção de Diretórios Vazios Residuais

Após mover com segurança os arquivos válidos para a lixeira, o `CleanupStage` realiza uma varredura reversa (bottom-up) nas pastas de origem (como `DCIM/100CANON` ou subpastas de timelapses):
- Se uma pasta estiver completamente vazia, ela é removida do cartão SD.
- Se uma pasta ainda contiver arquivos não reconhecidos (ex.: um arquivo de texto de anotações ou arquivo oculto de sistema), ela é **preservada intacta**, evitando qualquer exclusão não intencional.
