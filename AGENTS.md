# AGENTS.md

## Objetivo do repositório
Este projeto tem como foco a **análise e tradução de ROM de Nintendo 64 (N64)**.

## Workspace canônico
Para manter consistência entre tarefas, considere como base:
- Pasta de trabalho principal: `work/`
- Banco de dados principal: **SQLite** (no workspace do projeto)
- ROM base: a ROM de referência usada para extração e validação

## Prioridade atual
A prioridade ativa do projeto é:
- **segmentação e tokenização de script**

## Diretrizes obrigatórias para tarefas do Codex
1. **Não inventar semântica para control codes.**
   - Se o significado não estiver confirmado por evidência (dump, engenharia reversa, teste), manter como desconhecido.

2. **Preferir nomes neutros para comandos/control codes.**
   - Exemplo preferencial: `<CMD_8166>`
   - Evitar nomes interpretativos sem comprovação.

3. **Sempre adicionar testes** para mudanças de comportamento, parsing, tokenização, serialização ou normalização.

4. **Sempre atualizar README/docs** ao introduzir comando, marcador, regra de parsing ou convenção nova.

5. **Não misturar escopos**:
   - Tarefas de análise não devem incluir reinserção de script, geração de fonte/font pipeline, ou ajustes de checksum.

6. **Preservar compatibilidade com a ROM base** identificada por:
   - `MD5: 482bdd39ad2574b943db780b12a9bdfb`
   - Mudanças devem manter fluxo, offsets e validações alinhados a essa referência.

## Regra de segurança de conhecimento
Quando houver ambiguidade técnica, documentar hipótese como hipótese e registrar evidências necessárias para confirmação.
