import os
import time
import random
import subprocess
import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# Benchmark Configuration
# Lista de instâncias: (NUM_NODES, NUM_SEEDS)
INSTANCES = [
    (5,   20),
    (10,  20),
    (20,  20),
    (50,  5),
    (100, 5),
]

def generate_distance_matrix(num_nodes, seed):
    """Generates a symmetric Euclidean distance matrix using a random seed."""
    np.random.seed(seed)
    random.seed(seed)

    # Generate random 2D coordinates in [0, 1000] x [0, 1000]
    coords = np.random.randint(0, 1001, size=(num_nodes, 2))

    # Calculate pairwise Euclidean distances rounded to nearest integer (TSPLIB EUC_2D style)
    distance_matrix = np.zeros((num_nodes, num_nodes), dtype=int)
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:
                dist = np.sqrt((coords[i][0] - coords[j][0])**2 + (coords[i][1] - coords[j][1])**2)
                distance_matrix[i][j] = int(round(dist))
            else:
                distance_matrix[i][j] = 0
    return distance_matrix

def compute_tour_cost(tour, distance_matrix):
    """Calculates the total travel cost of a tour based on the distance matrix."""
    if not tour or len(tour) < 2:
        return float('inf')
    cost = 0
    n = len(tour)
    for i in range(n):
        cost += distance_matrix[tour[i]][tour[(i + 1) % n]]
    return cost

# -------------------------------------------------------------------------
# 1. Simplex (MIP Solver using MTZ formulation)
# -------------------------------------------------------------------------
def solve_simplex_mtz(distance_matrix):
    """Solves the TSP exactly using Miller-Tucker-Zemlin formulation in OR-Tools MIP solver."""
    n = len(distance_matrix)

    # Create the MIP solver using SCIP (which utilizes simplex relaxation and branch-and-bound)
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        # Fallback to CBC
        solver = pywraplp.Solver.CreateSolver('CBC')
    if not solver:
        raise Exception("MIP Solver (SCIP/CBC) not found.")

    # Variables: x_ij is 1 if the edge (i,j) is in the tour, 0 otherwise
    x = {}
    for i in range(n):
        for j in range(n):
            if i != j:
                x[i, j] = solver.BoolVar(f'x_{i}_{j}')
            else:
                x[i, j] = None

    # Variables: u_i for subtour elimination (for i = 1 to n-1)
    u = {}
    for i in range(1, n):
        u[i] = solver.NumVar(1.0, float(n - 1), f'u_{i}')

    # Constraints:
    # A. Each node must have exactly one outgoing edge
    for i in range(n):
        solver.Add(solver.Sum(x[i, j] for j in range(n) if i != j) == 1)

    # B. Each node must have exactly one incoming edge
    for j in range(n):
        solver.Add(solver.Sum(x[i, j] for i in range(n) if i != j) == 1)

    # C. MTZ Subtour Elimination Constraints:
    # u_i - u_j + n * x_ij <= n - 1 (for i, j >= 1, i != j)
    for i in range(1, n):
        for j in range(1, n):
            if i != j:
                solver.Add(u[i] - u[j] + n * x[i, j] <= n - 1)

    # Objective: Minimize total distance
    objective = solver.Objective()
    for i in range(n):
        for j in range(n):
            if i != j:
                objective.SetCoefficient(x[i, j], float(distance_matrix[i][j]))
    objective.SetMinimization()

    # Solve
    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        # Extract the tour
        tour = [0]
        curr = 0
        visited = {0}
        while len(tour) < n:
            next_node = None
            for j in range(n):
                if curr != j and x[curr, j].solution_value() > 0.5:
                    next_node = j
                    break
            if next_node is None or next_node in visited:
                break
            tour.append(next_node)
            visited.add(next_node)
            curr = next_node

        return tour, objective.Value()
    else:
        return None, float('inf')

