import numpy as np
from collections import defaultdict
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.csgraph import (maximum_bipartite_matching,
                                  connected_components, breadth_first_order)

def are_strongly_connected(graph, u, v):
    """Check if nodes u and v are strongly connected."""
    # Path from u to v
    order = breadth_first_order(graph, u, directed=True, return_predecessors=False)
    u_to_v = v in order
    # Path from v to u
    order = breadth_first_order(graph, v, directed=True, return_predecessors=False)
    v_to_u = u in order
    return u_to_v and v_to_u

def get_path(predecessors, start, end):
    """Extract path from start to end using predecessors array."""
    if predecessors[end] == -9999 and start != end:
        return None
    path = []
    current = int(end)
    while current != -9999:
        path.append(current)
        if current == start:
            break
        current = int(predecessors[current])
    if current != start:
        return None
    return path[::-1]


def find_permutations(M):
    n = M.shape[0]
    used_cols = [False] * n
    perm = [-1] * n  # perm[i] = column assigned to row i
    solutions = []

    def backtrack(row):
        if row == n:
            P = np.zeros((n, n), dtype=int)
            for i in range(n):
                P[i, perm[i]] = 1
            solutions.append(P.copy())
            return
        for col in range(n):
            if M[row, col] == 1 and not used_cols[col]:
                used_cols[col] = True
                perm[row] = col
                backtrack(row + 1)
                used_cols[col] = False

    backtrack(0)
    return solutions


def bipartite_matching_orig(graph, n):
    """Find a maximum matching in a bipartite graph using DFS.
    graph[i] = list of columns j where M[i, j] = 1.
    Returns the size of the maximum matching."""
    match = [-1] * n  # match[i] = column matched to row i, or -1
    used = [False] * n

    def dfs(row, visited):
        if visited[row]:
            return False
        visited[row] = True
        for col in graph[row]:
            if match[col] == -1 or (dfs(match[col], visited)):
                match[col] = row
                return True
        return False

    matching_size = 0
    for i in range(n):
        visited = [False] * n
        if dfs(i, visited):
            matching_size += 1
    return matching_size

def find_closed_components_orig(M):
    """Find closed components (S, T) where M[T, S] is all 1s and |S| = |T|."""
    n = M.shape[0]
    col_to_rows = defaultdict(set)
    for j in range(n):
        for i in range(n):
            if M[i, j] == 1:
                col_to_rows[j].add(i)

    # Group columns by their row sets
    rowset_to_cols = defaultdict(set)
    for j, rows in col_to_rows.items():
        rowset_to_cols[frozenset(rows)].add(j)

    closed_components = []
    for rows, cols in rowset_to_cols.items():
        rows = set(rows)
        cols = set(cols)
        if len(rows) == len(cols) and len(rows) > 0:
            # Verify M[rows, cols] is all 1s
            is_closed = True
            for i in rows:
                for j in cols:
                    if M[i, j] != 1:
                        is_closed = False
                        break
                if not is_closed:
                    break
            if is_closed:
                closed_components.append((cols, rows))

    return closed_components

def find_closed_components(M):
    # Indices n..2n-1 correspond to the column
    num, mask = connected_components(bipartite_to_directed(M))
    return [*mask[n:]]

def is_or_matrix(M):
    """Predicate: Returns True if M equals the OR matrix R, False otherwise."""
    n = M.shape[0]

    # Step 1: Check if M is all zeros (special case: R = 0 if no solutions, or M = R = 0)
    if np.all(M == 0):
        return True  # R is all zeros (no perfect matchings possible)

    # Step 2: Build adjacency list for bipartite graph
    graph = build_graph(M, n)

    # Step 3: Check if M supports a perfect matching
    if bipartite_matching(graph, n) != n:
        return False  # No solutions exist, so R is all zeros, but M has 1s

    # Step 4: Check for closed components that force M[i, j] = 1 to R[i, j] = 0
    closed_components = find_closed_components(M)
    for cols, rows in closed_components:
        # Check if any i in rows, j not in cols has M[i, j] = 1
        for i in rows:
            for j in range(n):
                if j not in cols and M[i, j] == 1:
                    return False  # M[i, j] = 1 but R[i, j] = 0

    return True


