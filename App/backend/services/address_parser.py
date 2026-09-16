import re
import uuid
from difflib import SequenceMatcher

from core.schemas import AddressCandidate, ParsedAddress
from services import br_address_terms as termos
from services import cnefe

THRESHOLD = 0.3

_LIXO = " .,;:-/"
# Hífen e barra só separam quando cercados de espaço: "Mogi-Guaçu" é um nome só.
_SEPARADOR = re.compile(r"\s*[,;]\s*|\s+[-–/]\s+")
_SEM_NUMERO = re.compile(r"(?i)(?<![a-zà-ú])s\s*/?\s*n[ºo°.]?(?![a-zà-ú0-9])")
_NUMERO = re.compile(r"(?i)(?:,\s*|\bn[ºo°.]?\s*|\bnumero\s*|\s)(\d{1,6})\b")
_UF_SIGLA = re.compile(
    r"(?i)(?:^|[\s,;/-])(" + "|".join(termos.UF_SIGLAS) + r")(?![0-9A-Za-zÀ-ú])"
)
_ROTULO_BAIRRO = re.compile(r"(?i)\bbairro\s*:?\s*")
_ROTULO_CIDADE = re.compile(r"(?i)\b(cidade|munic[íi]pio|localidade)\s*:?\s*")
_ROTULO_CEP = re.compile(r"(?i)\bcep\s*:?\s*")
# A fronteira à direita evita que "LTDA" da razão social vire "Lt DA".
_COMPLEMENTO = re.compile(
    r"(?i)(?<![a-zà-ú])(" + "|".join(sorted(termos.TERMOS_COMPLEMENTO, key=len, reverse=True))
    + r")(?![a-zà-ú])\.?\s*:?\s*([\w/-]{1,12})"
)
_PREFIXO_BAIRRO = re.compile(
    r"(?i)^(" + "|".join(sorted(termos.PREFIXOS_BAIRRO, key=len, reverse=True)) + r")\.?\s"
)
_CONTEXTO = re.compile(
    r"(?i)\b(bairro|cidade|cep|munic[ií]pio|distrito|jardim|jd\.?|vila|centro|"
    r"parque|conjunto|residencial|quadra|lote)\b"
)


def _limpar(text: str) -> str:
    text = termos.RUIDO.sub(" ", text)
    text = termos.DESCARTAVEIS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-")
    return termos.CEP.sub(termos.formatar_cep, text)


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, termos.normalizar(a), termos.normalizar(b)).ratio()


def _cortar(text: str, inicio: int, fim: int) -> str:
    return re.sub(r"\s+", " ", (text[:inicio] + " , " + text[fim:])).strip(_LIXO)


def _segmentar(text: str) -> list[str]:
    return [s for s in (p.strip(_LIXO) for p in _SEPARADOR.split(text)) if s]


def _consumir_uf(resto: str, out: ParsedAddress) -> str:
    """Escada de três degraus. A sigla no fim do texto é o caso dominante; a sigla no
    meio fica por último porque colide com bairros curtos ("Sé" vira Sergipe), e vários
    estados são homônimos da capital ou de logradouros ("Rua São Paulo")."""
    siglas = list(_UF_SIGLA.finditer(resto))

    for m in reversed(siglas):
        if not resto[m.end(1):].strip(_LIXO):
            out.uf = m.group(1).upper()
            return _cortar(resto, m.start(1), m.end(1))

    for seg in reversed(_segmentar(resto)):
        uf = termos.UF_POR_NOME.get(termos.sem_acento(seg).lower())
        if uf:
            out.uf = uf
            inicio = resto.rfind(seg)
            return _cortar(resto, inicio, inicio + len(seg))

    if siglas:
        m = siglas[-1]
        out.uf = m.group(1).upper()
        return _cortar(resto, m.start(1), m.end(1))
    return resto