# -------------------------------------------------------------------------
# 2. LKH3 Solver Wrapper
# -------------------------------------------------------------------------
def solve_lkh3(distance_matrix, seed):
    """Solves the TSP using the compiled LKH3 solver via TSPLIB files."""
    n = len(distance_matrix)

    # Define unique filenames based on the seed and instance size to avoid collisions
    tsp_filename = f"temp_n{n}_seed_{seed}.tsp"
    par_filename = f"temp_n{n}_seed_{seed}.par"
    tour_filename = f"temp_n{n}_seed_{seed}.tour"

    # A. Write the TSP file (Explicit Full Matrix format)
    with open(tsp_filename, "w") as f:
        f.write(f"NAME : temp_n{n}_seed_{seed}\n")
        f.write("TYPE : TSP\n")
        f.write(f"DIMENSION : {n}\n")
        f.write("EDGE_WEIGHT_TYPE : EXPLICIT\n")
        f.write("EDGE_WEIGHT_FORMAT : FULL_MATRIX\n")
        f.write("EDGE_WEIGHT_SECTION\n")
        for row in distance_matrix:
            f.write(" ".join(map(str, row)) + "\n")
        f.write("EOF\n")

    # B. Write the Parameter file
    with open(par_filename, "w") as f:
        f.write(f"PROBLEM_FILE = {tsp_filename}\n")
        f.write(f"OUTPUT_TOUR_FILE = {tour_filename}\n")
        f.write("RUNS = 1\n")

    # C. Run LKH.exe
    workspace = os.path.dirname(os.path.abspath(__file__))
    lkh_path = os.path.join(workspace, "LKH.exe")

    try:
        subprocess.run(
            [lkh_path, par_filename],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        # Cleanup and raise
        for fn in [tsp_filename, par_filename, tour_filename]:
            if os.path.exists(fn):
                os.remove(fn)
        raise Exception(f"LKH3 solver execution failed: {e.stderr}")

    # D. Parse output tour
    tour = []
    if os.path.exists(tour_filename):
        with open(tour_filename, "r") as f:
            lines = f.readlines()

        in_tour_section = False
        for line in lines:
            line = line.strip()
            if line.startswith("TOUR_SECTION"):
                in_tour_section = True
                continue
            if in_tour_section:
                if line == "-1":
                    break
                # LKH output is 1-indexed, convert to 0-indexed
                node = int(line) - 1
                tour.append(node)

    # E. Clean up files
    for fn in [tsp_filename, par_filename, tour_filename]:
        if os.path.exists(fn):
            try:
                os.remove(fn)
            except:
                pass

    if tour:
        # Align tour to start at node 0
        start_idx = tour.index(0)
        shifted_tour = tour[start_idx:] + tour[:start_idx]
        return shifted_tour
    else:
        raise Exception("Failed to read tour from LKH3 output.")

# -------------------------------------------------------------------------
# 3. Google OR-Tools Routing Solver
# -------------------------------------------------------------------------
def solve_ortools_routing(distance_matrix):
    """Solves the TSP using Google OR-Tools Routing Library."""
    n = len(distance_matrix)

    # Create the routing index manager and routing model
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)  # locations, vehicles, start depot
    routing = pywrapcp.RoutingModel(manager)

    # Distance Callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.solution_limit = 100

    # Solve
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        tour = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            tour.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        return tour, solution.ObjectiveValue()
    else:
        return None, float('inf')

# -------------------------------------------------------------------------
# 4. Nearest Neighbor (Vizinho Mais Próximo)
# -------------------------------------------------------------------------
def solve_nearest_neighbor_tour(distance_matrix):
    """Solves the TSP heuristically by choosing the nearest unvisited node at each step."""
    n = len(distance_matrix)
    curr = 0
    tour = [0]
    unvisited = set(range(1, n))

    while unvisited:
        next_node = min(unvisited, key=lambda x: distance_matrix[curr][x])
        tour.append(next_node)
        unvisited.remove(next_node)
        curr = next_node

    return tour

