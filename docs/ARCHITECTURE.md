# Arquitetura do OrbisStudio

## Princípios

1. A imagem física original é somente leitura.
2. Toda modificação ocorre em cópias versionadas.
3. Cada artefato gerado possui manifesto e SHA-256.
4. O fluxo de build é separado do fluxo de flash.
5. Flash permanece bloqueado enquanto AVB, rollback e recuperação não estiverem validados.

## Camadas

### `gpt.py`

Valida o cabeçalho GPT e a tabela de entradas por CRC32, retornando offsets e tamanhos absolutos.

### `lp.py`

Consome metadata LP exportada e transforma partições lógicas lineares em extents absolutos dentro de `super.img`.

### `diff.py`

Compara `Stock` e `Work` por tamanho e SHA-256. O resultado determina quais partições ficaram sujas.

### `super_builder.py`

Cria uma cópia de `super.img`, injeta imagens lógicas nos extents originais e verifica byte a byte por SHA-256. A metadata LP não é regenerada nesta fase.

## Próximos motores permanentes

- leitor e escritor EXT4 com preservação de inode e xattrs;
- parser e verificador AVB/vbmeta;
- parser de boot/vendor_boot/dtbo;
- validador do perfil HY300/H713;
- frontend desktop sobre a mesma API de domínio.

Nenhuma dessas etapas deve gerar outro projeto descartável. Todas serão incorporadas a este repositório.
