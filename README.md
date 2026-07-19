# OrbisStudio

OrbisStudio é um laboratório de engenharia de firmware Android voltado inicialmente ao projetor HY300/H713. O fluxo preserva a imagem física original e trabalha somente sobre cópias verificáveis.

## Capacidades atuais

- parser GPT com CRC;
- leitura de metadata LP por perfil;
- extração e remontagem lógica de `super.img` preservando extents;
- comparação `Stock × Work` por SHA-256;
- edição transacional de imagens EXT4 com `debugfs`;
- extração e verificação pós-gravação de arquivos EXT4;
- leitura, validação, conversão raw→sparse e sparse→raw;
- inspeção e verificação AVB por `avbtool`;
- pipeline JSON integrado para EXT4 → sparse → super → AVB;
- manifestos e relatórios reproduzíveis;
- bootstrap gerenciado da toolchain em Windows, Linux e macOS;
- testes automatizados, lint e tipagem estática.

## Instalação no Windows

Abra o PowerShell dentro da pasta clonada do projeto:

```powershell
git clone https://github.com/PrimalSword/OrbisStudio.git
cd OrbisStudio
py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Instale as ferramentas portáteis gerenciadas e gere o diagnóstico:

```powershell
orbis setup
orbis doctor
```

O bootstrap baixa scripts oficiais do AOSP para `~/.orbisstudio/tools`, cria launchers locais e registra origem e SHA-256 em `toolchain.lock.json`. A pasta pode ser alterada com `--tools-dir` ou pela variável `ORBIS_TOOLS`.

Nesta versão, `avbtool`, `mkbootimg`, `unpack_bootimg` e `mkdtimg` são instalados automaticamente. Ferramentas que exigem binários nativos — como `lpunpack`, `lpmake`, `dtc`, `payload_generator` e `brillo_update_payload` — são detectadas e reportadas pelo `doctor`, mas ainda não são baixadas automaticamente.

Nas próximas atualizações:

```powershell
cd C:\caminho\OrbisStudio
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check src tests
pytest -q
mypy src
```

## Comandos principais

```powershell
orbis setup
orbis doctor
orbis inspect-gpt --image Backup\mmcblk0.img
orbis ext4-inspect --image Backup\Extracted\Logical\system_a.img
orbis ext4-build --image system_a.img --output system_a_orbis.img --replace novo.apk=/system/app/App/App.apk
orbis sparse --image system_a_orbis.img --output system_a_orbis.sparse.img
orbis unsparse --image system_a_orbis.sparse.img --output system_a_restored.img
orbis avb-info --image vbmeta_a.img
orbis avb-verify --image vbmeta_a.img
orbis build --plan profiles\hy300\build-plan.example.json
```

## Build plan

O arquivo `profiles/hy300/build-plan.example.json` reúne em uma única execução:

1. cópia/edição das imagens lógicas;
2. verificação das substituições EXT4;
3. geração opcional de sparse images;
4. reconstrução de `super.img`;
5. verificação AVB opcional;
6. emissão de relatório JSON.

Ajuste os caminhos do exemplo para a pasta real do backup antes de executar.

## Segurança

A imagem física original nunca é alterada. Os módulos recusam sobrescrever a origem e usam arquivos temporários antes da substituição atômica da saída. O bootstrap não altera o `PATH` global do Windows e registra a origem e o hash local das ferramentas gerenciadas. Flash continua deliberadamente fora do fluxo padrão até que boot, AVB, rollback e recuperação estejam validados no hardware.

## Limites atuais

O suporte ao HY300 ainda depende de ferramentas nativas para manipulação completa de partições dinâmicas, Device Tree e OTA A/B. A emulação integral do Allwinner H713 não está disponível; as validações sem hardware cobrem estrutura, hashes, EXT4, sparse, LP e AVB, mas não substituem um teste final controlado no aparelho.