# -------------------------------------------------------------------------
# 5. Ant Colony Optimization (Ant Colony System - ACS)
# -------------------------------------------------------------------------
def solve_acs(distance_matrix, num_iterations=100, beta=2.0, q0=0.9, alpha=0.1, rho=0.1):
    """Solves the TSP using the Ant Colony System (ACS) metaheuristic."""
    n = len(distance_matrix)

    # Use Nearest Neighbor to establish a baseline L_nn
    nn_tour = solve_nearest_neighbor_tour(distance_matrix)
    L_nn = compute_tour_cost(nn_tour, distance_matrix)

    # Initialize pheromone levels
    tau_0 = 1.0 / (n * L_nn)
    tau = np.full((n, n), tau_0)

    # Precompute visibility eta = 1 / distance
    eta = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                eta[i, j] = 1.0 / float(distance_matrix[i][j])

    best_tour = nn_tour
    best_cost = L_nn

    for iteration in range(num_iterations):
        tours = []
        costs = []

        # Place N ants, one at each starting node
        for ant in range(n):
            start_node = ant
            tour = [start_node]
            unvisited = set(range(n))
            unvisited.remove(start_node)

            curr = start_node
            while unvisited:
                nodes_list = list(unvisited)
                # Compute product of pheromone and desirability
                values = [tau[curr, u] * (eta[curr, u] ** beta) for u in nodes_list]

                q = random.random()
                if q <= q0:
                    # Exploitation
                    max_idx = np.argmax(values)
                    next_node = nodes_list[max_idx]
                else:
                    # Probabilistic Exploration
                    total = sum(values)
                    if total == 0:
                        next_node = random.choice(nodes_list)
                    else:
                        probs = [v / total for v in values]
                        next_node = random.choices(nodes_list, weights=probs, k=1)[0]

                tour.append(next_node)
                unvisited.remove(next_node)

                # Local pheromone update
                tau[curr, next_node] = (1 - rho) * tau[curr, next_node] + rho * tau_0
                tau[next_node, curr] = tau[curr, next_node]  # Maintain symmetry

                curr = next_node

            # Local update for returning edge
            tau[curr, start_node] = (1 - rho) * tau[curr, start_node] + rho * tau_0
            tau[start_node, curr] = tau[curr, start_node]

            tours.append(tour)
            costs.append(compute_tour_cost(tour, distance_matrix))

        # Update global best tour
        iter_best_idx = np.argmin(costs)
        if costs[iter_best_idx] < best_cost:
            best_cost = costs[iter_best_idx]
            best_tour = tours[iter_best_idx]

        # Global pheromone update (applied only to edges in the global best tour)
        tau = (1 - alpha) * tau
        delta_tau = 1.0 / best_cost
        for i in range(n):
            u = best_tour[i]
            v = best_tour[(i + 1) % n]
            tau[u, v] += alpha * delta_tau
            tau[v, u] += alpha * delta_tau  # Maintain symmetry

    # Shift best_tour to start at 0
    start_idx = best_tour.index(0)
    shifted_tour = best_tour[start_idx:] + best_tour[:start_idx]
    return shifted_tour, best_cost

