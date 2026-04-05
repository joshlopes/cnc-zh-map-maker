FROM --platform=linux/amd64 tobix/pywine:3.12

ENV WINEDEBUG=-all
ENV PYTHON="wine /opt/wineprefix/drive_c/Python/python.exe"
ENV WINEPREFIX=/opt/wineprefix

# Install Python dependencies via Wine Python (no numpy/Pillow - not needed for GUI)
RUN $PYTHON -m pip install --no-cache-dir \
    setuptools \
    wheel \
    "pyinstaller==6.10.0" \
    anthropic

# Patch PyInstaller: skip hook discovery (subprocess dies under Wine)
RUN PYINSTALLER_INIT=$(find /opt/wineprefix -path "*/PyInstaller/building/build_main.py" -print -quit) && \
    sed -i 's/self\.hookspath += discover_hook_directories()/# self.hookspath += discover_hook_directories()  # patched for Wine/' "$PYINSTALLER_INIT"

# Patch PyInstaller: skip binary dependency scanning (numpy crashes Wine subprocess)
RUN PYINSTALLER_INIT=$(find /opt/wineprefix -path "*/PyInstaller/building/build_main.py" -print -quit) && \
    sed -i 's/self\.binaries\.extend(find_binary_dependencies/# self.binaries.extend(find_binary_dependencies/' "$PYINSTALLER_INIT"

# Copy project files
WORKDIR /app
COPY src/ src/
COPY pyproject.toml .

# Install our package (without numpy/Pillow deps - they're optional for GUI)
RUN $PYTHON -m pip install --no-cache-dir --no-deps .

# Create spec file
RUN cat > zh_map_maker.spec << 'SPEC'
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['src/cnc_zh_map_maker/gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'cnc_zh_map_maker',
        'cnc_zh_map_maker.map_file',
        'cnc_zh_map_maker.builder',
        'cnc_zh_map_maker.binary_io',
        'cnc_zh_map_maker.data_model',
        'cnc_zh_map_maker.refpack',
        'cnc_zh_map_maker.ai_generator',
        'cnc_zh_map_maker.installer',
        'cnc_zh_map_maker.gui',
        'anthropic',
        'anthropic._client',
        'anthropic._base_client',
        'anthropic._streaming',
        'anthropic._response',
        'anthropic.resources',
        'anthropic.resources.messages',
        'anthropic.types',
        'anthropic.types.message',
        'anthropic.types.content_block',
        'anthropic.types.text_block',
        'httpx',
        'httpx._transports',
        'httpx._transports.default',
        'httpcore',
        'httpcore._sync',
        'httpcore._async',
        'certifi',
        'h11',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'sniffio',
        'pydantic',
        'pydantic.main',
        'pydantic.fields',
        'pydantic_core',
        'jiter',
        'distro',
        'idna',
        'docstring_parser',
        'typing_extensions',
        'annotated_types',
        'typing_inspection',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'Pillow', 'matplotlib', 'scipy', 'pandas', 'IPython', 'notebook', 'test', 'unittest'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ZH-Map-Maker',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    windowed=True,
)
SPEC

# Build the exe
RUN $PYTHON -m PyInstaller --noconfirm --log-level WARN zh_map_maker.spec

# Output stage - extract just the exe
FROM scratch AS export
COPY --from=0 /app/dist/ZH-Map-Maker.exe /ZH-Map-Maker.exe
