# Routrip — Aplicativo Desktop

Aplicativo de roteamento de veículos: extrai endereços de imagens e PDFs (OCR) ou de
planilhas (.xlsx / CSV, com escolha das colunas), geocodifica via OpenRouteService,
otimiza a ordem das visitas com o LKH-3 (ATSP, matriz assimétrica) e exporta a rota
final para o Google Maps.

## Arquitetura

- **Backend**: Python + FastAPI (porta dinâmica, somente 127.0.0.1)
- **Frontend**: React + TypeScript (Vite), servido pelo próprio backend em produção
- **Janela nativa**: pywebview (WebView2)
- **Solver**: `vendor/LKH.exe` (LKH-3.0.14) via arquivos TSPLIB `TYPE: ATSP`
- **OCR**: RapidOCR (PP-OCR em ONNX, via onnxruntime) com os modelos em `vendor/ocr`; roda in-process, sem binário externo
- **PDF**: pypdfium2 — usa a camada de texto quando existe e rasteriza a página para OCR quando o PDF é escaneado

## Requisitos de desenvolvimento

- Python 3.11+ · Node 18+ · Microsoft Edge WebView2 Runtime (já presente em Windows 10/11 atualizados)

## Setup

```powershell
cd App
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
# baixa os modelos de OCR (necessário para ler imagens):
powershell -ExecutionPolicy Bypass -File scripts\get_ocr_models.ps1
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
scripts\build.ps1                       # gera backend\dist\Routrip\Routrip.exe (pasta onedir)
scripts\make_installer.ps1 -Version 1.0.0   # build + instalador único
```

O `make_installer.ps1` gera `installer\output\Routrip-Setup-<versão>.exe`, que é o
arquivo a distribuir. Requer o [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install -e --id JRSoftware.InnoSetup`). Use `-SkipBuild` para apenas
reempacotar o `dist` existente.

O instalador não exige administrador (instala em `%LocalAppData%\Programs\Routrip`
por padrão, com opção de instalar para todos os usuários), cria atalhos no menu
Iniciar e na área de trabalho, baixa e instala o **WebView2 Runtime** quando ausente
e inclui desinstalador.

> O executável não é assinado digitalmente, então o SmartScreen mostra
> "Windows protegeu o computador" na primeira execução: **Mais informações →
> Executar assim mesmo**. Para eliminar o aviso é preciso um certificado de
> assinatura de código.

Alternativa sem instalador: zipar a pasta `backend\dist\Routrip` inteira. O app **não inclui chave da API**:
cada usuário informa a própria chav3e gratuita do [openrouteservice.org](https://openrouteservice.org/)
em Configurações. A chave fica salva em `%APPDATA%\Routrip\config.json`.

## Limites do plano gratuito do ORS

- Matriz: 3500 pares por requisição (acima disso o ORS devolve o erro 6004), ou seja
  uma matriz completa de até 59×59. Passando disso, `ors_client.matrix()` monta a
  matriz em faixas de linhas, e o app limita a **100 paradas + origem** — custa 3
  requisições de matriz e 3 de direções por rota calculada
- Geocodificação: 100 req/min — a caixa de busca responde pelo cadastro local do IBGE
  (CNEFE) e só recorre ao ORS quando o endereço não está lá, então digitar não gasta cota
