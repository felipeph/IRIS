# ADR-004: Upload no YouTube em Chunks com Resumable Upload Manual

* **Status:** Aprovado e Implementado
* **Data:** 26/09/2026
* **Decisores:** Felipe Heitmann

---

## Contexto

Os vídeos 4K UHD masterizados gerados pelo IRIS possuem tamanhos consideráveis (frequentemente entre 500MB e 5GB por arquivo).

O envio desses arquivos utilizando métodos convencionais de upload HTTP (POST único) ou wrappers simples de bibliotecas em alto nível apresentava fragilidades:
1. **Quedas de Conexão:** Qualquer oscilação na rede Wi-Fi/Ethernet interrompia o upload aos 90%, forçando o reinício do zero.
2. **Falta de Feedback Visual:** Métodos bloqueantes não expunham o percentual de bytes transmitidos, impedindo a exibição de uma barra de progresso em tempo real na interface Rich.
3. **Limite de Payload:** O Google impõe cotas rigorosas e recomenda explicitamente o protocolo de upload retomável (*Resumable Upload*) para mídias pesadas.

---

## Decisão

Implementamos um cliente de upload customizado baseado na **YouTube Data API v3** com suporte formal a **Resumable Upload em Chunks de 5MB**:
1. O uploader solicita uma URI de sessão de upload ao endpoint do Google informando o tamanho total do arquivo e os metadados iniciais.
2. O arquivo de vídeo é transmitido em blocos sequenciais (*chunks*) de 5.242.880 bytes (5MB).
3. A cada chunk concluído, a resposta HTTP `308 Resume Incomplete` retorna o intervalo de bytes recebidos com sucesso pelo servidor (`Range: bytes=0-XXXXX`).
4. Uma barra de progresso da biblioteca `rich` é atualizada dinamicamente com velocidade de upload (Mbps) e tempo estimado restante.
5. Em caso de erro temporário de rede (`5xx` ou desconexão de socket), o sistema aplica backoff exponencial com até 5 tentativas, retomando a transmissão exatamente do byte onde houve a interrupção.

---

## Consequências

- **Positivas:**
  - Tolerância absoluta a oscilações de rede durante uploads de vídeos de vários gigabytes.
  - Experiência de usuário premium no terminal, com métricas precisas de transmissão.
  - Criação automática de sessões salvas que podem ser continuadas em execuções posteriores.
