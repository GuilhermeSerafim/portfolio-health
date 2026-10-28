# portfolio-health

Monitor de disponibilidade das minhas demonstrações públicas. Publica um feed JSON com evidências HTTPS limitadas, prazo de validade explícito e estados que distinguem falha do serviço de verificação inconclusiva. A sondagem não substitui teste funcional ou monitoramento dos produtos privados.

## Demonstração e imagens

[Feed público](https://guilhermeserafim.github.io/portfolio-health/status.json) · [Consumidor no portfólio](https://guiler.vercel.app). Publicação do feed não significa que todos os serviços estejam saudáveis.

## Minha contribuição e autoria

O histórico do repositório registra minha implementação do monitor e seus testes. O contrato torna explícito o que uma sondagem consegue — e não consegue — observar.

## Arquitetura e implementação

A coleta limita destinos, tempo e volume de resposta. Uma evidência expira após 45 minutos; atualizar o horário de geração do arquivo não renova o horário da observação. Mudanças de URL ou receita invalidam a identidade anterior do alvo. GitHub Actions publica somente os artefatos previstos em Pages.

O [contrato](CONTRACT.md) define os estados e a validade; os [testes do monitor](tests/test_monitor.py) cobrem o tratamento dessas evidências.

## Instalação e configuração

Requer Python 3.11 ou superior e curl com suporte a `%{json}`. `monitor.py` consulta os alvos externos configurados.

A implementação usa biblioteca padrão Python. Execute os testes antes de fazer a sondagem externa; `targets.json` controla os alvos permitidos.

```text
python monitor.py
```

## Testes e verificações

Os comandos abaixo documentam a suíte existente; não representam uma execução nova nem um resultado de aprovação.

```text
python -m unittest discover -s tests -v
```

## Limites atuais

- Não verifica banco, APIs privadas, transações ou execução completa do JavaScript.
- Bloqueio automatizado e falta de evidência não devem ser convertidos em falha definitiva de serviço.
- Não fornece SLA, disponibilidade contínua comprovada ou monitoramento completo dos produtos.

<details>
<summary>Referência de uso e documentação complementar</summary>

## Cobertura e critérios de sondagem

- GeoRisk / OrbTalus: demonstração pública sintética.
- SEVEN Tools: demonstração pública com cenários sintéticos.
- Play Senac: demonstração pública com reservas sintéticas; seleciona o módulo `main-`.
- Mesa de Negócios: documento público da landing page e seu módulo de entrada.

As sondagens validam HTTP 200, um marcador HTML esperado e um módulo de entrada da mesma origem. Por padrão, usam o primeiro módulo; um prefixo explícito seleciona a entrada da aplicação quando há um auxiliar antes dela, como os polyfills do Angular. A ausência do módulo selecionado faz a verificação falhar.

Não executam JavaScript, não verificam imports transitivos e não submetem formulários. Os produtos privados e os backends Render não fazem parte dessa cobertura.

Duas falhas de serviço equivalentes produzem `down`; recuperação na segunda tentativa produz `degraded`. Respostas HTTP 401/403, desafios contra bots e limites de requisições são inconclusivos. Consulte o [contrato](CONTRACT.md) e o [JSON Schema](status.schema.json).

## Limites da sondagem e artefatos

O coletor limita a quatro alvos simultâneos, 15 segundos por tentativa, uma repetição após 30 segundos para falha de serviço e 180 segundos de prazo total. Cada resposta é limitada a 2 MiB. Redirecionamentos precisam permanecer em hosts HTTPS revisados, sem credenciais ou parâmetros de consulta. Corpos temporários de resposta são descartados.

`responseTimeMs` mede a sondagem completa, incluindo a espera de repetição quando houver; não é uma pontuação de velocidade da página.

O artefato publicado no Pages contém apenas `status.json`, `status.schema.json` e `.nojekyll`. Logs, corpos de resposta e credenciais não são publicados.

## Operação e agendamento

O workflow solicita verificações nos minutos **03, 18, 33 e 48 UTC**. O GitHub pode atrasar ou não executar um agendamento. Consumidores devem rebaixar observações com mais de 45 minutos para `unknown`.

Edite `targets.json` somente após validar a URL pública final e o caminho seguro de leitura. Mudanças de URL, papel ou receita da sondagem, incluindo `entryScriptPrefix`, produzem um novo `targetId`, impedindo reutilizar sucesso antigo.

É possível declarar manutenção em `maintenance`, com `startsAt`, `endsAt` em UTC ISO e uma mensagem pública curta em `message`.

O workflow serializa coleta e publicação. O histórico opcional de último sucesso vem somente do snapshot público anterior do mesmo alvo. Se estiver indisponível, permanece nulo; nenhum horário é inventado.

Revise periodicamente Actions, Pages e a atividade do repositório. O GitHub pode desativar agendamentos após 60 dias sem atividade. Um `workflow_dispatch` manual comprova publicação, não o funcionamento do agendador. Referências: [agendamento no GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) e [limites do Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).

</details>
