"""
pipelines/setup_data.py
Reproducibly prepares the raw data layout in data/raw/rice/ from datasets/Rice Diversity/
Ensures path safety across Windows and Linux (no OS symlinks).
"""
import shutil
from pathlib import Path

def setup_rice_data(project_root: Path | None = None) -> None:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    source_dir = project_root / "datasets" / "Rice Diversity"
    dest_dir = project_root / "data" / "raw" / "rice"
    dest_pheno_dir = dest_dir / "phenotype"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_pheno_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy Genotype HapMap
    genotype_src = (
        source_dir
        / "Genotype - MET_crfilt_.75_allchrom.hmp.txt"
        / "MET_crfilt_.75_allchrom.hmp.txt"
    )
    genotype_dest = dest_dir / "MET_crfilt_.75_allchrom.hmp.txt"
    if genotype_src.exists() and not genotype_dest.exists():
        print(f"Copying genotype file: {genotype_src.name} -> {genotype_dest}")
        shutil.copy2(genotype_src, genotype_dest)
    elif genotype_dest.exists():
        print(f"Genotype file already exists: {genotype_dest}")
    else:
        print(f"WARNING: Source genotype not found at {genotype_src}")

    # 2. Copy Phenotype CSVs
    pheno_src_dir = (
        source_dir
        / "Phenotype & Env - RYT_plotdata_by_GHID_corrected_PUBLIC_ACCESS"
        / "RYT_plotdata_by_GHID_corrected_PUBLIC_ACCESS"
    )
    if pheno_src_dir.exists():
        csv_files = list(pheno_src_dir.glob("*.csv"))
        for f in csv_files:
            target = dest_pheno_dir / f.name
            if not target.exists():
                print(f"Copying phenotype file: {f.name} -> {target}")
                shutil.copy2(f, target)
        print(f"Phenotype CSV setup complete: {len(csv_files)} files copied.")
    else:
        print(f"WARNING: Source phenotype directory not found at {pheno_src_dir}")

if __name__ == "__main__":
    setup_rice_data()
