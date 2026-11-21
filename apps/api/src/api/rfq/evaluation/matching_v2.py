"""Maximum-weight one-to-one assignment. Neither MPN nor quantity chooses identity."""

from difflib import SequenceMatcher

VERSION = "assignment/2.0"


def maximum_assignment(weights):
    if not weights:
        return []
    n = len(weights)
    m = len(weights[0])
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minimum = [float("inf")] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    current = -weights[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j] = current
                        way[j] = j0
                    if minimum[j] < delta:
                        delta = minimum[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if not p[j0]:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if not j0:
                break
    return [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]


def match_items(expected, predicted):
    weights = []
    for truth in expected:
        row = []
        for item in predicted:
            description = item.fields.get("description")
            line = item.fields.get("line_number")
            ratio = SequenceMatcher(
                None,
                (truth.get("description") or "").casefold(),
                (description.value or "").casefold() if description else "",
            ).ratio()
            same_line = bool(
                truth.get("line_number") and line and line.value == truth["line_number"]
            )
            evidence = next((e for f in item.fields.values() for e in f.evidence), None)
            source = truth.get("source", {})
            compatible = (
                not evidence
                or not source.get("sheet")
                or source["sheet"] == evidence.location.sheet
            )
            if (
                evidence
                and source.get("page")
                and evidence.location.page != source["page"]
            ):
                compatible = False
            score = (
                3 * ratio + (3 if same_line else 0)
                if compatible and (ratio >= 0.45 or same_line)
                else -1000
            )
            if (
                evidence
                and not source.get("bbox")
                and source.get("row") == evidence.location.row
            ):
                score += 1
            row.append(score)
        weights.append(row + [0.0] * len(expected))
    pairs = []
    for i, j in maximum_assignment(weights):
        if j >= len(predicted) or weights[i][j] <= 0:
            continue
        alternatives = [
            k
            for k in range(len(predicted))
            if k != j
            and abs(weights[i][k] - weights[i][j]) < 0.15
            and weights[i][k] > 0
        ]
        pairs.append(
            {
                "truth": i,
                "prediction": j,
                "ambiguous": bool(alternatives),
                "score": weights[i][j],
            }
        )
    return pairs
