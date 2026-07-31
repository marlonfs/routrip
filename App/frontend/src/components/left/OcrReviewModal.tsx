import { useRef, useState } from "react";
import { api, postJson } from "../../api/client";
import { newStopId, useAppStore } from "../../store/useAppStore";
import type { AddressOption, CnefeBusca, ResolvedAddress } from "../../types";

interface ReviewItem {
  id: string;
  lido: string;
  opcoes: AddressOption[];
  /** `null` significa "não adicionar": rádio não desmarca sozinho e o usuário
   * precisa de um jeito explícito de recusar o que foi proposto. */
  escolha: string | null;
  numero: string;
  busca: string;
  cidade: string;
  uf: string;
  avisos: string[];
  ocupado: boolean;
  erro?: string;
  adicionado: boolean;
}

const AVISO: Record<string, string> = {
  cep_logradouro_divergente: "a rua lida não bate com a do CEP",
  cep_inexistente: "CEP não existe",
  cep_nao_verificado: "não foi possível consultar o CEP",
  cep_fora_da_base: "CEP ausente na base do IBGE",
  cep_generico: "CEP genérico, cobre a cidade inteira",
  rua_fora_do_cadastro: "esta rua não consta no cadastro do IBGE para esta cidade",
  municipio_desconhecido: "não deu para identificar a cidade",
};

const MIN_BUSCA = 3;
const ESPERA_MS = 250;

function naFaixa(o: AddressOption, numero: string): boolean {
  const n = Number(numero);
  return (
    o.num_min !== null && o.num_max !== null
    && Number.isInteger(n) && n >= o.num_min && n <= o.num_max
  );
}

/** "Rua X, Piracicaba - SP" com número vira "Rua X, 1500, Piracicaba - SP". */
function rotuloParada(o: AddressOption, numero: string): string {
  if (!numero.trim()) return o.label;
  const corte = o.label.indexOf(",");
  return corte < 0
    ? `${o.label}, ${numero}`
    : `${o.label.slice(0, corte)}, ${numero}${o.label.slice(corte)}`;
}

function faixa(o: AddressOption): string {
  if (o.num_min === null || o.num_max === null) return "";
  return ` · nºs ${o.num_min}–${o.num_max}`;
}

function novoItem(lido: string, p: ResolvedAddress | undefined): ReviewItem {
  const opcoes = p?.options ?? [];
  const melhor = opcoes[0];
  // Verificado e provável já vêm com a rua reconhecida no cadastro; deixar marcado
  // preserva a conveniência antiga sem esconder do usuário o que foi escolhido.
  const confiavel = p?.status === "verificado" || p?.status === "provavel";
  // Só a rua vai para o campo de busca. Mandar o endereço inteiro faria a base
  // comparar "alfredo guedes 1500 vila rezende piracicaba sp" com nomes de rua.
  const rua = [p?.parsed?.tipo_logradouro, p?.parsed?.logradouro].filter(Boolean).join(" ");
  return {
    id: p?.id ?? lido,
    lido,
    opcoes,
    escolha: confiavel && melhor ? melhor.id : null,
    numero: p?.parsed?.numero ?? (melhor?.numero != null ? String(melhor.numero) : ""),
    busca: rua || melhor?.logradouro || "",
    cidade: p?.parsed?.localidade ?? melhor?.municipio ?? "",
    uf: p?.parsed?.uf ?? melhor?.uf ?? "",
    avisos: p?.avisos ?? [],
    ocupado: false,
    adicionado: false,
  };
}

