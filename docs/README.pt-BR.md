# Streaming Top Series BR (português)

Job serverless que roda toda manhã e mantém listas públicas no **MDBList** com as novidades da
**Netflix**, da **HBO Max** e do **Prime Video** no Brasil. As notas vêm do **IMDb**, e o TMDB
só é usado quando o IMDb não tem nota:

- **Séries:** uma lista única, a [**StreammySeries**](https://mdblist.com/lists/mestreyodarossi/streammyseries),
  com as 20 séries com episódios mais recentes e boa avaliação de cada serviço.
- **Filmes:** uma lista única, a [**StreammyMovies**](https://mdblist.com/lists/mestreyodarossi/streammymovies),
  com os últimos 20 lançamentos de cada serviço. Os critérios são nota ≥ 5,0, sem filmes sem nota
  e sem comédia.

As listas podem ser usadas no Stremio, no Kodi, no Plex e em outras integrações.

## Como funciona

1. O **EventBridge Scheduler** dispara a Lambda às 06:00 para as séries e às 06:15 para os filmes
   (horário de Brasília).
2. A Lambda consulta o **TMDB**, cujos dados de disponibilidade vêm do JustWatch. Ela busca séries
   do catálogo por assinatura de cada serviço com episódio exibido nos últimos 14 dias. Se não
   houver 20 séries elegíveis, a janela é ampliada (21, 30, 45… até 365 dias) até completar 20.
3. Aplica os critérios:
   - nota IMDb ≥ 6,0, com a do TMDB como fallback, excluindo séries sem nota;
   - sem reality shows;
   - sem as franquias Chicago, Law & Order / Lei & Ordem e NCIS.
4. Ordena pela data do episódio mais recente e depois pela nota, e fica com as 20 primeiras.
5. Calcula a **diferença** em relação à lista atual no MDBList e aplica só as mudanças. Por isso
   a execução é idempotente.
6. Grava um snapshot diário em JSON no **S3**, como trilha de auditoria.

## Destaques de engenharia

- **Arquitetura hexagonal:**
  - o domínio é puro, sem I/O;
  - os casos de uso dependem de portas;
  - os adaptadores são substituíveis.
- **Fail-safe:** se a fonte de dados degradar, nenhuma série é removida. Uma falha em um
  provedor não afeta os outros.
- **Zero dependências em runtime:** o pacote da Lambda é só o código-fonte.
- **Segurança:**
  - segredos ficam no SSM Parameter Store e nunca entram no state do Terraform;
  - IAM com menor privilégio;
  - CI/CD via GitHub OIDC, sem chaves AWS de longa duração.
- **Observabilidade:**
  - logs JSON estruturados;
  - alarmes de erro e de execução não realizada (*dead man's switch*);
  - DLQ.
- **Qualidade:**
  - ruff e mypy no modo estrito;
  - 81 testes com 94% de cobertura;
  - `terraform validate` no CI.

Os detalhes de instalação, configuração e deploy estão no [README principal](../README.md) e no
[runbook](runbook.md).