def parse_address(text: str) -> ParsedAddress:
    """Extrai campos por consumo-e-remoção: cada campo encontrado sai do texto para
    não competir com os seguintes."""
    resto = _limpar(text)
    out = ParsedAddress()

    m = termos.CEP.search(resto)
    if m:
        out.cep = termos.formatar_cep(m)
        inicio = m.start()
        rotulo = _ROTULO_CEP.search(resto, max(0, inicio - 6), inicio)
        resto = _cortar(resto, rotulo.start() if rotulo else inicio, m.end())

    resto = _consumir_uf(resto, out)

    m = _COMPLEMENTO.search(resto)
    if m:
        out.complemento = f"{m.group(1).capitalize()} {m.group(2)}"
        resto = _cortar(resto, m.start(), m.end())

    # A marca de "sem número" vira separador: em texto corrido de OCR ela é a única
    # fronteira entre o logradouro e o que vem depois.
    if _SEM_NUMERO.search(resto):
        out.sem_numero = True
        resto = _SEM_NUMERO.sub(" , ", resto)

    segmentos = _segmentar(resto)

    idx_logradouro = None
    for i, seg in enumerate(segmentos):
        m = termos.TIPO_LOGRADOURO.match(seg)
        if not m:
            continue
        out.tipo_logradouro = termos.expandir_tipo(m.group(1))
        nome = seg[m.end():].strip(_LIXO)
        num = _NUMERO.search(nome)
        if num:
            out.numero = num.group(1)
            sobra = nome[num.end():].strip(_LIXO)
            nome = nome[:num.start()].strip(_LIXO)
            if sobra:
                segmentos.insert(i + 1, sobra)
        out.logradouro = nome or None
        idx_logradouro = i
        break

    livres = [s for i, s in enumerate(segmentos) if i != idx_logradouro]

    if out.numero is None and idx_logradouro is not None and livres:
        proximo = segmentos[idx_logradouro + 1] if idx_logradouro + 1 < len(segmentos) else None
        if proximo and re.fullmatch(r"\d{1,6}", proximo):
            out.numero = proximo
            livres.remove(proximo)

    for seg in list(livres):
        m = _ROTULO_BAIRRO.match(seg)
        if m:
            out.bairro = seg[m.end():].strip(_LIXO) or None
            livres.remove(seg)
            break
        m = _ROTULO_CIDADE.match(seg)
        if m:
            out.localidade = seg[m.end():].strip(_LIXO) or None
            livres.remove(seg)
            break

    # Sem rótulo explícito, o último segmento livre é a cidade (vem colada à UF) e o
    # anterior é o bairro — a ordem canônica de um endereço escrito em pt-BR.
    if out.localidade is None and livres:
        out.localidade = livres.pop().strip(_LIXO) or None
    if out.bairro is None and livres:
        candidato = livres[-1]
        if _PREFIXO_BAIRRO.match(candidato) or _CONTEXTO.search(candidato) or len(livres) == 1:
            out.bairro = candidato.strip(_LIXO) or None

    if out.localidade and re.fullmatch(r"\d+", out.localidade):
        out.numero = out.numero or out.localidade
        out.localidade = None
    return out


def parse_busca(text: str) -> ParsedAddress:
    """Texto digitado na caixa de busca do painel.

    `parse_address` cobre o endereço escrito por extenso, mas se apoia em reconhecer o
    tipo de logradouro: em "Alfredo Guedes 1500" — o jeito normal de digitar numa caixa
    de busca — ele devolve todos os campos vazios e joga a linha inteira em `localidade`.
    Aqui a leitura é do fim para o começo: sai a UF, sai a cidade (só se ela existir no
    cadastro, senão "Rua Piracicaba" viraria cidade), sai o número, e o que sobra é a rua.
    """
    p = parse_address(text)
    if p.logradouro:
        return p

    resto = _limpar(text)
    out = ParsedAddress()
    m = termos.CEP.search(resto)
    if m:
        out.cep = termos.formatar_cep(m)
        resto = _cortar(resto, m.start(), m.end())
    resto = _consumir_uf(resto, out)

    segmentos = _segmentar(resto)
    if len(segmentos) > 1 and cnefe.municipio_por_nome(segmentos[-1], out.uf):
        out.localidade = segmentos.pop()
    if out.localidade is None and out.uf and len(segmentos) == 1:
        # Sem vírgula nenhuma a cidade fica colada na rua ("nossa senhora da penha 1506
        # vitoria es"). Exigir a UF escrita é o que impede "Rua São Paulo" de perder o
        # próprio nome para o município homônimo.
        palavras = segmentos[0].split()
        for n in (3, 2, 1):
            sobra = " ".join(palavras[:-n])
            m = termos.TIPO_LOGRADOURO.match(sobra)
            # Se o que sobra é só "Rua", o nome da rua é que era o município.
            if len(palavras) <= n or (m and not sobra[m.end():].strip(_LIXO)):
                continue
            if cnefe.municipio_por_nome(" ".join(palavras[-n:]), out.uf):
                out.localidade = " ".join(palavras[-n:])
                segmentos[0] = sobra
                break
    if len(segmentos) > 1 and re.fullmatch(r"\d{1,5}", segmentos[-1]):
        out.numero = segmentos.pop()
    if out.numero is None and segmentos:
        # Exige espaço antes: "Rua 25" tem o número no começo e ele é parte do nome.
        m = re.search(r"\s(?:n[ºo°.]?\s*)?(\d{1,5})$", segmentos[-1])
        if m:
            out.numero = m.group(1)
            segmentos[-1] = segmentos[-1][:m.start()].strip(_LIXO)

    via = " ".join(s for s in segmentos if s).strip(_LIXO)
    m = termos.TIPO_LOGRADOURO.match(via)
    if m:
        out.tipo_logradouro = termos.expandir_tipo(m.group(1))
        via = via[m.end():].strip(_LIXO)
    out.logradouro = via or None
    return out


def format_address(p: ParsedAddress) -> str:
    via = " ".join(x for x in (p.tipo_logradouro, p.logradouro) if x)
    if p.numero:
        via = f"{via}, {p.numero}" if via else p.numero
    elif p.sem_numero and via:
        via = f"{via}, s/n"
    partes = [via, p.complemento, p.bairro]
    if p.localidade and p.uf:
        partes.append(f"{p.localidade} - {p.uf}")
    else:
        partes.extend([p.localidade, p.uf])
    partes.append(p.cep)
    return ", ".join(x for x in partes if x)