def bipartite_matching(graph, matches_row=None, matches_col=None):
    # Returns matching size and match arrays
    # assuming graph is a lil_matrix
    # csr.nonzero()
    n = graph.shape[0]
    visited = [False] * n

    if matches_row is None and matches_col is None:
        matches_row = [None] * n
        matches_col = [None] * n
    elif matches_row is None:
        matches_row = [None] * n
        for col, row in enumerate(matches_col):
            if row is not None:
                matches_row[row] = col
    elif matches_col is None:
        matches_col = [None] * n
        for row, col in enumerate(matches_row):
            if col is not None:
                matches_col[col] = row

    def dfs(row):
        if visited[row]:
            return False
        visited[row] = True
        for _, col in zip(*graph[row].nonzero()):
            if matches_col[col] is None or dfs(matches_col[col]):
                matches_col[col] = row
                return True
        return False
    
    matching = sum(1 for x in matches_col if x is not None)

    for row, col in enumerate(matches_row):
        if col is None:
            visited = [False] * n
            if dfs(row):
                matching += 1

    for col, row in enumerate(matches_col):
        if row is not None:
            matches_row[row] = col
       
    return matching, matches_row, matches_col








def build_graph(M, n=None):
    """Build an adjacency list for a bipartite graph"""
    n = n or M.shape[0]
    return [[j for j in range(n) if M[i][j] == 1] for i in range(n)]


def get_path(predecessors, start, end):
    """Extract path from start to end using predecessors array."""
    if end >= len(predecessors) or start >= len(predecessors) or end < 0 or start < 0:
        return None
    if predecessors[end] == -9999 and start != end:
        return None
    path = []
    current = int(end)
    while current != -9999:
        path.append(current)
        if current == start:
            break
        current = int(predecessors[current])
        if current >= len(predecessors) or current < 0:
            return None
    if current != start:
        return None
    return path[::-1]

def are_strongly_connected(graph, u, v, n):
    """Check if u and v are strongly connected, return paths."""
    if u >= 2*n or v >= 2*n or u < 0 or v < 0:
        return False, None, None
    _, predecessors = breadth_first_order(graph, u, directed=True, return_predecessors=True)
    u_to_v_path = get_path(predecessors, u, v)
    u_to_v = u_to_v_path is not None
    
    _, predecessors = breadth_first_order(graph, v, directed=True, return_predecessors=True)
    v_to_u_path = get_path(predecessors, v, u)
    v_to_u = v_to_u_path is not None
    
    return u_to_v and v_to_u, u_to_v_path, v_to_u_path



def compute_or_matrix_safe(M):
    n = M.shape[0]
    
    # Convert M to LIL matrix
    graph = lil_matrix(M)
    edgeset = set(zip(*graph.nonzero()))
    known_good = set()

    matching_size, matches_row, matches_col = bipartite_matching(graph)

    # Discard known good edges
    edgeset.difference_update(enumerate(matches_row))
    # Add them to known good edges
    known_good.update(enumerate(matches_row))
    matches_col_save = tuple(matches_col)

    while edgeset:
        # Get an edge from the set
        row, col = edgeset.pop()

        save_row = graph[row, :].copy()
        save_col = graph[:,col].copy()

        # Set row & col to 0s except for (row, col) to force it in the matching
        graph[row, :] = 0
        graph[: ,col] = 0
        graph[row, col] = 1

        # Alter matches
        matches_col[matches_row[row]] = None
        match_count, new_matches_row, new_matches_col = bipartite_matching(graph, matches_col=matches_col)

        graph[row,:] = save_row  # restore the altered row
        graph[:,col] = save_col  # restore the altered row
        if match_count == n:  # Forced edge is in a perfect matching
            edgeset.difference_update(enumerate(new_matches_row))
            known_good.update(enumerate(new_matches_row))
        else:
            graph[row, col] = 0  # Remove edge completely
            # edgeset.remove((row, col)) # edge already pop()ed
        
        # restore the altered row and matches
        matches_col[:] = matches_col_save[:]


    return graph.toarray()



