"""Vocabulário de endereços brasileiros compartilhado pelo parser e pelo cliente do ORS."""

import re
import unicodedata

# Abreviação (sem ponto, minúscula, sem acento) -> forma canônica.
TIPOS_LOGRADOURO: dict[str, str] = {
    "r": "Rua",
    "rua": "Rua",
    "av": "Avenida",
    "avn": "Avenida",
    "avenida": "Avenida",
    "al": "Alameda",
    "alameda": "Alameda",
    "tv": "Travessa",
    "trav": "Travessa",
    "travessa": "Travessa",
    "rod": "Rodovia",
    "rodovia": "Rodovia",
    "est": "Estrada",
    "estr": "Estrada",
    "estrada": "Estrada",
    "pc": "Praça",
    "pca": "Praça",
    "praca": "Praça",
    "lg": "Largo",
    "lgo": "Largo",
    "largo": "Largo",
    "vla": "Viela",
    "viela": "Viela",
    "via": "Via",
    "linha": "Linha",
    "mar": "Marginal",
    "marginal": "Marginal",
    "psg": "Passagem",
    "passagem": "Passagem",
    "ladeira": "Ladeira",
    "servidao": "Servidão",
    "quadra": "Quadra",
    "setor": "Setor",
}

# Prefixos que denotam bairro/loteamento, não tipo de logradouro.
PREFIXOS_BAIRRO = (
    "jardim", "jd", "vila", "vl", "parque", "pq", "conjunto", "cj", "residencial",
    "loteamento", "chacara", "chacaras", "nucleo", "distrito", "sitio", "bairro",
    "centro", "cidade", "recanto", "colina", "morada",
)

UF_SIGLAS = frozenset((
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
))

UF_POR_NOME: dict[str, str] = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}

TERMOS_COMPLEMENTO = (
    "apto", "apart", "apartamento", "ap", "bloco", "bl", "casa", "cs", "sala",
    "sl", "andar", "fundos", "frente", "loja", "lj", "galpao", "conjunto",
    "torre", "lote", "lt", "km", "sobrado", "anexo",
)

MARCADORES_DESTINO = re.compile(
    r"(?i)\b(destinat[áa]rio|entregar?\s+(?:em|para|a)|local\s+de\s+entrega|"
    r"endere[çc]o\s+de\s+entrega|cliente|comprador|sacado)\b"
)
MARCADORES_ORIGEM = re.compile(
    r"(?i)\b(emitente|remetente|expedidor|transportador|fornecedor|raz[ãa]o\s+social)\b"
)

# Sequências que nunca fazem parte de um endereço e atrapalham a extração do CEP
# e do número (o CNPJ e a chave da NF-e são os piores ofensores).
DESCARTAVEIS = re.compile(
    r"\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}"          # CNPJ
    r"|(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"     # CPF
    r"|(?<!\d)\d{44}(?!\d)"                        # chave de acesso da NF-e
    r"|\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)"     # telefone
    r"|R\$\s?[\d.,]+"                              # valores
    r"|(?<!\d)\d{2}/\d{2}/\d{2,4}(?!\d)"           # datas
    r"|\b\d{2}:\d{2}(?::\d{2})?\b"                 # horas
)

RUIDO = re.compile(r"[|_~•■□®°*]+")

# O ponto de milhar aparece em "13.400-000", grafia comum em nota fiscal.
CEP = re.compile(r"(?<!\d)(\d{2}\.?\d{3})[.\-\s]?(\d{3})(?!\d)")


def formatar_cep(m: re.Match[str]) -> str:
    return f"{m.group(1).replace('.', '')}-{m.group(2)}"


# O geocoder do ORS lida mal com abreviações ("R. Alfredo" não acha "Rua Alfredo").
# Só entram as inequívocas: "Mar." é Marechal muito mais vezes que Marginal.
ABREVIACOES: dict[str, str] = {
    "r": "Rua", "av": "Avenida", "avn": "Avenida", "al": "Alameda",
    "tv": "Travessa", "trav": "Travessa", "rod": "Rodovia", "est": "Estrada",
    "estr": "Estrada", "pc": "Praça", "pç": "Praça", "pca": "Praça",
    "pça": "Praça", "lgo": "Largo", "psg": "Passagem",
    "jd": "Jardim", "vl": "Vila", "pq": "Parque", "cj": "Conjunto",
}
_ABREVIACAO = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in ABREVIACOES) + r")\.", re.IGNORECASE
)

_TIPO_ALTERNATIVAS = "|".join(
    sorted((re.escape(t) for t in TIPOS_LOGRADOURO), key=len, reverse=True)
)
# Casa "Av.", "AV", "Avenida" — mas não o começo de outra palavra ("Aveiro").
TIPO_LOGRADOURO = re.compile(
    rf"(?<![0-9A-Za-zÀ-ú])({_TIPO_ALTERNATIVAS})\.?(?![0-9A-Za-zÀ-ú])", re.IGNORECASE
)


def sem_acento(text: str) -> str:
    normalizado = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def normalizar(text: str) -> str:
    """Forma canônica para comparação: sem acento, minúscula, sem pontuação."""
    return re.sub(r"[^a-z0-9 ]+", " ", sem_acento(text).lower()).strip()


def expandir_tipo(token: str) -> str | None:
    return TIPOS_LOGRADOURO.get(sem_acento(token).lower().strip(". "))


def expandir_abreviacoes(text: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        palavra = ABREVIACOES[m.group(1).lower()]
        return palavra if m.group(1)[0].isupper() else palavra.lower()

    return _ABREVIACAO.sub(_sub, text)
