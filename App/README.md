# Routrip — Aplicativo Desktop

Aplicativo de roteamento de veículos: extrai endereços de imagens (OCR), geocodifica via
OpenRouteService, otimiza a ordem das visitas com o LKH-3 (ATSP, matriz assimétrica) e
exporta a rota final para o Google Maps.

## Arquitetura

- **Backend**: Python + FastAPI (porta dinâmica, somente 127.0.0.1)
- **Frontend**: React + TypeScript (Vite), servido pelo próprio backend em produção
- **Janela nativa**: pywebview (WebView2)
- **Solver**: `vendor/LKH.exe` (LKH-3.0.14) via arquivos TSPLIB `TYPE: ATSP`
- **OCR**: PyTesseract com Tesseract vendorizado em `vendor/tesseract`

## Requisitos de desenvolvimento

- Python 3.11+ · Node 18+ · Microsoft Edge WebView2 Runtime (já presente em Windows 10/11 atualizados)

## Setup

```powershell
cd App
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
# opcional (embute o OCR na distribuição):
powershell -ExecutionPolicy Bypass -File scripts\get_tesseract.ps1
```

## Desenvolvimento

```powershell
scripts\dev.ps1   # abre uvicorn (:8000) e vite dev (:5173)
```

Acesse http://localhost:5173 no navegador. O proxy do Vite encaminha `/api` para o backend.

Para testar a janela nativa: `cd frontend; npm run build` e depois
`cd ..\backend; ..\.venv\Scripts\python.exe main.py`.

## Distribuição

```powershell
scripts\build.ps1   # gera backend\dist\Routrip\Routrip.exe (pasta onedir)
```

Distribua a pasta `dist\Routrip` inteira (zip). O app **não inclui chave da API**:
cada usuário informa a própria chave gratuita do [openrouteservice.org](https://openrouteservice.org/)
em Configurações. A chave fica salva em `%APPDATA%\Routrip\config.json`.

## Limites do plano gratuito do ORS

- Matriz: ~50×50 locais por requisição → o app limita a **49 paradas + origem**
- Geocodificação: 100 req/min — o autocomplete usa debounce e mínimo de 3 caracteres
