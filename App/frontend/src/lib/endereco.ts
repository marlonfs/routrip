import type { AddressOption } from "../types";

/** O quanto a posição do pino é cadastro e o quanto é dedução. Quem sabe é o servidor:
 * só ele conhece a versão da base instalada. "entre X e Y" é o que deixa o usuário
 * julgar — entre 450 e 460 é a casa certa, entre 100 e 890 é o meio da rua. */
export function badgeNumero(o: AddressOption): { texto: string; classe: string } {
  switch (o.numero_status) {
    case "exato":
      return { texto: `nº ${o.numero} no cadastro`, classe: "badge ok" };
    case "vizinho":
      return { texto: `entre ${o.num_antes} e ${o.num_depois}`, classe: "badge ok soft" };
    case "fora":
      return { texto: "nº fora da rua", classe: "badge warn" };
    case "faixa":
      return { texto: "nº na faixa da rua", classe: "badge ok soft" };
    case "sem_numeracao":
      return { texto: "rua sem nº no cadastro", classe: "badge ok soft" };
    default:
      return { texto: "rua no cadastro", classe: "badge ok soft" };
  }
}

/** "Rua X, Piracicaba - SP" com número vira "Rua X, 1500, Piracicaba - SP". */
export function rotuloParada(o: AddressOption, numero: string): string {
  if (!numero.trim()) return o.label;
  const corte = o.label.indexOf(",");
  return corte < 0
    ? `${o.label}, ${numero}`
    : `${o.label.slice(0, corte)}, ${numero}${o.label.slice(corte)}`;
}