# -------------------------------------------------------------------------
# Main Execution Loop
# -------------------------------------------------------------------------
def main():
    print("Iniciando o comparativo de algoritmos para o TSP (multi-instâncias)...")
    print(f"Configurações: {INSTANCES}\n")

    results = []

    for num_nodes, num_seeds in INSTANCES:
        instance_label = f"TSP{num_nodes}"
        print(f"\n========== Instância {instance_label} (Seeds = {num_seeds}) ==========")

        for seed in range(1, num_seeds + 1):
            print(f"--- {instance_label} | Seed {seed:02d} ---")

            # 1. Generate the shared distance matrix
            distance_matrix = generate_distance_matrix(num_nodes, seed)

            row_data = {"Instance": instance_label, "Seed": seed}

            # A. Simplex (MIP SCIP/CBC)
            t_start = time.perf_counter()
            simplex_tour, _ = solve_simplex_mtz(distance_matrix)
            t_end = time.perf_counter()
            simplex_cost = compute_tour_cost(simplex_tour, distance_matrix)
            simplex_time = t_end - t_start
            row_data["Simplex_Cost"] = simplex_cost
            row_data["Simplex_Time (s)"] = simplex_time
            print(f"  [Simplex]        Custo: {simplex_cost:<6d} | Tempo: {simplex_time:.4f}s")

            # B. LKH3
            t_start = time.perf_counter()
            lkh_tour = solve_lkh3(distance_matrix, seed)
            t_end = time.perf_counter()
            lkh_cost = compute_tour_cost(lkh_tour, distance_matrix)
            lkh_time = t_end - t_start
            row_data["LKH3_Cost"] = lkh_cost
            row_data["LKH3_Time (s)"] = lkh_time
            print(f"  [LKH3]           Custo: {lkh_cost:<6d} | Tempo: {lkh_time:.4f}s")

            # C. Google OR-Tools
            t_start = time.perf_counter()
            ortools_tour, _ = solve_ortools_routing(distance_matrix)
            t_end = time.perf_counter()
            ortools_cost = compute_tour_cost(ortools_tour, distance_matrix)
            ortools_time = t_end - t_start
            row_data["ORTools_Cost"] = ortools_cost
            row_data["ORTools_Time (s)"] = ortools_time
            print(f"  [OR-Tools]       Custo: {ortools_cost:<6d} | Tempo: {ortools_time:.4f}s")

            # D. Nearest Neighbor
            t_start = time.perf_counter()
            nn_tour = solve_nearest_neighbor_tour(distance_matrix)
            t_end = time.perf_counter()
            nn_cost = compute_tour_cost(nn_tour, distance_matrix)
            nn_time = t_end - t_start
            row_data["NearestNeighbor_Cost"] = nn_cost
            row_data["NearestNeighbor_Time (s)"] = nn_time
            print(f"  [NearestNeighbor]Custo: {nn_cost:<6d} | Tempo: {nn_time:.4f}s")

            # E. Ant Colony Optimization (ACS)
            t_start = time.perf_counter()
            aco_tour, _ = solve_acs(distance_matrix, num_iterations=100)
            t_end = time.perf_counter()
            aco_cost = compute_tour_cost(aco_tour, distance_matrix)
            aco_time = t_end - t_start
            row_data["ACO_Cost"] = aco_cost
            row_data["ACO_Time (s)"] = aco_time
            print(f"  [ACO - ACS]      Custo: {aco_cost:<6d} | Tempo: {aco_time:.4f}s")

            results.append(row_data)
            print("-" * 50)

    # 2. Save results to Excel (.xlsx) using pandas
    df = pd.DataFrame(results)

    # Reorder columns to group by algorithm for easier comparison
    col_order = [
        "Instance", "Seed",
        "Simplex_Cost", "Simplex_Time (s)",
        "LKH3_Cost", "LKH3_Time (s)",
        "ORTools_Cost", "ORTools_Time (s)",
        "NearestNeighbor_Cost", "NearestNeighbor_Time (s)",
        "ACO_Cost", "ACO_Time (s)"
    ]
    df = df[col_order]

    # Localizar o diretório da Área de Trabalho (Desktop) do usuário no Windows
    user_profile = os.environ.get('USERPROFILE', os.path.expanduser('~'))
    desktop_options = [
        os.path.join(user_profile, 'Desktop'),
        os.path.join(user_profile, 'OneDrive', 'Desktop'),
        os.path.join(user_profile, 'OneDrive - Personal', 'Desktop')
    ]

    desktop_path = user_profile
    for option in desktop_options:
        if os.path.exists(option):
            desktop_path = option
            break

    output_filename = os.path.join(desktop_path, "Comparação TSPs.xlsx")
    df.to_excel(output_filename, index=False)
    print(f"\nResultados salvos em: {output_filename}")

if __name__ == "__main__":
    main()
