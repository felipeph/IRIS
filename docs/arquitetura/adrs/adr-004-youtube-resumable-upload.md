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

Implementamos um cliente de upload customizado baseado na **YouTube Data API v3** com suporte formal a **Resumable Upload em Chunks de 64MB** (configurável via `modules.youtube.chunk_size_mb`):
1. O uploader solicita uma URI de sessão de upload ao endpoint do Google informando o tamanho total do arquivo e os metadados iniciais.
2. O arquivo de vídeo é transmitido em blocos sequenciais (*chunks*) de 67.108.864 bytes (64MB), atendendo estritamente à exigência da API do Google (múltiplos exatos de 256 KB = 256 blocos).
3. A cada chunk concluído, a resposta HTTP `308 Resume Incomplete` retorna o intervalo de bytes recebidos com sucesso pelo servidor (`Range: bytes=0-XXXXX`).
4. Uma barra de progresso da biblioteca `rich` é atualizada dinamicamente com velocidade de upload (MB/s), bytes transmitidos e tempo estimado restante (ETA).
5. Em caso de erro temporário de rede (`5xx` ou desconexão de socket), o sistema aplica backoff exponencial com até 5 tentativas, retomando a transmissão exatamente do byte onde houve a interrupção.

---

## Consequências

- **Positivas:**
  - Maximização do throughput em conexões de banda larga modernas (100Mbps a 1Gbps+), reduzindo drasticamente o overhead de centenas de round-trips HTTP/TLS presentes em blocos pequenos (5MB/8MB).
  - Tolerância absoluta a oscilações de rede durante uploads de vídeos de vários gigabytes.
  - Flexibilidade total: o usuário pode personalizar o tamanho do chunk (em MB) via `config.yaml` ou pelo menu interativo do CLI.
  - Experiência de usuário premium no terminal, com métricas precisas de transmissão.

