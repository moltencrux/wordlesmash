import numpy as np
from collections import defaultdict
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching, connected_components


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



def compute_or_matrix(M):
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
            edgeset.remove((row, col))
        
        # restore the altered row and matches
        matches_col[:] = matches_col_save[:]


    return graph.toarray()





def build_graph(M, n=None):
    """Build an adjacency list for a bipartite graph"""
    n = n or M.shape[0]
    return [[j for j in range(n) if M[i][j] == 1] for i in range(n)]


# i,j means directed path from i to j (not j-> i)
# so... i tink our i,j and also j, i iwll be 1
# or.. rather i->j will become i->n+j
# what about j->i? necessary?
# UL quadrant empty b/c left partition does not connect to itself
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

    def main():
        test_r6()


if __name__ == '__main__':

    main()