def compute_or_matrix(M):
    r"""
    This method computes the "OR" matrix, or the matrix of edges that are
    present in some perfect matching the bipartite graph represented by M, with
    the rows and columns represent each partition. Conceptually, it's the matrix
    that would result by ORing the set of all perfect matches together. Its time
    complexity is :math:`O(\lvert E \rvert \sqrt{\lvert V \rvert})`, bound by
    SciPy's maximum_bipartite_matching()
    """
    n = M.shape[0]

    if M.ndim != 2 or M.shape[0] != M.shape[1]:
        raise ValueError("M must be a 2D square matrix")

    if isinstance(M, lil_matrix):
        graph = M.tocsr(copy=True)
    else:
        graph = csr_matrix(M)

    # Step 1: Find perfect matching
    matches_row = maximum_bipartite_matching(graph, perm_type='row')
    if -1 in matches_row:
        return np.zeros((n, n), dtype=int)

    # Step 2: Create modified directed graph

    # Forward edges: i->j+n
    dg_indptr = graph.indptr
    dg_indices = graph.indices + n

    # Backward edges: j+n->i (matched)
    dg_indptr = np.append(dg_indptr, np.arange(n) + (dg_indptr[-1] + 1))
    dg_indices = np.append(dg_indices, matches_row)
    dg_data = np.ones_like(dg_indices)
    
    directed_graph = csr_matrix((dg_data, dg_indices, dg_indptr), shape=(2*n, 2*n))

    # Step 3: Find strongly connected components
    _, labels = connected_components(directed_graph, directed=True, connection='strong')

    # Step 4: Build R
    rows, cols = graph.nonzero()
    idx = np.nonzero(labels[rows] == labels[cols + n])
    R = csr_matrix((np.ones_like(idx[0]), (rows[idx], cols[idx])), shape = (n, n))

    return R




def bipartite_to_directed(bipartite_matrix, dtype=None):
    dtype=dtype or bipartite_matrix.dtype
    n = bipartite_matrix.shape[0]
    directed_matrix = np.zeros((2 * n, 2 * n), dtype=dtype)

    directed_matrix[:n, n:2*n] = bipartite_matrix

    directed_matrix[n:2*n, 0:n] = bipartite_matrix.T

    # directed_matrix[2*n,n:2*n] = np.ones((1, n), dtype=dtype)
    # directed_matrix[:n,2*n + 1] = np.ones((1, n), dtype=dtype)
    # # Populate the directed matrix
    # for i in range(n):
    #     for j in range(n):
    #         directed_matrix[i][n + j] = bipartite_matrix[i][j]  # Flow from left to right
    #         directed_matrix[n + j][i] = 0  # No flow from right to left

    return directed_matrix