export default function OcrReviewModal() {
  const candidates = useAppStore((s) => s.candidates);
  const propostas = useAppStore((s) => s.propostas);
  const setReviewOpen = useAppStore((s) => s.setReviewOpen);
  const addStop = useAppStore((s) => s.addStop);
  const origin = useAppStore((s) => s.origin);

  const [items, setItems] = useState<ReviewItem[]>(() =>
    candidates.map((c) => novoItem(c.cleaned, propostas.find((p) => p.id === c.id))),
  );

  // A busca é disparada por digitação, então o handler que roda depois do atraso
  // enxergaria um `items` velho pelo closure.
  const atuais = useRef(items);
  atuais.current = items;
  const timers = useRef<Record<string, number>>({});

  const update = (id: string, changes: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...changes } : it)));

  const buscar = async (id: string) => {
    const item = atuais.current.find((it) => it.id === id);
    if (!item) return;
    const texto = (item.busca.trim() || item.lido).trim();
    if (texto.length < MIN_BUSCA || !item.cidade.trim()) return;

    update(id, { ocupado: true, erro: undefined });
    const params = new URLSearchParams({ texto, municipio: item.cidade.trim() });
    if (item.uf.trim()) params.set("uf", item.uf.trim());
    if (/^\d+$/.test(item.numero)) params.set("numero", item.numero);
    try {
      const r = await api<CnefeBusca>(`/api/cnefe/buscar?${params.toString()}`);
      // A lista é remontada a cada busca e os ids das opções são posicionais, então
      // a escolha do usuário é reencontrada pelo rótulo, não pelo id.
      const antes = item.opcoes.find((o) => o.id === item.escolha)?.label;
      update(id, {
        opcoes: r.opcoes,
        escolha: r.opcoes.find((o) => o.label === antes)?.id ?? null,
        ocupado: false,
        avisos: r.opcoes.length === 0 ? ["rua_fora_do_cadastro"] : [],
      });
    } catch (e) {
      update(id, { ocupado: false, erro: e instanceof Error ? e.message : "falhou" });
    }
  };

  const buscarDepois = (id: string) => {
    window.clearTimeout(timers.current[id]);
    timers.current[id] = window.setTimeout(() => void buscar(id), ESPERA_MS);
  };

  /** Escape do cadastro: o geocoder do ORS é o único que responde fora dele, e o que
   * ele devolve entra sempre marcado como não confirmado. */
  const tentarGeocoder = async (id: string) => {
    const item = atuais.current.find((it) => it.id === id);
    if (!item) return;
    update(id, { ocupado: true, erro: undefined });
    try {
      const r = await postJson<ResolvedAddress>("/api/geocode/resolve", {
        text: item.busca.trim() || item.lido,
        id: item.id,
        origin_lat: origin?.lat,
        origin_lon: origin?.lon,
      });
      update(id, {
        opcoes: r.options,
        escolha: null,
        ocupado: false,
        avisos: r.options.length === 0 ? [...item.avisos, "nada_no_geocoder"] : item.avisos,
      });
    } catch (e) {
      update(id, { ocupado: false, erro: e instanceof Error ? e.message : "falhou" });
    }
  };

  const adicionar = () => {
    const escolhidos = items.filter((it) => !it.adicionado && it.escolha);
    for (const it of escolhidos) {
      const o = it.opcoes.find((op) => op.id === it.escolha);
      if (o) addStop({ id: newStopId(), label: rotuloParada(o, it.numero), lat: o.lat, lon: o.lon });
    }
    const ids = new Set(escolhidos.map((it) => it.id));
    setItems((prev) => prev.map((it) => (ids.has(it.id) ? { ...it, adicionado: true } : it)));
    if (escolhidos.length === items.length) setReviewOpen(false);
  };

  const prontos = items.filter((it) => !it.adicionado && it.escolha).length;

  return (
    <div className="modal-backdrop">
      <div className="modal modal-wide">
        <h2>Endereços encontrados</h2>
        <p className="muted">
          As opções abaixo vêm do cadastro de endereços do IBGE — só aparece aqui o que
          existe de verdade. Confira o número e escolha um endereço por linha.
        </p>

        <div className="review-list">
          {items.map((item) => (
            <div className="review-item-block" key={item.id}>
              <div className="review-item">
                <strong className="review-lido">{item.lido}</strong>
                {item.adicionado && <span className="badge ok">na rota</span>}
                {item.ocupado && <span className="badge warn">buscando…</span>}
                {item.erro && <span className="badge err">{item.erro}</span>}
              </div>

              {!item.adicionado && (
                <div className="review-detail">
                  {item.avisos.map((a) => (
                    <small className="muted" key={a}>
                      ⚠ {AVISO[a] ?? a}
                    </small>
                  ))}

                  {item.opcoes.map((o) => (
                    <label className="review-opcao" key={o.id}>
                      <input
                        type="radio"
                        name={`op-${item.id}`}
                        checked={item.escolha === o.id}
                        onChange={() => update(item.id, { escolha: o.id })}
                      />
                      <span>
                        {o.label}
                        <small className="muted">{faixa(o)}</small>
                      </span>
                      {o.confirmado ? (
                        <span className={naFaixa(o, item.numero) ? "badge ok" : "badge ok soft"}>
                          {naFaixa(o, item.numero) ? "número confere" : "rua no cadastro"}
                        </span>
                      ) : (
                        <span className="badge warn">não confirmado</span>
                      )}
                    </label>
                  ))}

                  {item.opcoes.length > 0 && (
                    <label className="review-opcao">
                      <input
                        type="radio"
                        name={`op-${item.id}`}
                        checked={item.escolha === null}
                        onChange={() => update(item.id, { escolha: null })}
                      />
                      <span className="muted">Não adicionar este endereço</span>
                    </label>
                  )}

                  <div className="review-campos">
                    <label>
                      Número
                      <input
                        type="text"
                        inputMode="numeric"
                        value={item.numero}
                        onChange={(e) => {
                          update(item.id, { numero: e.target.value });
                          buscarDepois(item.id);
                        }}
                      />
                    </label>
                    <label>
                      Cidade
                      <input
                        type="text"
                        value={item.cidade}
                        onChange={(e) => {
                          update(item.id, { cidade: e.target.value });
                          buscarDepois(item.id);
                        }}
                      />
                    </label>
                    <label className="curto">
                      UF
                      <input
                        type="text"
                        maxLength={2}
                        value={item.uf}
                        onChange={(e) => {
                          update(item.id, { uf: e.target.value.toUpperCase() });
                          buscarDepois(item.id);
                        }}
                      />
                    </label>
                    <label className="cresce">
                      Rua
                      <input
                        type="text"
                        placeholder="nome da rua"
                        value={item.busca}
                        onChange={(e) => {
                          update(item.id, { busca: e.target.value });
                          buscarDepois(item.id);
                        }}
                      />
                    </label>
                  </div>

                  {item.opcoes.length === 0 && (
                    <button
                      className="btn-link"
                      disabled={item.ocupado}
                      onClick={() => void tentarGeocoder(item.id)}
                    >
                      Não está no cadastro do IBGE — procurar mesmo assim no mapa
                      (entra na rota como não confirmado)
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={() => setReviewOpen(false)}>
            Fechar
          </button>
          <button className="btn-primary" disabled={prontos === 0} onClick={adicionar}>
            Adicionar selecionados ({prontos})
          </button>
        </div>
      </div>
    </div>
  );
}
