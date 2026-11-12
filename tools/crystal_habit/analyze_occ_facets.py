import csv, math, sys
from pathlib import Path
import numpy as np

root = Path(sys.argv[1])

# RJK2286_auto unit cell from the input CIF.
a, b, c = 10.5082, 6.3273, 15.1743
beta = math.radians(100.224)
A = np.array([[a, 0.0, c * math.cos(beta)], [0.0, b, 0.0], [0.0, 0.0, c * math.sin(beta)]]).T
B = np.linalg.inv(A).T

rows = list(csv.DictReader((root / "facet-energy-comparison.csv").open(encoding="utf-8-sig")))
by_solvent = {}
for r in rows:
    hkl = tuple(int(r[x]) for x in ("H", "K", "L"))
    by_solvent.setdefault(r["Solvent"], {})[hkl] = float(r["SurfaceEnergy"])

def read_ply(path):
    lines = path.read_text().splitlines()
    nv = nf = None
    end = None
    for i, line in enumerate(lines):
        if line.startswith("element vertex "): nv = int(line.split()[-1])
        if line.startswith("element face "): nf = int(line.split()[-1])
        if line == "end_header": end = i + 1; break
    verts = np.array([[float(x) for x in line.split()[:3]] for line in lines[end:end+nv]])
    faces = [[int(x) for x in line.split()[1:]] for line in lines[end+nv:end+nv+nf]]
    return verts, faces

def exposed_facets(solvent):
    verts, faces = read_ply(root / solvent / f"input_{solvent}.ply")
    facets = by_solvent[solvent]
    candidates = []
    for hkl, energy in facets.items():
        vec = B @ np.array(hkl, dtype=float)
        candidates.append((hkl, energy, vec / np.linalg.norm(vec)))
    hits = {}
    for face in faces:
        p = verts[face]
        normal = np.cross(p[1]-p[0], p[2]-p[0])
        norm = np.linalg.norm(normal)
        if norm < 1e-10: continue
        normal /= norm
        dist = abs(float(np.dot(normal, p[0])))
        best = min(candidates, key=lambda x: (1-abs(float(np.dot(normal, x[2]))), abs(dist-x[1])))
        cosine = abs(float(np.dot(normal, best[2])))
        if cosine > 0.9999 and abs(dist-best[1]) < 7e-4:
            hits[best[0]] = hits.get(best[0], 0) + 1
    return hits, len(verts), len(faces)

for solvent in by_solvent:
    hits, nv, nf = exposed_facets(solvent)
    print(f"SOLVENT {solvent} rows={len(by_solvent[solvent])} vertices={nv} triangles={nf} exposed={len(hits)}")
    for hkl in sorted(hits, key=lambda x: by_solvent[solvent][x]):
        print("ACTIVE", solvent, *hkl, f"{by_solvent[solvent][hkl]:.4f}", hits[hkl])

common = sorted(set(by_solvent["n-hexane"]) & set(by_solvent["water"]))
records = []
for hkl in common:
    eh = by_solvent["n-hexane"][hkl]
    ew = by_solvent["water"][hkl]
    records.append((hkl, eh, ew, ew-eh, (ew/eh-1)*100))

print("SUMMARY", "common", len(records), "corr", np.corrcoef([r[1] for r in records],[r[2] for r in records])[0,1])
print("MEAN", np.mean([r[1] for r in records]), np.mean([r[2] for r in records]), np.mean([r[3] for r in records]))
print("LOW_INDEX")
for r in sorted([r for r in records if sum(abs(x) for x in r[0]) <= 3]):
    print("DELTA", *r[0], f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:+.4f}", f"{r[4]:+.1f}%")
print("LARGEST_ABS_LOW8")
for r in sorted([r for r in records if max(abs(x) for x in r[0]) <= 8], key=lambda x: abs(x[3]), reverse=True)[:20]:
    print("CHANGE", *r[0], f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:+.4f}", f"{r[4]:+.1f}%")
