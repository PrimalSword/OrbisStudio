# OrbisStudio

OrbisStudio é um laboratório de engenharia de firmware Android voltado inicialmente ao projetor HY300/H713. O objetivo é oferecer um fluxo reproduzível para:

1. importar e preservar uma imagem física original;
2. mapear GPT e Android Dynamic Partitions;
3. extrair e inspecionar partições EXT4;
4. aplicar alterações somente em uma árvore de trabalho;
5. reconstruir imagens lógicas e `super.img` em cópias;
6. validar estrutura, hashes e AVB antes de qualquer gravação no aparelho.

## Estado do projeto

O repositório começa com uma base única e permanente. Não haverá mais pacotes descartáveis por versão. Cada avanço entra como commit neste repositório.

O código inicial inclui:

- modelo de projeto e diretórios `Stock`, `Work`, `Build` e `Reports`;
- parser GPT;
- parser de metadata LP baseado em perfis exportados;
- comparação `Stock × Work`;
- injeção segura de arquivos modificados em imagens EXT4 por backend selecionável;
- reconstrução de `super.img` preservando a metadata LP original;
- validação por SHA-256;
- CLI unificada;
- testes automatizados.

## Segurança

O projeto nunca deve alterar a imagem física original. Flash permanece fora do fluxo padrão e somente será habilitado após validação explícita de AVB, rollback e método de recuperação.

## Instalação para desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Uso inicial

```bash
orbis init --project C:\OrbisOS\Room
orbis inspect-gpt --image C:\OrbisOS\Backup\mmcblk0.img
orbis diff --project C:\OrbisOS\Room
orbis preflight --project C:\OrbisOS\Room --logical C:\OrbisOS\Backup\Extracted\Logical --physical C:\OrbisOS\Backup\Images
```

A documentação técnica está em `docs/`.