def _score(text: str, p: ParsedAddress) -> float:
    score = 0.0
    if p.logradouro:
        score += 0.4
    if p.cep:
        score += 0.3
    if p.numero or p.sem_numero:
        score += 0.15
    if p.localidade or p.uf or p.bairro:
        score += 0.15
    if score == 0.0 and _CONTEXTO.search(text):
        score = 0.15
    return round(score, 2)


def _pesos_por_secao(lines: list[str]) -> list[float]:
    """Nota fiscal e romaneio trazem o endereço do emitente e o do destinatário; sem
    essa distinção, o CEP do emitente acaba colado ao logradouro do destinatário."""
    pesos: list[float] = []
    atual = 1.0
    for line in lines:
        if termos.MARCADORES_DESTINO.search(line):
            atual = 1.25
        elif termos.MARCADORES_ORIGEM.search(line):
            atual = 0.7
        pesos.append(atual)
    return pesos


def _ordem_coerente(linhas: list[str], p: ParsedAddress) -> bool:
    """Endereço brasileiro vai do logradouro para o CEP. CEP numa linha anterior à do
    logradouro significa que a janela juntou o fim de um endereço com o começo do
    seguinte, e o candidato sai com o logradouro de um e o CEP do vizinho — com nota
    máxima, porque todos os campos estão preenchidos."""
    if len(linhas) < 2 or not p.cep or not p.logradouro:
        return True
    alvo = termos.normalizar(p.logradouro)
    i_log = next((i for i, ln in enumerate(linhas) if alvo in termos.normalizar(ln)), None)
    i_cep = next((i for i, ln in enumerate(linhas) if termos.CEP.search(ln)), None)
    return i_log is None or i_cep is None or i_cep >= i_log


def _novo(raw: str, p: ParsedAddress, confianca: float) -> AddressCandidate:
    return AddressCandidate(
        id=uuid.uuid4().hex[:8],
        raw_text=raw,
        cleaned=format_address(p) or _limpar(raw),
        confidence=min(confianca, 1.0),
        parsed=p,
    )


def extract_address_candidates(text: str) -> list[AddressCandidate]:
    """Avalia janelas de 1 a 3 linhas adjacentes porque, em OCR e PDFs, o endereço
    costuma quebrar em várias linhas."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 6]
    pesos = _pesos_por_secao(lines)

    avaliados = []
    for i in range(len(lines)):
        for tamanho in (1, 2, 3):
            if i + tamanho > len(lines):
                break
            trecho = lines[i:i + tamanho]
            janela = ", ".join(trecho)
            p = parse_address(janela)
            if not _ordem_coerente(trecho, p):
                continue
            s = _score(janela, p) * pesos[i]
            if s >= THRESHOLD:
                avaliados.append((s, tamanho, janela, p))
    # Empate vai para a janela menor: ela carrega menos texto vizinho para dentro
    # dos campos (linha de valores virando cidade, razão social virando bairro).
    avaliados.sort(key=lambda item: (-item[0], item[1]))

    candidates: list[AddressCandidate] = []
    vistos: set[tuple] = set()
    ceps_com_rua: set[str] = set()
    for s, _tamanho, raw, p in avaliados:
        cleaned = format_address(p)
        # Sem logradouro e sem CEP não há o que geocodificar: é a linha de valores ou
        # o rodapé tendo sobrado da janela.
        if len(cleaned) < 8 or not (p.logradouro or p.cep):
            continue
        # A lista vem do mais completo para o menos, então a versão truncada do mesmo
        # endereço colide aqui e some da revisão em vez de virar uma segunda parada.
        chave = ((termos.normalizar(p.logradouro), p.numero) if p.logradouro
                 else ("", p.cep))
        # Cidade e CEP soltos são o rabo do endereço logo acima, já aceito com a rua.
        if not p.logradouro and p.cep in ceps_com_rua:
            continue
        if chave in vistos or any(_similar(cleaned, c.cleaned) > 0.85 for c in candidates):
            continue
        if p.logradouro and p.cep:
            ceps_com_rua.add(p.cep)
        vistos.add(chave)
        candidates.append(_novo(raw, p, s))
    return candidates


def candidates_from_lines(lines: list[str]) -> list[AddressCandidate]:
    """Linhas escolhidas manualmente na planilha: como a seleção é explícita, nada é
    descartado por pontuação e a deduplicação é exata (endereços na mesma rua são
    parecidos demais para o critério de similaridade)."""
    candidates: list[AddressCandidate] = []
    seen: set[str] = set()
    for raw in lines:
        p = parse_address(raw)
        cleaned = format_address(p) or _limpar(raw)
        if not cleaned or cleaned.casefold() in seen:
            continue
        seen.add(cleaned.casefold())
        candidates.append(_novo(raw, p, _score(raw, p)))
    return candidates