if __name__ == '__main__':
    test_matrices = [
        np.array([
            [1, 1, 0],
            [1, 1, 1],
            [0, 0, 1],
        ]),

        np.array([
            [1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 1, 0]
        ]),

        np.array([
            [1, 1, 1, 1, 0],
            [1, 1, 0, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
        ]),


        np.array([
            [1, 0, 0, 0, 0],
            [1, 1, 0, 0, 0],
            [1, 1, 0, 1, 0],
            [1, 1, 1, 1, 0],
            [0, 1, 0, 0, 1]
        ]),

        np.array([
            [1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 1, 0]
        ]),

        np.array([
            [1, 1, 0, 0, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 0, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 0, 0]
        ]),

        np.array([
            [0, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1]
        ]),

        np.array([
            [0, 1, 1, 1, 0],
            [1, 1, 0, 0, 0],
            [1, 0, 1, 0, 0],
            [0, 0, 0, 1, 1],
            [0, 0, 0, 1, 1]
        ]),

        np.array([
            [0, 0, 1, 1, 1],
            [1, 0, 0, 0, 1],
            [1, 0, 1, 0, 0],
            [0, 1, 0, 1, 0],
            [0, 1, 0, 1, 0]
        ]),

        np.array([
            [1, 1, 0, 1, 0],
            [1, 1, 0, 1, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 1, 1],
        ])
    ]

    # Compute OR matrix
    def test_or():
        R = M.copy()
        closed_components = find_closed_components(M)
        for cols, rows in closed_components:
            # Set R[i, j] = 0 for i in rows, j not in cols where M[i, j] = 1
            for i in rows:
                for j in range(M.shape[1]):
                    if j not in cols and M[i, j] == 1:
                        R[i, j] = 0

        print("OR Matrix R:\n", R)

        # Test with the given matrix
        M = np.array([
            [1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 1, 0]
        ])
        print(is_or_matrix(M))  # Should print False

        # Test with the OR matrix R
        R = np.array([
            [1, 1, 0, 0, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 0, 0]
        ])
        print(is_or_matrix(R))  # Should print True

    def test_r2():
        R2 = np.array([
            [1, 0, 0, 0, 0],
            [1, 1, 0, 0, 0],
            [1, 1, 0, 1, 0],
            [1, 1, 1, 1, 0],
            [0, 1, 0, 0, 1]
        ])
        graph = build_graph(R2)

        res = bipartite_matching(graph, 5)
        print(f'{res = }')

    def test_r3():
        M = np.array([
            [1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 1, 0]
        ])
        graph = build_graph(M)

        # res = bipartite_matching(graph, 5)
        print(f'{is_or_matrix(M) = }')

    def test_r4():
        M = np.array([
            [1, 1, 0, 0, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 0, 1, 1],
            [0, 0, 1, 1, 1],
            [1, 1, 0, 0, 0]
        ])
        solutions = find_permutations(M)
        print(f"Number of solutions: {len(solutions)}")
        t = np.zeros_like(M)
        for i, P in enumerate(solutions):
            t |= P
            print(f"Solution {i+1}:\n{P}\n")

        print(f"Final ORed matrix:\n{t}\n")
        print(f'{is_or_matrix(M) = }')


    def test_r5():
        """this should find a CC"""
        M = np.array([
            [0, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 1, 1, 1]
        ])
        result = find_closed_components(M)
        print(f'{result = }')
        M2 = np.array([
            [0, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [0, 0, 0, 1, 1],
            [0, 0, 0, 1, 1]
        ])
        # result = find_closed_components(M2)
        # print(f'{result = }')
        M3 = np.array([
            [0, 1, 1, 1, 0],
            [1, 1, 0, 0, 0],
            [1, 0, 1, 0, 0],
            [0, 0, 0, 1, 1],
            [0, 0, 0, 1, 1]
        ])

        M4 = np.array([
            [0, 0, 1, 1, 1],
            [1, 0, 0, 0, 1],
            [1, 0, 1, 0, 0],
            [0, 1, 0, 1, 0],
            [0, 1, 0, 1, 0]
        ])
        # result = find_closed_components(M3)
        M4_or = compute_or_matrix(M4)
        print(f'{M4_or = }')
        print(f'{connected_components(bipartite_to_directed(M4_or)) = }')

    def test_r6():
        # A: 1 1 0 1 0
        # A: 1 1 0 1 0
        # B: 1 1 1 0 0
        # C: 1 1 1 0 0
        # ?: 1 1 1 1 1

        M = np.array([
            [1, 1, 0, 1, 0],
            [1, 1, 0, 1, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 0, 0],
            [1, 1, 1, 1, 1],
        ])
        M_or = compute_or_matrix(M)
        print(f'{M_or = }')
        print(f'{connected_components(bipartite_to_directed(M_or)) = }')

    def multi_test():
        np.set_printoptions(formatter={'str_kind': lambda x: x})
        for M in test_matrices:
            R1 = compute_or_matrix_safe(M)
            R2 = compute_or_matrix(M)
            if np.all(R1 == R2):
                print("Good comparison")
            else:
                print("Bad comparison")

            #str_M = f"{M}".split('\n')
            print("Original M")
            print(f"{M}")
            print("Results:")

            str_R1 = f"Expected:\n{R1}".split('\n')
            width = max(len(s) for s in str_R1)
            str_R1 = [s.ljust(width) for s in str_R1]

            str_R2 = f"Actual:\n{R2.toarray()}".split('\n')
            width = max(len(s) for s in str_R2)
            str_R2 = [s.ljust(width) for s in str_R2]

            str_diff = f"Differing:\n{np.where(R1 == R2, ' ', 'X')}".split('\n')
            width = max(len(s) for s in str_diff)
            str_diff = [s.ljust(width) for s in str_diff]

            combined_output = [f"{row1}   {row2}   {row3}" for row1, row2, row3 in zip(str_R1, str_R2, str_diff)]
            print('\n'.join(combined_output))
            print('=' * 72)

            # Print the matrices side by side with formatting

        if False:
            for row1, row2 in zip(matrix1, matrix2):
                print(f"{row1}     {row2}")

            str_matrix1 = [np.array2string(row, separator=' ')[1:-1] for row in matrix1]
            str_matrix2 = [np.array2string(row, separator=' ')[1:-1] for row in matrix2]

            # Zip the string representations and format them
            combined_output = [f"{row1}     {row2}" for row1, row2 in zip(str_matrix1, str_matrix2)]

            # Print the combined output
            for line in combined_output:
                print(line)



    def main():
        #test_r6()
        multi_test()


if __name__ == '__main__':

    main()

