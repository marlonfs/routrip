/** Uma cor por veículo, no mapa e no itinerário. Começa pela cor da marca (a mesma
 * da rota de um veículo só) e evita o verde, que é o do ponto de partida. Com mais de
 * dez veículos as cores se repetem; o número do veículo continua distinguindo. */
const VEHICLE_COLORS = [
  "#A51C30",
  "#1D4ED8",
  "#D97706",
  "#7C3AED",
  "#0E7490",
  "#DB2777",
  "#4D7C0F",
  "#475569",
  "#EA580C",
  "#92400E",
];

/** `vehicle` começa em 1, como no servidor. */
export function vehicleColor(vehicle: number): string {
  return VEHICLE_COLORS[(vehicle - 1) % VEHICLE_COLORS.length];
}

export function vehiclesLabel(n: number): string {
  return n === 1 ? "1 veículo" : `${n} veículos`;
}
